import type { CatalogEntry } from "@tabluo/shared";

const norm = (s: string) => s.toLowerCase().normalize("NFD").replace(/\p{Diacritic}/gu, "");

/** Ricerca locale: tutte le parole devono comparire in titolo, tag, categoria o descrizione. */
export function searchGames(games: readonly CatalogEntry[], query: string): CatalogEntry[] {
  const words = norm(query).split(/\s+/).filter(Boolean);
  if (words.length === 0) return [];
  return games
    .map((g) => {
      const title = norm(g.title);
      const hay = `${title} ${g.tags.join(" ")} ${g.category} ${norm(g.description)}`;
      if (!words.every((w) => hay.includes(w))) return null;
      return { g, score: words.filter((w) => title.includes(w)).length };
    })
    .filter((x): x is { g: CatalogEntry; score: number } => x !== null)
    .sort((a, b) => b.score - a.score || a.g.title.localeCompare(b.g.title))
    .map((x) => x.g);
}
