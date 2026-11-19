import { resolve } from "node:path";
import { defineConfig } from "vite";

// Ogni gioco è una pagina statica indipendente, servita da un origin separato dal portale.
const GAMES = ["mines", "sudoku", "nonogram"];

export default defineConfig({
  base: "./",
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: { input: Object.fromEntries(GAMES.map((g) => [g, resolve(import.meta.dirname, g, "index.html")])) },
  },
  server: { headers: { "Cross-Origin-Resource-Policy": "cross-origin" } },
});
