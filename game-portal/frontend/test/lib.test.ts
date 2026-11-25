import { beforeEach, describe, expect, it } from "vitest";
import { PROTOCOL, type CatalogEntry } from "@tabluo/shared";
import { CATALOG, findGame, related } from "../src/lib/catalog";
import { acceptMessage, expectedOrigin, gameUrl, sandboxFor } from "../src/lib/player";
import { searchGames } from "../src/lib/search";
import { favorites, history } from "../src/lib/storage";

const g = (over: Partial<CatalogEntry>): CatalogEntry => ({
  slug: "x", title: "X", version: "1.0.0", category: "logic", tags: [], description: "", aspect: "1:1", usesStorage: false, ...over,
});

describe("player: isolamento", () => {
  it("non concede mai permessi pericolosi", () => {
    for (const s of [sandboxFor({ usesStorage: false }), sandboxFor({ usesStorage: true })]) {
      expect(s).not.toMatch(/top-navigation|popups|forms|modals|downloads/);
      expect(s).toContain("allow-scripts");
    }
    expect(sandboxFor({ usesStorage: false })).not.toContain("allow-same-origin");
  });
  it("origin atteso: quello dei giochi o 'null' per i sandbox opachi", () => {
    expect(expectedOrigin("https://play.example/", { usesStorage: true })).toBe("https://play.example");
    expect(expectedOrigin("https://play.example", { usesStorage: false })).toBe("null");
  });
  it("accetta solo messaggi dall'iframe corrente e dall'origin atteso", () => {
    const frame = {} as Window;
    const other = {} as Window;
    const data = { protocol: PROTOCOL, type: "ready" };
    expect(acceptMessage({ source: frame, origin: "https://play.example", data }, frame, "https://play.example")).toEqual(data);
    expect(acceptMessage({ source: other, origin: "https://play.example", data }, frame, "https://play.example")).toBeNull();
    expect(acceptMessage({ source: frame, origin: "https://evil.example", data }, frame, "https://play.example")).toBeNull();
    expect(acceptMessage({ source: frame, origin: "https://play.example", data: { type: "ready" } }, frame, "https://play.example")).toBeNull();
    expect(acceptMessage({ source: frame, origin: "https://play.example", data }, null, "https://play.example")).toBeNull();
  });
  it("costruisce URL di gioco codificati", () => {
    expect(gameUrl("https://play.example/", "mines")).toBe("https://play.example/mines/index.html");
    expect(gameUrl("https://play.example", "a/../b")).toBe("https://play.example/a%2F..%2Fb/index.html");
  });
});

describe("catalogo e ricerca", () => {
  it("il catalogo generato contiene i giochi pubblicabili", () => {
    expect(CATALOG.map((x) => x.slug).sort()).toEqual(["klondike", "mines", "nonogram", "sudoku"]);
    expect(findGame("mines")?.title).toBe("Mines");
    expect(findGame("nope")).toBeUndefined();
  });
  it("i correlati escludono il gioco stesso e privilegiano la categoria", () => {
    const mines = findGame("mines") as CatalogEntry;
    expect(related(mines).map((x) => x.slug)).not.toContain("mines");
    expect(related(mines)[0]?.category).toBe("logic");
  });
  it("cerca per titolo, tag e descrizione ignorando maiuscole e accenti", () => {
    const games = [g({ slug: "a", title: "Sudoku", tags: ["numbers"] }), g({ slug: "b", title: "Mines", description: "Évitez les mines" })];
    expect(searchGames(games, "SUDOKU").map((x) => x.slug)).toEqual(["a"]);
    expect(searchGames(games, "numbers").map((x) => x.slug)).toEqual(["a"]);
    expect(searchGames(games, "evitez").map((x) => x.slug)).toEqual(["b"]);
    expect(searchGames(games, "   ")).toEqual([]);
    expect(searchGames(games, "chess")).toEqual([]);
  });
});

describe("preferiti e cronologia locali", () => {
  beforeEach(() => window.localStorage.clear());
  it("aggiunge e rimuove preferiti", () => {
    expect(favorites.toggle("mines")).toBe(true);
    expect(favorites.has("mines")).toBe(true);
    expect(favorites.toggle("mines")).toBe(false);
    expect(favorites.list()).toEqual([]);
  });
  it("cronologia ordinata, senza duplicati e con limite", () => {
    for (let i = 0; i < 40; i++) history.add(`g${i}`);
    history.add("g5");
    const list = history.list();
    expect(list[0]).toBe("g5");
    expect(list).toHaveLength(30);
    expect(new Set(list).size).toBe(30);
  });
  it("tollera dati corrotti", () => {
    window.localStorage.setItem("tabluo.favorites", "{not json");
    expect(favorites.list()).toEqual([]);
    window.localStorage.setItem("tabluo.favorites", JSON.stringify([1, "mines", null]));
    expect(favorites.list()).toEqual(["mines"]);
  });
});
