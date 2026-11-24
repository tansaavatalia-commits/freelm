import { defineConfig } from "vite";

// No React plugin: Vite's built-in esbuild compiles TSX (one dependency fewer).
// The build goes straight into the Python package, so `genesis serve` needs no Node.
export default defineConfig({
  base: "./",
  esbuild: { jsx: "automatic" },
  build: {
    outDir: "../../genesis/api/static",
    emptyOutDir: true,
    target: "es2020",
    sourcemap: false,
  },
  server: {
    // `npm run dev` against a running `genesis serve`; set VITE_GENESIS_TOKEN to the token in <home>/data/api_token.
    proxy: { "/api": { target: "http://127.0.0.1:8765", changeOrigin: true } },
  },
});
