// Screenshot del portale per la revisione visiva (desktop e telefono).
// Prerequisiti: server avviati come in scripts/e2e.sh. Uso: node scripts/screenshots.mjs [slug...]
import { createRequire } from "node:module";
import { join } from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const WEB = process.env.WEB ?? "http://127.0.0.1:4173";
const out = join(import.meta.dirname, "..", "docs", "screenshots");
const slugs = process.argv.slice(2).length ? process.argv.slice(2) : ["klondike"];
const devices = {
  desktop: { viewport: { width: 1280, height: 900 }, deviceScaleFactor: 2 },
  mobile: { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
};

const browser = await chromium.launch();
for (const slug of slugs) {
  for (const [name, opts] of Object.entries(devices)) {
    const ctx = await browser.newContext(opts);
    const page = await ctx.newPage();
    await page.goto(`${WEB}/play/${slug}`);
    await page.locator(".player-overlay").waitFor({ state: "detached", timeout: 10000 });
    await page.waitForTimeout(400);
    await page.screenshot({ path: join(out, `${slug}-${name}.png`) });
    await ctx.close();
  }
}
await browser.close();
console.log(`Screenshot salvati in ${out}`);
