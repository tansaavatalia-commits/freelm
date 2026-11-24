// End-to-end check of the real interface in a real browser.
// Usage: node e2e/smoke.cjs <python> <empty-home-dir> [screenshot-dir]
// Starts `genesis serve` on a free port, drives the UI, fails on any browser error (CSP included).
const { spawn } = require("node:child_process");
const path = require("node:path");
const { chromium } = require("playwright");

const [python, home, shots] = process.argv.slice(2);
if (!python || !home) {
  console.error("usage: node e2e/smoke.cjs <python> <empty-home-dir> [screenshot-dir]");
  process.exit(2);
}
const genesisRoot = path.resolve(__dirname, "../../..");

function startServer() {
  return new Promise((resolve, reject) => {
    const proc = spawn(python, ["-m", "genesis", "--home", home, "serve", "--port", "0", "--no-browser"], {
      cwd: genesisRoot,
      env: { ...process.env, PYTHONIOENCODING: "utf-8" },
    });
    let out = "";
    const timer = setTimeout(() => reject(new Error(`server did not start:\n${out}`)), 30000);
    proc.stdout.on("data", (chunk) => {
      out += chunk;
      const match = out.match(/http:\/\/127\.0\.0\.1:\d+\//);
      if (match) {
        clearTimeout(timer);
        resolve({ proc, url: match[0], output: () => out });
      }
    });
    proc.stderr.on("data", (chunk) => (out += chunk));
    proc.on("exit", (code) => reject(new Error(`server exited (${code}):\n${out}`)));
  });
}

async function main() {
  const server = await startServer();
  const browser = await chromium.launch();
  const problems = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 860 }, deviceScaleFactor: shots ? 2 : 1 });
    page.on("console", (msg) => msg.type() === "error" && problems.push(`console: ${msg.text()}`));
    page.on("pageerror", (err) => problems.push(`page: ${err.message}`));

    // Dashboard
    await page.goto(server.url);
    await page.getByRole("heading", { name: "GÉNESIS" }).waitFor();
    await page.getByText("Esecutore dei compiti attivo").waitFor();
    await page.getByText("GÉNESIS ora usa").waitFor();
    if (shots) await page.screenshot({ path: path.join(shots, "1-dashboard.png"), fullPage: true });

    // Projects: create one
    await page.getByRole("link", { name: "Progetti" }).click();
    await page.getByLabel("Nome").fill("Ricerca modelli aperti");
    await page.getByLabel("Descrizione (facoltativa)").fill("Primo progetto creato dall'interfaccia");
    await page.getByRole("button", { name: "Crea progetto" }).click();
    await page.getByRole("cell", { name: "Ricerca modelli aperti" }).waitFor();

    // Tasks: queue an echo task on that project and wait for the worker
    await page.getByRole("button", { name: "Compiti" }).click();
    await page.getByRole("heading", { name: "Compiti", level: 1 }).waitFor();
    await page.getByLabel("Tipo").selectOption("system.echo");
    await page.getByLabel("Dati in ingresso (JSON)").fill('{"messaggio": "ciao da GÉNESIS"}');
    await page.getByRole("button", { name: "Metti in coda" }).click();
    await page.locator("tbody .badge", { hasText: "Completato" }).first().waitFor({ timeout: 15000 });
    await page.getByRole("button", { name: "Dettagli" }).first().click();
    await page.getByText('"messaggio": "ciao da GÉNESIS"').first().waitFor();
    if (shots) await page.screenshot({ path: path.join(shots, "2-compiti.png"), fullPage: true });

    // Invalid JSON is caught in the form, nothing is sent
    await page.getByLabel("Dati in ingresso (JSON)").fill("{non valido");
    await page.getByRole("button", { name: "Metti in coda" }).click();
    await page.getByText("devono essere JSON valido").waitFor();

    // Dashboard: backup button queues a real backup task
    await page.getByRole("link", { name: "Dashboard", exact: true }).click();
    await page.getByRole("button", { name: "Crea un backup" }).click();
    await page.getByText("Backup messo in coda").waitFor();

    // Diagnostics: checks, audit chain, the backup just made
    await page.getByRole("link", { name: "Diagnostica" }).click();
    await page.getByText("Integrità del database").waitFor();
    await page.getByText(/Catena integra/).waitFor();
    await page.locator(".plain-list .mono", { hasText: /^genesis-.*\.db$/ }).first().waitFor({ timeout: 15000 });

    // Agents: the analyst solves a calculation locally
    await page.getByRole("link", { name: "Agenti", exact: true }).click();
    await page.getByLabel("Richiesta").fill("quanto fa 12*(3+4)?");
    await page.getByRole("button", { name: "Invia" }).click();
    await page.locator(".approval .badge", { hasText: "riuscita" }).first().waitFor({ timeout: 15000 });

    // Research Lab: baseline vs rule classifier, then a paired comparison with a statistical verdict
    await page.getByRole("link", { name: "Laboratorio", exact: true }).click();
    await page.getByLabel("Soggetto").selectOption("baseline:majority");
    await page.getByRole("button", { name: "Avvia esperimento" }).click();
    await page.getByText("in coda").first().waitFor();
    await page.getByLabel("Soggetto").selectOption("classifier");
    await page.getByRole("button", { name: "Avvia esperimento" }).click();
    await page.locator("tbody .badge", { hasText: "completato" }).nth(1).waitFor({ timeout: 20000 });
    const rows = page.locator("tbody tr").filter({ has: page.locator(".badge", { hasText: "completato" }) });
    await rows.filter({ hasText: "baseline:majority" }).first().getByRole("checkbox").check();
    await rows.filter({ hasText: /^.*classifier/ }).first().getByRole("checkbox").check();
    await page.getByRole("button", { name: "Confronta i 2 selezionati" }).click();
    await page.getByText(/B migliore di A: dimostrato/).waitFor();
    if (shots) await page.screenshot({ path: path.join(shots, "4-laboratorio.png"), fullPage: true });

    // Approvals page renders its empty state
    await page.getByRole("link", { name: "Approvazioni" }).click();
    await page.getByText("Nessuna richiesta in attesa.").waitFor();

    // Mobile width: no horizontal page scroll
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole("link", { name: "Dashboard", exact: true }).click();
    await page.getByRole("heading", { name: "GÉNESIS" }).waitFor();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    if (overflow > 1) problems.push(`horizontal overflow on mobile: ${overflow}px`);
    if (shots) await page.screenshot({ path: path.join(shots, "3-mobile.png"), fullPage: true });

    const status = await page.evaluate(async () => {
      const token = document.querySelector('meta[name="genesis-token"]').content;
      const r = await fetch("/api/status", { headers: { "X-Genesis-Token": token } });
      return r.json();
    });
    console.log(`server process RSS: ${status.memory.process_rss_mb} MB; tasks: ${JSON.stringify(status.tasks)}`);
  } finally {
    await browser.close();
    server.proc.kill("SIGINT");
    await new Promise((r) => server.proc.once("exit", r));
  }
  if (!/GÉNESIS è stato fermato/.test(server.output())) problems.push("server did not stop cleanly");
  if (problems.length) {
    console.error("E2E FAILED:\n" + problems.join("\n"));
    process.exit(1);
  }
  console.log("E2E OK: dashboard, progetti, compiti, agenti, laboratorio, backup, diagnostica, approvazioni, mobile, nessun errore nel browser");
}

main().catch((err) => {
  console.error("E2E FAILED:", err);
  process.exit(1);
});
