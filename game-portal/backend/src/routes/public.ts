import { Hono } from "hono";
import type { AppEnv } from "../env";
import { CATALOG, findGame } from "../catalog";
import { SEMVER_RE, readJson, today } from "../util";

export const publicRoutes = new Hono<AppEnv>();

publicRoutes.get("/health", (c) => c.json({ ok: true }));

publicRoutes.get("/games", (c) => {
  c.header("Cache-Control", "public, max-age=300");
  return c.json({ games: CATALOG });
});

/** Kill switch: il player chiede lo stato prima di caricare l'iframe. */
publicRoutes.get("/games/:slug/status", async (c) => {
  const slug = c.req.param("slug");
  if (!findGame(slug)) return c.json({ error: "not_found" }, 404);
  const row = await c.env.DB.prepare("SELECT status, reason FROM game_status WHERE slug = ?")
    .bind(slug)
    .first<{ status: string; reason: string }>();
  c.header("Cache-Control", "no-store");
  const suspended = row?.status === "suspended";
  return c.json({ slug, playable: !suspended, reason: suspended ? row?.reason ?? "" : "" });
});

/** Evento di sessione aggregato: nessun identificativo, solo contatori giornalieri. */
publicRoutes.post("/events", async (c) => {
  const body = (await readJson(c.req.raw, 1024)) as Record<string, unknown> | undefined;
  if (!body || typeof body !== "object") return c.json({ error: "invalid_body" }, 400);
  const { slug, version, seconds, completed, won, error } = body;
  if (typeof slug !== "string" || !findGame(slug)) return c.json({ error: "unknown_game" }, 400);
  if (typeof version !== "string" || !SEMVER_RE.test(version)) return c.json({ error: "invalid_version" }, 400);
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds < 0 || seconds > 86_400)
    return c.json({ error: "invalid_seconds" }, 400);
  for (const flag of [completed, won, error]) {
    if (flag !== undefined && typeof flag !== "boolean") return c.json({ error: "invalid_flag" }, 400);
  }
  await c.env.DB.prepare(
    `INSERT INTO events_daily (day, slug, version, sessions, completions, wins, total_seconds, errors)
     VALUES (?, ?, ?, 1, ?, ?, ?, ?)
     ON CONFLICT (day, slug, version) DO UPDATE SET
       sessions = sessions + 1,
       completions = completions + excluded.completions,
       wins = wins + excluded.wins,
       total_seconds = total_seconds + excluded.total_seconds,
       errors = errors + excluded.errors`,
  )
    .bind(today(), slug, version, completed ? 1 : 0, won ? 1 : 0, Math.round(seconds), error ? 1 : 0)
    .run();
  return c.body(null, 204);
});
