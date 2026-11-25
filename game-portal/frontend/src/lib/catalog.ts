import type { Category, CatalogEntry } from "@tabluo/shared";
import data from "../generated/catalog.json";

export const CATALOG = data as CatalogEntry[];

export const CATEGORY_LABELS: Record<Category, string> = {
  cards: "Card games",
  puzzle: "Puzzles",
  logic: "Logic",
  board: "Board games",
  words: "Word games",
};

/** Simbolo e colore delle copertine generate in CSS (nessuna immagine di terzi). */
export const ART: Record<string, { glyph: string; hue: number }> = {
  mines: { glyph: "✹", hue: 12 },
  sudoku: { glyph: "9", hue: 158 },
  nonogram: { glyph: "▦", hue: 215 },
  klondike: { glyph: "♠", hue: 140 },
};

export function findGame(slug: string): CatalogEntry | undefined {
  return CATALOG.find((g) => g.slug === slug);
}

export function categoriesInUse(): Category[] {
  return [...new Set(CATALOG.map((g) => g.category))];
}

/** Correlati: stessa categoria prima, poi tag in comune; esclude il gioco stesso. */
export function related(game: CatalogEntry, limit = 4): CatalogEntry[] {
  return CATALOG.filter((g) => g.slug !== game.slug)
    .map((g) => ({ g, score: (g.category === game.category ? 2 : 0) + g.tags.filter((t) => game.tags.includes(t)).length }))
    .sort((a, b) => b.score - a.score || a.g.title.localeCompare(b.g.title))
    .slice(0, limit)
    .map((x) => x.g);
}
