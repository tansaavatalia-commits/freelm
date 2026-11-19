import { Hono } from "hono";
import { CATEGORIES } from "@tabluo/shared";
import type { AppEnv } from "../env";
import { findGame } from "../catalog";
import { DATE_RE, PLACEMENT_RE, isSafeHttpsUrl, readJson, safeEqual } from "../util";

/**
 * API amministrativa. Autenticazione TEMPORANEA con Bearer token (>= 32 caratteri);
 * da sostituire con passkey + MFA su origin separato (FASE 7). Deny-by-default.
 */
export const adminRoutes = new Hono<AppEnv & { Variables: { actor: string } }>();

adminRoutes.use("*", async (c, next) => {
  const token = c.env.ADMIN_TOKEN;
  if (!token || token.length < 32) return c.json({ error: "admin_disabled" }, 503);
  const header = c.req.header("Authorization") ?? "";
  const given = header.startsWith("Bearer ") ? header.slice(7) : "";
  if (!(await safeEqual(given, token))) return c.json({ error: "unauthorized" }, 401);
  c.set("actor", "admin-token");
  c.header("Cache-Control", "no-store");
  await next();
});

async function audit(db: D1Database, actor: string, action: string, entity: string, detail = "") {
  await db
    .prepare("INSERT INTO audit_log (at, actor, action, entity, detail) VALUES (?, ?, ?, ?, ?)")
    .bind(new Date().toISOString(), actor, action, entity, detail.slice(0, 500))
    .run();
}

async function setStatus(db: D1Database, slug: string, status: "active" | "suspended", reason: string) {
  await db
    .prepare(
      `INSERT INTO game_status (slug, status, reason, updated_at) VALUES (?, ?, ?, ?)
       ON CONFLICT (slug) DO UPDATE SET status = excluded.status, reason = excluded.reason, updated_at = excluded.updated_at`,
    )
    .bind(slug, status, reason, new Date().toISOString())
    .run();
}

/** Sospensione immediata (sicurezza o diritti). Effetto: il player non carica più il gioco. */
adminRoutes.post("/games/:slug/suspend", async (c) => {
  const slug = c.req.param("slug");
  if (!findGame(slug)) return c.json({ error: "not_found" }, 404);
  const body = (await readJson(c.req.raw, 1024)) as { reason?: unknown } | undefined;
  const reason = typeof body?.reason === "string" ? body.reason.trim().slice(0, 300) : "";
  if (reason === "") return c.json({ error: "reason_required" }, 400);
  await setStatus(c.env.DB, slug, "suspended", reason);
  await audit(c.env.DB, c.get("actor"), "game.suspend", slug, reason);
  return c.json({ slug, status: "suspended" });
});

adminRoutes.post("/games/:slug/restore", async (c) => {
  const slug = c.req.param("slug");
  if (!findGame(slug)) return c.json({ error: "not_found" }, 404);
  await setStatus(c.env.DB, slug, "active", "");
  await audit(c.env.DB, c.get("actor"), "game.restore", slug);
  return c.json({ slug, status: "active" });
});

adminRoutes.get("/stats/daily", async (c) => {
  const from = c.req.query("from") ?? "0000-01-01";
  const to = c.req.query("to") ?? "9999-12-31";
  if (!DATE_RE.test(from) || !DATE_RE.test(to)) return c.json({ error: "invalid_date" }, 400);
  const { results } = await c.env.DB.prepare(
    `SELECT day, slug, SUM(sessions) AS sessions, SUM(completions) AS completions, SUM(wins) AS wins,
            SUM(total_seconds) AS total_seconds, SUM(errors) AS errors
     FROM events_daily WHERE day BETWEEN ? AND ? GROUP BY day, slug ORDER BY day, slug`,
  )
    .bind(from, to)
    .all();
  return c.json({ rows: results });
});

adminRoutes.post("/advertisers", async (c) => {
  const b = (await readJson(c.req.raw, 2048)) as Record<string, unknown> | undefined;
  const name = typeof b?.name === "string" ? b.name.trim() : "";
  if (name === "" || name.length > 120) return c.json({ error: "invalid_name" }, 400);
  const contact = typeof b?.contact === "string" ? b.contact.slice(0, 200) : "";
  const vatId = typeof b?.vatId === "string" ? b.vatId.slice(0, 40) : "";
  const r = await c.env.DB.prepare("INSERT INTO advertisers (name, contact, vat_id, created_at) VALUES (?, ?, ?, ?)")
    .bind(name, contact, vatId, new Date().toISOString())
    .run();
  const id = r.meta.last_row_id;
  await audit(c.env.DB, c.get("actor"), "advertiser.create", `advertiser:${id}`, name);
  return c.json({ id }, 201);
});

adminRoutes.post("/campaigns", async (c) => {
  const b = (await readJson(c.req.raw, 4096)) as Record<string, unknown> | undefined;
  if (!b) return c.json({ error: "invalid_body" }, 400);
  const errors: string[] = [];
  if (!Number.isInteger(b.advertiserId)) errors.push("advertiserId");
  if (typeof b.name !== "string" || b.name.trim() === "" || b.name.length > 120) errors.push("name");
  if (b.kind !== "direct" && b.kind !== "sponsor") errors.push("kind");
  if (typeof b.startDate !== "string" || !DATE_RE.test(b.startDate)) errors.push("startDate");
  if (typeof b.endDate !== "string" || !DATE_RE.test(b.endDate) || (b.endDate as string) < (b.startDate as string))
    errors.push("endDate");
  if (b.impressionCap !== undefined && b.impressionCap !== null && !(Number.isInteger(b.impressionCap) && (b.impressionCap as number) > 0))
    errors.push("impressionCap");
  if (b.category !== undefined && b.category !== null && !(CATEGORIES as readonly string[]).includes(b.category as string))
    errors.push("category");
  if (errors.length) return c.json({ error: "invalid_fields", fields: errors }, 400);
  const adv = await c.env.DB.prepare("SELECT id FROM advertisers WHERE id = ?").bind(b.advertiserId).first();
  if (!adv) return c.json({ error: "unknown_advertiser" }, 400);
  const r = await c.env.DB.prepare(
    `INSERT INTO campaigns (advertiser_id, name, kind, status, start_date, end_date, priority, impression_cap, category, contract_ref, created_at)
     VALUES (?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?, ?)`,
  )
    .bind(
      b.advertiserId,
      (b.name as string).trim(),
      b.kind,
      b.startDate,
      b.endDate,
      Number.isInteger(b.priority) ? b.priority : 0,
      b.impressionCap ?? null,
      b.category ?? null,
      typeof b.contractRef === "string" ? b.contractRef.slice(0, 120) : "",
      new Date().toISOString(),
    )
    .run();
  const id = r.meta.last_row_id;
  await audit(c.env.DB, c.get("actor"), "campaign.create", `campaign:${id}`);
  return c.json({ id, status: "draft" }, 201);
});

const CAMPAIGN_STATUSES = ["draft", "active", "paused", "ended"];
const PAYMENT_STATUSES = ["unpaid", "invoiced", "paid"];

adminRoutes.patch("/campaigns/:id", async (c) => {
  const id = Number(c.req.param("id"));
  const b = (await readJson(c.req.raw, 1024)) as Record<string, unknown> | undefined;
  if (!Number.isInteger(id) || !b) return c.json({ error: "invalid_request" }, 400);
  if (b.status !== undefined && !CAMPAIGN_STATUSES.includes(b.status as string)) return c.json({ error: "invalid_status" }, 400);
  if (b.paymentStatus !== undefined && !PAYMENT_STATUSES.includes(b.paymentStatus as string))
    return c.json({ error: "invalid_payment_status" }, 400);
  const r = await c.env.DB.prepare(
    "UPDATE campaigns SET status = COALESCE(?, status), payment_status = COALESCE(?, payment_status) WHERE id = ?",
  )
    .bind(b.status ?? null, b.paymentStatus ?? null, id)
    .run();
  if (r.meta.changes === 0) return c.json({ error: "not_found" }, 404);
  await audit(c.env.DB, c.get("actor"), "campaign.update", `campaign:${id}`, JSON.stringify(b));
  return c.json({ id });
});

adminRoutes.post("/creatives", async (c) => {
  const b = (await readJson(c.req.raw, 4096)) as Record<string, unknown> | undefined;
  if (!b) return c.json({ error: "invalid_body" }, 400);
  const errors: string[] = [];
  if (!Number.isInteger(b.campaignId)) errors.push("campaignId");
  if (typeof b.placement !== "string" || !PLACEMENT_RE.test(b.placement)) errors.push("placement");
  // Solo immagini raster statiche servite dal nostro origin (nessun SVG, nessun dominio esterno).
  if (typeof b.imagePath !== "string" || !/^\/ads\/[a-z0-9-]+\.(png|jpg|jpeg|webp)$/.test(b.imagePath)) errors.push("imagePath");
  if (typeof b.altText !== "string" || b.altText.trim() === "" || b.altText.length > 150) errors.push("altText");
  if (!isSafeHttpsUrl(b.clickUrl)) errors.push("clickUrl");
  for (const k of ["width", "height"]) {
    const v = b[k];
    if (!Number.isInteger(v) || (v as number) < 1 || (v as number) > 2000) errors.push(k);
  }
  if (errors.length) return c.json({ error: "invalid_fields", fields: errors }, 400);
  const camp = await c.env.DB.prepare("SELECT id FROM campaigns WHERE id = ?").bind(b.campaignId).first();
  if (!camp) return c.json({ error: "unknown_campaign" }, 400);
  const r = await c.env.DB.prepare(
    `INSERT INTO creatives (campaign_id, placement, image_path, alt_text, click_url, width, height, approved)
     VALUES (?, ?, ?, ?, ?, ?, ?, 0)`,
  )
    .bind(b.campaignId, b.placement, b.imagePath, (b.altText as string).trim(), b.clickUrl, b.width, b.height)
    .run();
  const id = r.meta.last_row_id;
  await audit(c.env.DB, c.get("actor"), "creative.create", `creative:${id}`);
  return c.json({ id, approved: false }, 201);
});

/** Approvazione esplicita della creatività (revisione umana obbligatoria). */
adminRoutes.post("/creatives/:id/approve", async (c) => {
  const id = Number(c.req.param("id"));
  if (!Number.isInteger(id)) return c.json({ error: "invalid_id" }, 400);
  const r = await c.env.DB.prepare("UPDATE creatives SET approved = 1 WHERE id = ?").bind(id).run();
  if (r.meta.changes === 0) return c.json({ error: "not_found" }, 404);
  await audit(c.env.DB, c.get("actor"), "creative.approve", `creative:${id}`);
  return c.json({ id, approved: true });
});

adminRoutes.get("/campaigns/:id/report", async (c) => {
  const id = Number(c.req.param("id"));
  if (!Number.isInteger(id)) return c.json({ error: "invalid_id" }, 400);
  const { results } = await c.env.DB.prepare(
    `SELECT s.day, s.placement, SUM(s.impressions) AS impressions, SUM(s.clicks) AS clicks
     FROM ad_daily_stats s JOIN creatives cr ON cr.id = s.creative_id
     WHERE cr.campaign_id = ? GROUP BY s.day, s.placement ORDER BY s.day`,
  )
    .bind(id)
    .all<{ day: string; placement: string; impressions: number; clicks: number }>();
  const totals = results.reduce(
    (t, r) => ({ impressions: t.impressions + r.impressions, clicks: t.clicks + r.clicks }),
    { impressions: 0, clicks: 0 },
  );
  return c.json({ campaignId: id, totals, ctr: totals.impressions ? totals.clicks / totals.impressions : 0, rows: results });
});

adminRoutes.get("/audit", async (c) => {
  const { results } = await c.env.DB.prepare("SELECT * FROM audit_log ORDER BY id DESC LIMIT 200").all();
  return c.json({ rows: results });
});
