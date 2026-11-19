// Rende un gruppo di card in un solo processo (il bundle si costruisce una volta sola).
// Uso: node render.mjs jobs.json   — jobs.json = {"publicDir": "...", "jobs": [{"out": "...mp4", "props": {...}}]}
// Stampa una riga JSON per card: {"out": ..., "ok": true|false, "error": ...}
import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition } from "@remotion/renderer";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const { publicDir, jobs } = JSON.parse(readFileSync(process.argv[2], "utf8"));
const browserExecutable = process.env.YTF_CHROME || null;
const serveUrl = await bundle({ entryPoint: path.join(here, "src/index.ts"), publicDir });

for (const job of jobs) {
  try {
    const composition = await selectComposition({ serveUrl, id: "Card", inputProps: job.props, browserExecutable });
    await renderMedia({
      composition,
      serveUrl,
      codec: "h264",
      outputLocation: job.out,
      inputProps: job.props,
      browserExecutable,
      crf: 20,
      muted: true,
      concurrency: Number(process.env.YTF_MOTION_CONCURRENCY || 2),
      chromiumOptions: { gl: "swangle" },
    });
    console.log(JSON.stringify({ out: job.out, ok: true }));
  } catch (e) {
    console.log(JSON.stringify({ out: job.out, ok: false, error: String(e?.message || e).slice(0, 300) }));
  }
}
