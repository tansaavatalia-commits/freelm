import { Hono } from "hono";
import type { AppEnv } from "./env";
import { adRoutes, clickRoute } from "./routes/ads";
import { adminRoutes } from "./routes/admin";
import { publicRoutes } from "./routes/public";

export const app = new Hono<AppEnv>();

// Header di sicurezza per tutte le risposte API.
app.use("*", async (c, next) => {
  await next();
  c.header("X-Content-Type-Options", "nosniff");
  c.header("X-Frame-Options", "DENY");
  c.header("Referrer-Policy", c.res.headers.get("Referrer-Policy") ?? "strict-origin-when-cross-origin");
  c.header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'");
  c.header("Cross-Origin-Resource-Policy", "same-origin");
});

app.route("/api/v1", publicRoutes);
app.route("/api/v1/ads", adRoutes);
app.route("/r", clickRoute);
app.route("/admin-api", adminRoutes);

app.notFound((c) => c.json({ error: "not_found" }, 404));
app.onError((err, c) => {
  console.error("unhandled", err instanceof Error ? err.message : String(err));
  return c.json({ error: "internal_error" }, 500);
});

export default app;
