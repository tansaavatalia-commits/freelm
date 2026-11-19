// Test end-to-end in un browser reale (Chromium via Playwright preinstallato).
// Prerequisiti: API su :8787 (wrangler dev --local), giochi su :5174, portale su :4173.
// Uso: ADMIN_TOKEN=... node tests/e2e/smoke.mjs
import { createRequire } from "node:module";
import { strict as assert } from "node:assert";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const WEB = process.env.WEB ?? "http://127.0.0.1:4173";
const API = process.env.API ?? "http://127.0.0.1:8787";
const TOKEN = process.env.ADMIN_TOKEN ?? "";
const GAMES_ORIGIN = "http://localhost:5174";
assert.ok(TOKEN.length >= 32, "ADMIN_TOKEN mancante");

const results = [];
async function step(name, fn) {
  try {
    await fn();
    results.push(["PASS", name]);
  } catch (e) {
    results.push(["FAIL", name, e.message.split("\n")[0]]);
  }
}
const adminFetch = (path, init = {}) =>
  fetch(`${API}${path}`, { ...init, headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json", ...init.headers } });
const sessions = async (slug) => {
  const day = new Date().toISOString().slice(0, 10);
  const { rows } = await (await adminFetch(`/admin-api/stats/daily?from=${day}&to=${day}`)).json();
  return rows.filter((r) => r.slug === slug).reduce((n, r) => n + r.sessions, 0);
};

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
page.on("console", (m) => { if (m.type() === "error") errors.push(`console: ${m.text()}`); });

await step("home: mostra i 3 giochi", async () => {
  await page.goto(WEB);
  await page.getByRole("heading", { level: 1 }).waitFor();
  const cards = await page.locator(".card").count();
  assert.equal(cards, 3);
});

await step("pagina gioco: il gioco invia 'ready' e il portale lo accetta", async () => {
  await page.goto(`${WEB}/play/mines`);
  const iframe = page.locator('iframe[title="Mines game"]');
  await iframe.waitFor();
  assert.equal(await iframe.getAttribute("sandbox"), "allow-scripts allow-same-origin");
  await page.locator(".player-overlay").waitFor({ state: "detached", timeout: 10000 });
});

await step("il gioco funziona dentro l'iframe", async () => {
  const frame = page.frameLocator('iframe[title="Mines game"]');
  await frame.locator("#board button").nth(40).click();
  const opened = await frame.locator("#board button.open").count();
  assert.ok(opened > 1, `celle aperte: ${opened}`);
});

await step("isolamento: il gioco non può leggere DOM o cookie del portale", async () => {
  const f = page.frames().find((x) => x.url().startsWith(GAMES_ORIGIN));
  assert.ok(f, "frame del gioco non trovato");
  const blocked = await f.evaluate(() => {
    try { void window.parent.document.cookie; return false; } catch { return true; }
  });
  assert.equal(blocked, true);
  const nav = await f.evaluate(() => {
    try { window.top.location.href = "https://example.com"; return "navigated"; } catch { return "blocked"; }
  });
  assert.equal(nav, "blocked");
  // Il browser registra in console il blocco della navigazione: è l'esito atteso di questo test.
  await page.waitForTimeout(200);
  for (let i = errors.length - 1; i >= 0; i--) if (errors[i].includes("Unsafe attempt to initiate navigation")) errors.splice(i, 1);
  assert.equal(page.url().startsWith(WEB), true, "il portale non deve essere stato navigato via");
});

await step("evento 'complete' dal gioco registrato in D1 (aggregato)", async () => {
  const before = await sessions("mines");
  const f = page.frames().find((x) => x.url().startsWith(GAMES_ORIGIN));
  await f.evaluate(() => window.parent.postMessage({ protocol: "tabluo/1", type: "complete", won: true, seconds: 42 }, "*"));
  let after = before;
  for (let i = 0; i < 20 && after === before; i++) { await page.waitForTimeout(150); after = await sessions("mines"); }
  assert.equal(after, before + 1);
});

await step("messaggi falsificati dalla pagina stessa vengono ignorati", async () => {
  const before = await sessions("mines");
  await page.evaluate(() => window.postMessage({ protocol: "tabluo/1", type: "complete", won: true, seconds: 1 }, "*"));
  await page.waitForTimeout(800);
  assert.equal(await sessions("mines"), before);
});

await step("kill switch: gioco sospeso non viene caricato", async () => {
  const r = await adminFetch("/admin-api/games/sudoku/suspend", { method: "POST", body: JSON.stringify({ reason: "E2E test" }) });
  assert.equal(r.status, 200);
  await page.goto(`${WEB}/play/sudoku`);
  await page.getByRole("alert").waitFor();
  assert.equal(await page.locator("iframe").count(), 0);
  const back = await adminFetch("/admin-api/games/sudoku/restore", { method: "POST" });
  assert.equal(back.status, 200);
  await page.reload();
  await page.locator('iframe[title="Sudoku game"]').waitFor();
});

await step("sudoku e nonogram si caricano e rispondono", async () => {
  for (const slug of ["sudoku", "nonogram"]) {
    await page.goto(`${WEB}/play/${slug}`);
    await page.locator(".player-overlay").waitFor({ state: "detached", timeout: 10000 });
  }
  const frame = page.frameLocator('iframe[title="Nonogram game"]');
  await frame.locator("#board td button").first().click();
  assert.equal(await frame.locator("#board td button.fill").count(), 1);
});

await step("preferiti salvati localmente e mostrati", async () => {
  await page.goto(`${WEB}/play/nonogram`);
  await page.getByRole("button", { name: "☆ Save" }).click();
  await page.goto(`${WEB}/favorites`);
  assert.equal(await page.locator(".card").count(), 1);
});

await step("ricerca dal campo nell'header", async () => {
  await page.goto(WEB);
  await page.getByPlaceholder("Search games").fill("sudoku");
  await page.keyboard.press("Enter");
  await page.waitForURL(/\/search\?q=sudoku/);
  await page.getByRole("status").filter({ hasText: "for “sudoku”" }).waitFor();
  assert.equal(await page.locator(".card").count(), 1);
});

await step("mobile: nessuno scroll orizzontale (home e gioco)", async () => {
  const m = await browser.newContext({ viewport: { width: 360, height: 740 }, isMobile: true, hasTouch: true });
  const p = await m.newPage();
  for (const path of ["/", "/play/mines", "/play/sudoku"]) {
    await p.goto(`${WEB}${path}`);
    await p.waitForTimeout(400);
    const over = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    assert.ok(over <= 0, `${path}: overflow ${over}px`);
  }
  await m.close();
});

await step("nessun errore JavaScript nella console", async () => {
  if (errors.length) console.error(errors.join("\n"));
  assert.deepEqual(errors, []);
});

await browser.close();
for (const r of results) console.log(r.join("  "));
const failed = results.filter((r) => r[0] === "FAIL").length;
console.log(`\n${results.length - failed}/${results.length} passati`);
process.exit(failed ? 1 : 0);
