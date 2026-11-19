import { Hono } from "hono";
import { CATEGORIES } from "@tabluo/shared";
import type { AppEnv } from "../env";
import { PLACEMENT_RE, isSafeHttpsUrl, readJson, today } from "../util";

/**
 * Ad serving diretto. Ordine: sponsor -> diretta -> rete (se AD_NETWORK=on) -> nessuno.
 * Nessun cookie, nessun identificativo: la frequenza è limitata lato client per sessione.
 */
export const adRoutes = new Hono<AppEnv>();

interface SlotRow {
  creative_id: number;
  kind: "direct" | "sponsor";
  image_path: string;
  alt_text: string;
  width: number;
  height: number;
}

const ACTIVE_CREATIVE_SQL = `
  SELECT cr.id AS creative_id, ca.kind, cr.image_path, cr.alt_text, cr.width, cr.height
  FROM creatives cr
  JOIN campaigns ca ON ca.id = cr.campaign_id
  WHERE cr.placement = ?1 AND cr.approved = 1 AND ca.status = 'active'
    AND ca.start_date <= ?2 AND ca.end_date >= ?2
    AND (ca.category IS NULL OR ca.category = ?3)
    AND (ca.impression_cap IS NULL OR ca.impression_cap > (
      SELECT COALESCE(SUM(s.impressions), 0) FROM ad_daily_stats s
      JOIN creatives c2 ON c2.id = s.creative_id WHERE c2.campaign_id = ca.id))
  ORDER BY CASE ca.kind WHEN 'sponsor' THEN 0 ELSE 1 END, ca.priority DESC, cr.id
  LIMIT 1`;

adRoutes.get("/slot/:placement", async (c) => {
  const placement = c.req.param("placement");
  if (!PLACEMENT_RE.test(placement)) return c.json({ error: "invalid_placement" }, 400);
  const cat = c.req.query("category");
  const category = cat && (CATEGORIES as readonly string[]).includes(cat) ? cat : null;
  c.header("Cache-Control", "no-store");
  const row = await c.env.DB.prepare(ACTIVE_CREATIVE_SQL).bind(placement, today(), category).first<SlotRow>();
  if (row) {
    return c.json({
      source: row.kind,
      creativeId: row.creative_id,
      image: row.image_path,
      alt: row.alt_text,
      width: row.width,
      height: row.height,
      href: `/r/${row.creative_id}`,
    });
  }
  return c.json({ source: c.env.AD_NETWORK === "on" ? "network" : "none" });
});

/** Batch di impression viste (>= 50% per >= 1 s, misurate dal client). La fonte viene dal DB, non dal client. */
adRoutes.post("/impressions", async (c) => {
  const body = (await readJson(c.req.raw, 4096)) as { items?: unknown } | undefined;
  const items = body?.items;
  if (!Array.isArray(items) || items.length === 0 || items.length > 20) return c.json({ error: "invalid_body" }, 400);
  const day = today();
  const stmts: D1PreparedStatement[] = [];
  for (const it of items) {
    const { creativeId, placement } = (it ?? {}) as Record<string, unknown>;
    if (!Number.isInteger(creativeId) || typeof placement !== "string" || !PLACEMENT_RE.test(placement))
      return c.json({ error: "invalid_item" }, 400);
    stmts.push(
      c.env.DB.prepare(
        `INSERT INTO ad_daily_stats (day, creative_id, placement, source, impressions, clicks)
         SELECT ?1, cr.id, ?2, ca.kind, 1, 0 FROM creatives cr JOIN campaigns ca ON ca.id = cr.campaign_id
         WHERE cr.id = ?3 AND cr.placement = ?2 AND cr.approved = 1
         ON CONFLICT (day, creative_id, placement, source) DO UPDATE SET impressions = impressions + 1`,
      ).bind(day, placement, creativeId),
    );
  }
  await c.env.DB.batch(stmts);
  return c.body(null, 204);
});

/** Redirect di clic: conta e reindirizza solo a URL https approvati. */
export const clickRoute = new Hono<AppEnv>();
clickRoute.get("/:id", async (c) => {
  const id = Number(c.req.param("id"));
  if (!Number.isInteger(id) || id <= 0) return c.redirect("/", 302);
  const row = await c.env.DB.prepare(
    `SELECT cr.click_url, cr.placement, ca.kind FROM creatives cr JOIN campaigns ca ON ca.id = cr.campaign_id
     WHERE cr.id = ? AND cr.approved = 1 AND ca.status = 'active'`,
  )
    .bind(id)
    .first<{ click_url: string; placement: string; kind: string }>();
  if (!row || !isSafeHttpsUrl(row.click_url)) return c.redirect("/", 302);
  await c.env.DB.prepare(
    `INSERT INTO ad_daily_stats (day, creative_id, placement, source, impressions, clicks) VALUES (?, ?, ?, ?, 0, 1)
     ON CONFLICT (day, creative_id, placement, source) DO UPDATE SET clicks = clicks + 1`,
  )
    .bind(today(), id, row.placement, row.kind)
    .run();
  c.header("Referrer-Policy", "no-referrer");
  return c.redirect(row.click_url, 302);
});
