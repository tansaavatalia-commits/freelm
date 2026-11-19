import { API_BASE } from "../config";

/** Stato del kill switch. Se l'API non risponde il gioco resta giocabile (fail-open per disponibilità). */
export async function gameStatus(slug: string, signal?: AbortSignal): Promise<{ playable: boolean; reason: string }> {
  try {
    const r = await fetch(`${API_BASE}/api/v1/games/${encodeURIComponent(slug)}/status`, { signal: signal ?? null });
    if (!r.ok) return { playable: true, reason: "" };
    const body = (await r.json()) as { playable?: unknown; reason?: unknown };
    return { playable: body.playable !== false, reason: typeof body.reason === "string" ? body.reason : "" };
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    return { playable: true, reason: "" };
  }
}

/** Evento aggregato e anonimo. Non blocca mai l'interfaccia. */
export function sendEvent(ev: { slug: string; version: string; seconds: number; completed?: boolean; won?: boolean; error?: boolean }) {
  const body = JSON.stringify(ev);
  try {
    if (navigator.sendBeacon?.(`${API_BASE}/api/v1/events`, new Blob([body], { type: "application/json" }))) return;
  } catch {
    /* fallback sotto */
  }
  void fetch(`${API_BASE}/api/v1/events`, { method: "POST", headers: { "Content-Type": "application/json" }, body, keepalive: true }).catch(() => {});
}

export interface AdSlotResponse {
  source: "direct" | "sponsor" | "network" | "none";
  creativeId?: number;
  image?: string;
  alt?: string;
  width?: number;
  height?: number;
  href?: string;
}

export async function fetchAdSlot(placement: string, category?: string, signal?: AbortSignal): Promise<AdSlotResponse> {
  try {
    const q = category ? `?category=${encodeURIComponent(category)}` : "";
    const r = await fetch(`${API_BASE}/api/v1/ads/slot/${encodeURIComponent(placement)}${q}`, { signal: signal ?? null });
    return r.ok ? ((await r.json()) as AdSlotResponse) : { source: "none" };
  } catch {
    return { source: "none" };
  }
}

export function sendImpression(creativeId: number, placement: string) {
  void fetch(`${API_BASE}/api/v1/ads/impressions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items: [{ creativeId, placement }] }),
    keepalive: true,
  }).catch(() => {});
}
