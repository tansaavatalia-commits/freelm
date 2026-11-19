import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../src/App";

beforeEach(() => {
  window.scrollTo = vi.fn() as unknown as typeof window.scrollTo;
  // Nessuna rete nei test: API simulata (gioco giocabile, nessuna pubblicità).
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const body = String(url).includes("/status") ? { playable: true, reason: "" } : { source: "none" };
      return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const at = (path: string) => render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);

describe("pagine", () => {
  it("home: titolo, giochi e categorie", () => {
    at("/");
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("Classic games");
    for (const t of ["Mines", "Sudoku", "Nonogram"]) expect(screen.getAllByText(t).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "Logic" })).toBeTruthy();
  });

  it("pagina gioco: iframe sandboxed dal suo origin", async () => {
    at("/play/sudoku");
    const frame = (await screen.findByTitle("Sudoku game")) as HTMLIFrameElement;
    expect(frame.getAttribute("sandbox")).toBe("allow-scripts allow-same-origin");
    expect(frame.getAttribute("src")).toBe("http://localhost:5174/sudoku/index.html");
    expect(frame.getAttribute("referrerpolicy")).toBe("no-referrer");
    expect(screen.getByRole("heading", { name: "You might also like" })).toBeTruthy();
  });

  it("gioco sospeso: nessun iframe", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ playable: false, reason: "Rights review" }), { status: 200 })));
    at("/play/mines");
    expect((await screen.findByRole("alert")).textContent).toContain("Rights review");
    expect(screen.queryByTitle("Mines game")).toBeNull();
  });

  it("ricerca e 404", () => {
    at("/search?q=daily");
    expect(screen.getByRole("status").textContent).toContain("1 game");
    cleanup();
    at("/play/does-not-exist");
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Page not found");
    cleanup();
    at("/c/casino");
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Page not found");
  });

  it("le pagine legali sono marcate come bozza", () => {
    at("/privacy");
    expect(screen.getByText(/under legal review/)).toBeTruthy();
  });
});

describe("navigazione", () => {
  it("non va in crash se scrollTo restituisce una Promise (Chromium recente)", async () => {
    window.scrollTo = vi.fn(() => Promise.resolve()) as unknown as typeof window.scrollTo;
    at("/");
    fireEvent.click(screen.getByRole("link", { name: "Favorites" }));
    expect((await screen.findByRole("heading", { level: 1 })).textContent).toBe("Favorites");
    fireEvent.click(screen.getByRole("link", { name: "Games" }));
    expect((await screen.findByRole("heading", { level: 1 })).textContent).toContain("Classic games");
  });
});
