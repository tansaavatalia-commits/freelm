import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    // In sviluppo l'API (wrangler dev) gira su 8787; stesso origin per il browser grazie al proxy.
    proxy: { "/api": "http://127.0.0.1:8787", "/r": "http://127.0.0.1:8787" },
  },
  preview: { proxy: { "/api": "http://127.0.0.1:8787", "/r": "http://127.0.0.1:8787" } },
  build: { target: "es2022", sourcemap: false },
  test: { environment: "jsdom", include: ["test/**/*.test.{ts,tsx}"] },
});
