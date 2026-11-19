import { beforeEach, describe, expect, it } from "vitest";
import { app } from "../src/index";
import type { Env } from "../src/env";
import { today } from "../src/util";
import { createTestDb } from "./d1-shim";

const TOKEN = "t".repeat(40);
let env: Env;

beforeEach(() => {
  env = { DB: createTestDb(), ADMIN_TOKEN: TOKEN, AD_NETWORK: "off" };
});

const req = (path: string, init: RequestInit = {}) => app.request(path, init, env);
const json = (body: unknown, extra: Record<string, string> = {}): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json", ...extra },
  body: JSON.stringify(body),
});
const admin = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
  ...(body === undefined ? {} : { body: JSON.stringify(body) }),
});

describe("API pubblica", () => {
  it("health e header di sicurezza", async () => {
    const r = await req("/api/v1/health");
    expect(r.status).toBe(200);
    expect(r.headers.get("x-content-type-options")).toBe("nosniff");
    expect(r.headers.get("content-security-policy")).toContain("default-src 'none'");
    expect(r.headers.get("x-frame-options")).toBe("DENY");
  });

  it("elenca i giochi del catalogo generato", async () => {
    const r = await req("/api/v1/games");
    const body = (await r.json()) as { games: { slug: string }[] };
    expect(body.games.map((g) => g.slug)).toEqual(expect.arrayContaining(["mines", "sudoku", "nonogram"]));
  });

  it("stato di gioco: giocabile di default, 404 se sconosciuto", async () => {
    expect(await (await req("/api/v1/games/mines/status")).json()).toEqual({ slug: "mines", playable: true, reason: "" });
    expect((await req("/api/v1/games/unknown/status")).status).toBe(404);
  });

  it("aggrega gli eventi di sessione senza identificativi", async () => {
    for (const won of [true, false]) {
      const r = await req("/api/v1/events", json({ slug: "mines", version: "1.0.0", seconds: 30.4, completed: true, won }));
      expect(r.status).toBe(204);
    }
    const s = await req(`/admin-api/stats/daily?from=${today()}&to=${today()}`, admin("GET"));
    const { rows } = (await s.json()) as { rows: Record<string, unknown>[] };
    expect(rows).toEqual([
      { day: today(), slug: "mines", sessions: 2, completions: 2, wins: 1, total_seconds: 60, errors: 0 },
    ]);
  });

  it("rifiuta eventi non validi", async () => {
    const bad = [
      { slug: "nope", version: "1.0.0", seconds: 1 },
      { slug: "mines", version: "x", seconds: 1 },
      { slug: "mines", version: "1.0.0", seconds: -5 },
      { slug: "mines", version: "1.0.0", seconds: 1, won: "yes" },
    ];
    for (const b of bad) expect((await req("/api/v1/events", json(b))).status).toBe(400);
    expect((await req("/api/v1/events", { method: "POST", body: "not json" })).status).toBe(400);
    expect((await req("/api/v1/events", json({ pad: "x".repeat(5000) }))).status).toBe(400);
  });
});

describe("autenticazione admin", () => {
  it("nega senza token o con token errato", async () => {
    expect((await req("/admin-api/audit")).status).toBe(401);
    expect((await req("/admin-api/audit", { headers: { Authorization: "Bearer wrong" } })).status).toBe(401);
  });
  it("disabilita l'admin se il token manca o è corto", async () => {
    env.ADMIN_TOKEN = "short";
    expect((await req("/admin-api/audit", admin("GET"))).status).toBe(503);
    env.ADMIN_TOKEN = undefined;
    expect((await req("/admin-api/audit", admin("GET"))).status).toBe(503);
  });
});

describe("kill switch", () => {
  it("sospende e ripristina un gioco con audit", async () => {
    expect((await req("/admin-api/games/mines/suspend", admin("POST", {}))).status).toBe(400);
    expect((await req("/admin-api/games/mines/suspend", admin("POST", { reason: "segnalazione diritti" }))).status).toBe(200);
    expect(await (await req("/api/v1/games/mines/status")).json()).toEqual({
      slug: "mines",
      playable: false,
      reason: "segnalazione diritti",
    });
    expect((await req("/admin-api/games/mines/restore", admin("POST"))).status).toBe(200);
    expect(((await (await req("/api/v1/games/mines/status")).json()) as { playable: boolean }).playable).toBe(true);
    const { rows } = (await (await req("/admin-api/audit", admin("GET"))).json()) as { rows: { action: string }[] };
    expect(rows.map((r) => r.action)).toEqual(["game.restore", "game.suspend"]);
    expect((await req("/admin-api/games/unknown/suspend", admin("POST", { reason: "x" }))).status).toBe(404);
  });
});

async function setupCampaign(overrides: Record<string, unknown> = {}) {
  const adv = (await (await req("/admin-api/advertisers", admin("POST", { name: "Acme" }))).json()) as { id: number };
  const camp = (await (
    await req(
      "/admin-api/campaigns",
      admin("POST", { advertiserId: adv.id, name: "Autunno", kind: "direct", startDate: "2020-01-01", endDate: "2099-12-31", ...overrides }),
    )
  ).json()) as { id: number };
  const cr = (await (
    await req(
      "/admin-api/creatives",
      admin("POST", {
        campaignId: camp.id,
        placement: "home-top",
        imagePath: "/ads/acme-autunno.webp",
        altText: "Acme autumn sale",
        clickUrl: "https://example.com/acme",
        width: 728,
        height: 90,
      }),
    )
  ).json()) as { id: number };
  return { campaignId: camp.id, creativeId: cr.id };
}

describe("ad server", () => {
  it("nessuna campagna: slot vuoto o rete se abilitata", async () => {
    expect(await (await req("/api/v1/ads/slot/home-top")).json()).toEqual({ source: "none" });
    env.AD_NETWORK = "on";
    expect(await (await req("/api/v1/ads/slot/home-top")).json()).toEqual({ source: "network" });
  });

  it("serve solo creatività approvate di campagne attive", async () => {
    const { campaignId, creativeId } = await setupCampaign();
    expect(((await (await req("/api/v1/ads/slot/home-top")).json()) as { source: string }).source).toBe("none");
    await req(`/admin-api/creatives/${creativeId}/approve`, admin("POST"));
    expect(((await (await req("/api/v1/ads/slot/home-top")).json()) as { source: string }).source).toBe("none");
    await req(`/admin-api/campaigns/${campaignId}`, admin("PATCH", { status: "active" }));
    const slot = (await (await req("/api/v1/ads/slot/home-top")).json()) as Record<string, unknown>;
    expect(slot).toMatchObject({ source: "direct", creativeId, href: `/r/${creativeId}`, width: 728 });
  });

  it("conta impression e clic e produce il report", async () => {
    const { campaignId, creativeId } = await setupCampaign();
    await req(`/admin-api/creatives/${creativeId}/approve`, admin("POST"));
    await req(`/admin-api/campaigns/${campaignId}`, admin("PATCH", { status: "active" }));
    const items = [{ creativeId, placement: "home-top" }, { creativeId, placement: "home-top" }, { creativeId: 999, placement: "home-top" }];
    expect((await req("/api/v1/ads/impressions", json({ items }))).status).toBe(204);
    const click = await req(`/r/${creativeId}`, { redirect: "manual" });
    expect(click.status).toBe(302);
    expect(click.headers.get("location")).toBe("https://example.com/acme");
    const rep = (await (await req(`/admin-api/campaigns/${campaignId}/report`, admin("GET"))).json()) as {
      totals: { impressions: number; clicks: number };
      ctr: number;
    };
    expect(rep.totals).toEqual({ impressions: 2, clicks: 1 });
    expect(rep.ctr).toBe(0.5);
  });

  it("rispetta il tetto di impression", async () => {
    const { campaignId, creativeId } = await setupCampaign({ impressionCap: 1 });
    await req(`/admin-api/creatives/${creativeId}/approve`, admin("POST"));
    await req(`/admin-api/campaigns/${campaignId}`, admin("PATCH", { status: "active" }));
    await req("/api/v1/ads/impressions", json({ items: [{ creativeId, placement: "home-top" }] }));
    expect(((await (await req("/api/v1/ads/slot/home-top")).json()) as { source: string }).source).toBe("none");
  });

  it("rifiuta creatività con URL o immagini non sicuri", async () => {
    const adv = (await (await req("/admin-api/advertisers", admin("POST", { name: "Evil" }))).json()) as { id: number };
    const camp = (await (
      await req("/admin-api/campaigns", admin("POST", { advertiserId: adv.id, name: "X", kind: "direct", startDate: "2026-01-01", endDate: "2026-12-31" }))
    ).json()) as { id: number };
    const base = { campaignId: camp.id, placement: "home-top", altText: "x", width: 10, height: 10 };
    for (const bad of [
      { ...base, imagePath: "/ads/a.png", clickUrl: "javascript:alert(1)" },
      { ...base, imagePath: "/ads/a.png", clickUrl: "http://example.com" },
      { ...base, imagePath: "/ads/a.svg", clickUrl: "https://example.com" },
      { ...base, imagePath: "https://cdn.evil/a.png", clickUrl: "https://example.com" },
    ]) {
      expect((await req("/admin-api/creatives", admin("POST", bad))).status).toBe(400);
    }
  });

  it("valida le campagne e i batch di impression", async () => {
    const r = await req("/admin-api/campaigns", admin("POST", { advertiserId: 1, name: "", kind: "x", startDate: "2026-02-01", endDate: "2026-01-01" }));
    expect(r.status).toBe(400);
    expect((await req("/api/v1/ads/impressions", json({ items: [] }))).status).toBe(400);
    expect((await req("/api/v1/ads/impressions", json({ items: Array(21).fill({ creativeId: 1, placement: "a" }) }))).status).toBe(400);
    expect((await req("/api/v1/ads/slot/BAD!")).status).toBe(400);
  });

  it("il redirect di un clic sconosciuto torna alla home", async () => {
    const r = await req("/r/12345", { redirect: "manual" });
    expect(r.headers.get("location")).toBe("/");
  });
});

it("404 JSON per rotte sconosciute", async () => {
  const r = await req("/nope");
  expect(r.status).toBe(404);
  expect(await r.json()).toEqual({ error: "not_found" });
});
