import { parseGameMessage, type CatalogEntry, type GameMessage } from "@tabluo/shared";

/**
 * Permessi dell'iframe. Mai "allow-top-navigation", "allow-popups", "allow-forms".
 * allow-same-origin è concesso solo ai giochi che usano storage (solo giochi interni,
 * imposto dallo script di catalogo): resta sicuro perché il gioco gira su un origin
 * diverso dal portale, senza accesso ai suoi cookie o al suo DOM.
 */
export function sandboxFor(game: Pick<CatalogEntry, "usesStorage">): string {
  return game.usesStorage ? "allow-scripts allow-same-origin" : "allow-scripts";
}

export function gameUrl(origin: string, slug: string): string {
  return `${origin.replace(/\/$/, "")}/${encodeURIComponent(slug)}/index.html`;
}

/** Origin atteso dei messaggi: quello dei giochi, oppure "null" per i sandbox senza allow-same-origin. */
export function expectedOrigin(gamesOrigin: string, game: Pick<CatalogEntry, "usesStorage">): string {
  return game.usesStorage ? new URL(gamesOrigin).origin : "null";
}

/** Accetta un messaggio solo se proviene dall'iframe corrente, dall'origin atteso e rispetta lo schema. */
export function acceptMessage(
  e: Pick<MessageEvent, "origin" | "source" | "data">,
  frame: Window | null | undefined,
  origin: string,
): GameMessage | null {
  if (!frame || e.source !== frame || e.origin !== origin) return null;
  return parseGameMessage(e.data);
}
