// Test dello script di catalogo: la regola bloccante delle licenze deve fermare la build.
import { strict as assert } from "node:assert";
import { spawnSync } from "node:child_process";
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, test } from "node:test";

const root = join(import.meta.dirname, "..");
const script = join(root, "scripts/build-catalog.ts");
const tmp = mkdtempSync(join(tmpdir(), "tabluo-catalog-"));
after(() => rmSync(tmp, { recursive: true, force: true }));

function fixture(name: string, edit?: (dir: string) => void): string {
  const games = join(tmp, name, "games");
  cpSync(join(root, "games/mines"), join(games, "mines"), { recursive: true });
  edit?.(join(games, "mines"));
  return games;
}

function run(games: string, today = "2026-11-19") {
  const out = join(games, "..", "out");
  const r = spawnSync(process.execPath, [script, "--games", games, "--out", out, "--today", today], { encoding: "utf8" });
  return { ...r, out };
}

test("genera il catalogo per un gioco con licenza approvata", () => {
  const r = run(fixture("ok"));
  assert.equal(r.status, 0, r.stderr);
  const cat = JSON.parse(readFileSync(join(r.out, "catalog.json"), "utf8"));
  assert.deepEqual(cat.map((g: { slug: string }) => g.slug), ["mines"]);
  assert.equal("license" in cat[0], false, "il catalogo pubblico non espone i dati di licenza");
});

test("blocca un gioco senza license.json", () => {
  const r = run(fixture("nolicense", (d) => rmSync(join(d, "license.json"))));
  assert.equal(r.status, 1);
  assert.match(r.stderr, /nessuna licenza registrata/);
});

test("blocca una licenza non approvata", () => {
  const r = run(
    fixture("review", (d) => {
      const lic = JSON.parse(readFileSync(join(d, "license.json"), "utf8"));
      writeFileSync(join(d, "license.json"), JSON.stringify({ ...lic, approvalStatus: "under_review" }));
    }),
  );
  assert.equal(r.status, 1);
  assert.match(r.stderr, /under_review/);
});

test("blocca una licenza scaduta e avvisa per quelle in scadenza", () => {
  const games = fixture("expiry", (d) => {
    const lic = JSON.parse(readFileSync(join(d, "license.json"), "utf8"));
    writeFileSync(join(d, "license.json"), JSON.stringify({ ...lic, endDate: "2026-12-01" }));
  });
  const soon = run(games, "2026-11-19");
  assert.equal(soon.status, 0);
  assert.match(soon.stderr, /in scadenza tra 12 giorni/);
  const expired = run(games, "2026-12-02");
  assert.equal(expired.status, 1);
  assert.match(expired.stderr, /scaduta/);
});

test("blocca un gioco di terzi che usa lo storage", () => {
  const r = run(
    fixture("thirdparty", (d) => {
      const m = JSON.parse(readFileSync(join(d, "manifest.json"), "utf8"));
      m.license = { type: "open_source", spdx: "MIT", rightsHolder: "Someone", thirdPartyAssets: [] };
      writeFileSync(join(d, "manifest.json"), JSON.stringify(m));
    }),
  );
  assert.equal(r.status, 1);
  assert.match(r.stderr, /non possono usare storage/);
});

test("blocca manifest non valido e slug diverso dalla cartella", () => {
  const r = run(
    fixture("badmanifest", (d) => {
      const m = JSON.parse(readFileSync(join(d, "manifest.json"), "utf8"));
      writeFileSync(join(d, "manifest.json"), JSON.stringify({ ...m, slug: "other", category: "casino" }));
    }),
  );
  assert.equal(r.status, 1);
  assert.match(r.stderr, /category/);
});
