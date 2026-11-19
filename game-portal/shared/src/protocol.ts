/**
 * Protocollo postMessage gioco -> portale. Il portale accetta SOLO questi messaggi,
 * SOLO dall'iframe del gioco corrente, e ignora tutto il resto.
 */

export const PROTOCOL = "tabluo/1" as const;

export type GameMessage =
  | { protocol: typeof PROTOCOL; type: "ready" }
  | { protocol: typeof PROTOCOL; type: "score"; value: number }
  | { protocol: typeof PROTOCOL; type: "complete"; won: boolean; seconds: number }
  | { protocol: typeof PROTOCOL; type: "error"; message: string };

const MAX_SCORE = 1e9;
const MAX_SECONDS = 24 * 3600;

/** Restituisce il messaggio normalizzato oppure null se non valido. */
export function parseGameMessage(data: unknown): GameMessage | null {
  if (typeof data !== "object" || data === null) return null;
  const d = data as Record<string, unknown>;
  if (d.protocol !== PROTOCOL) return null;
  switch (d.type) {
    case "ready":
      return { protocol: PROTOCOL, type: "ready" };
    case "score":
      return typeof d.value === "number" && Number.isFinite(d.value) && Math.abs(d.value) <= MAX_SCORE
        ? { protocol: PROTOCOL, type: "score", value: Math.trunc(d.value) }
        : null;
    case "complete":
      return typeof d.won === "boolean" &&
        typeof d.seconds === "number" &&
        Number.isFinite(d.seconds) &&
        d.seconds >= 0 &&
        d.seconds <= MAX_SECONDS
        ? { protocol: PROTOCOL, type: "complete", won: d.won, seconds: Math.round(d.seconds) }
        : null;
    case "error":
      return typeof d.message === "string"
        ? { protocol: PROTOCOL, type: "error", message: d.message.slice(0, 200) }
        : null;
    default:
      return null;
  }
}
