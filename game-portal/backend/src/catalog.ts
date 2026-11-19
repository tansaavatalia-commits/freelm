import catalog from "./generated/catalog.json";
import type { CatalogEntry } from "@tabluo/shared";

/** Catalogo pubblicato, generato in build da scripts/build-catalog.mjs (solo giochi con licenza valida). */
export const CATALOG: readonly CatalogEntry[] = catalog as CatalogEntry[];
const BY_SLUG = new Map(CATALOG.map((g) => [g.slug, g]));

export function findGame(slug: string): CatalogEntry | undefined {
  return BY_SLUG.get(slug);
}
