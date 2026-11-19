// Genera il catalogo pubblicato da games/<slug>/{manifest,license}.json.
// Regola bloccante (docs/LICENSE_MANAGEMENT.md): un gioco entra nel catalogo SOLO se
// manifest valido + licenza approvata, non scaduta, con diritti di hosting e monetizzazione.
// Qualsiasi errore => exit 1 (la build si ferma). Licenze in scadenza <= 30 giorni => avviso.
// Uso: node scripts/build-catalog.ts [--today YYYY-MM-DD] [--games DIR] [--out DIR]
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  canPublish,
  daysToExpiry,
  toCatalogEntry,
  validateManifest,
  type CatalogEntry,
  type GameManifest,
  type LicenseRecord,
} from "../shared/src/index.ts";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const arg = (name: string): string | undefined => {
  const i = process.argv.indexOf(name);
  return i > 0 ? process.argv[i + 1] : undefined;
};
const gamesDir = arg("--games") ?? join(root, "games");
const outDirs = arg("--out") ? [arg("--out") as string] : [join(root, "frontend/src/generated"), join(root, "backend/src/generated")];
const today = arg("--today") ?? new Date().toISOString().slice(0, 10);
if (!/^\d{4}-\d{2}-\d{2}$/.test(today)) {
  console.error(`ERRORE  --today non valido: ${today}`);
  process.exit(2);
}
const SKIP = new Set(["sdk", "test", "dist", "node_modules", "public"]);

const errors: string[] = [];
const warnings: string[] = [];
const entries: CatalogEntry[] = [];

function readJson(path: string): unknown {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch (e) {
    errors.push(`${path}: JSON non leggibile (${(e as Error).message})`);
    return undefined;
  }
}

for (const dir of readdirSync(gamesDir, { withFileTypes: true })) {
  if (!dir.isDirectory() || SKIP.has(dir.name)) continue;
  const base = join(gamesDir, dir.name);
  if (!existsSync(join(base, "manifest.json"))) {
    errors.push(`${dir.name}: manca manifest.json`);
    continue;
  }
  const manifest = readJson(join(base, "manifest.json"));
  if (manifest === undefined) continue;
  const mErr = validateManifest(manifest);
  if (mErr.length) {
    errors.push(...mErr.map((e) => `${dir.name}/manifest.json: ${e}`));
    continue;
  }
  const m = manifest as GameManifest;
  if (m.slug !== dir.name) errors.push(`${dir.name}: lo slug "${m.slug}" deve coincidere con la cartella`);
  if (m.license.type !== "internal" && m.usesStorage)
    errors.push(`${dir.name}: i giochi di terzi non possono usare storage (sandbox senza allow-same-origin)`);
  if (!existsSync(join(base, "index.html"))) errors.push(`${dir.name}: manca index.html`);
  const lic = existsSync(join(base, "license.json")) ? (readJson(join(base, "license.json")) as LicenseRecord) : null;
  const check = canPublish(lic, today);
  if (!check.ok) {
    errors.push(...check.reasons.map((r) => `${dir.name}: NON pubblicabile — ${r}`));
    continue;
  }
  const days = lic ? daysToExpiry(lic, today) : null;
  if (days !== null && days <= 30) warnings.push(`${dir.name}: licenza in scadenza tra ${days} giorni`);
  entries.push(toCatalogEntry(m));
}

for (const w of warnings) console.warn(`AVVISO  ${w}`);
if (errors.length) {
  for (const e of errors) console.error(`ERRORE  ${e}`);
  console.error(`\nCatalogo NON generato: ${errors.length} errori.`);
  process.exit(1);
}

entries.sort((a, b) => a.title.localeCompare(b.title));
const json = `${JSON.stringify(entries, null, 2)}\n`;
for (const dir of outDirs) {
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, "catalog.json"), json);
}
console.log(`Catalogo: ${entries.length} giochi pubblicabili (${entries.map((e) => e.slug).join(", ")}) — data di controllo ${today}`);
