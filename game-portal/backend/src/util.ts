/** Data UTC corrente in formato YYYY-MM-DD. */
export function today(now: Date = new Date()): string {
  return now.toISOString().slice(0, 10);
}

export const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
export const SEMVER_RE = /^\d+\.\d+\.\d+$/;
export const PLACEMENT_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
export const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Accetta solo URL https assoluti (niente javascript:, data:, http:). */
export function isSafeHttpsUrl(value: unknown): value is string {
  if (typeof value !== "string" || value.length > 2000) return false;
  try {
    const u = new URL(value);
    return u.protocol === "https:" && u.hostname.length > 0 && u.username === "" && u.password === "";
  } catch {
    return false;
  }
}

/** Confronto a tempo costante tramite digest SHA-256 (evita timing attack sul token). */
export async function safeEqual(a: string, b: string): Promise<boolean> {
  const enc = new TextEncoder();
  const [ha, hb] = await Promise.all([
    crypto.subtle.digest("SHA-256", enc.encode(a)),
    crypto.subtle.digest("SHA-256", enc.encode(b)),
  ]);
  const va = new Uint8Array(ha);
  const vb = new Uint8Array(hb);
  let diff = 0;
  for (let i = 0; i < va.length; i++) diff |= (va[i] ?? 0) ^ (vb[i] ?? 0);
  return diff === 0;
}

/** Legge un body JSON con limite di dimensione. Restituisce undefined se assente/non valido/troppo grande. */
export async function readJson(req: Request, maxBytes: number): Promise<unknown> {
  const len = Number(req.headers.get("content-length") ?? "0");
  if (len > maxBytes) return undefined;
  const text = await req.text();
  if (text.length === 0 || new TextEncoder().encode(text).length > maxBytes) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}
