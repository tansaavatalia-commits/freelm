/** Catalogo: tipi condivisi da frontend, backend e script di build. */

export const CATEGORIES = ["cards", "puzzle", "logic", "board", "words"] as const;
export type Category = (typeof CATEGORIES)[number];

export const GAME_STATUSES = ["draft", "review", "published", "suspended"] as const;
export type GameStatus = (typeof GAME_STATUSES)[number];

/** Contenuto di games/<slug>/manifest.json. */
export interface GameManifest {
  slug: string;
  title: string;
  version: string;
  category: Category;
  tags: string[];
  description: string;
  /** Rapporto d'aspetto consigliato del riquadro, es. "1:1" o "16:9". */
  aspect: "1:1" | "4:3" | "16:9" | "3:4";
  /** Il gioco salva i progressi in localStorage del proprio origin. */
  usesStorage: boolean;
  license: ManifestLicense;
}

export interface ManifestLicense {
  type: "internal" | "direct_license" | "commissioned" | "open_source";
  rightsHolder: string;
  spdx?: string;
  /** Asset di terzi usati dal gioco (vuoto = tutto originale). */
  thirdPartyAssets: { name: string; spdx: string; source: string }[];
}

export interface CatalogEntry {
  slug: string;
  title: string;
  version: string;
  category: Category;
  tags: string[];
  description: string;
  aspect: GameManifest["aspect"];
  usesStorage: boolean;
}

const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const SEMVER_RE = /^\d+\.\d+\.\d+$/;

/** Valida un manifest letto da disco o dall'admin. Restituisce gli errori (vuoto = valido). */
export function validateManifest(m: unknown): string[] {
  const errors: string[] = [];
  if (typeof m !== "object" || m === null) return ["manifest non è un oggetto"];
  const x = m as Record<string, unknown>;
  const str = (k: string, max: number) => {
    const v = x[k];
    if (typeof v !== "string" || v.trim() === "") errors.push(`${k}: stringa obbligatoria`);
    else if (v.length > max) errors.push(`${k}: massimo ${max} caratteri`);
  };
  str("slug", 48);
  str("title", 60);
  str("version", 20);
  str("description", 300);
  if (typeof x.slug === "string" && !SLUG_RE.test(x.slug)) errors.push("slug: solo a-z, 0-9 e trattini");
  if (typeof x.version === "string" && !SEMVER_RE.test(x.version)) errors.push("version: formato x.y.z");
  if (!CATEGORIES.includes(x.category as Category)) errors.push(`category: una tra ${CATEGORIES.join(", ")}`);
  if (!Array.isArray(x.tags) || !x.tags.every((t) => typeof t === "string" && SLUG_RE.test(t)))
    errors.push("tags: elenco di slug");
  if (!["1:1", "4:3", "16:9", "3:4"].includes(x.aspect as string)) errors.push("aspect non valido");
  if (typeof x.usesStorage !== "boolean") errors.push("usesStorage: booleano");
  const lic = x.license as Record<string, unknown> | undefined;
  if (!lic || typeof lic !== "object") errors.push("license: obbligatoria");
  else {
    if (!["internal", "direct_license", "commissioned", "open_source"].includes(lic.type as string))
      errors.push("license.type non valido");
    if (typeof lic.rightsHolder !== "string" || lic.rightsHolder === "") errors.push("license.rightsHolder obbligatorio");
    if (lic.type === "open_source" && typeof lic.spdx !== "string") errors.push("license.spdx obbligatorio per open source");
    if (!Array.isArray(lic.thirdPartyAssets)) errors.push("license.thirdPartyAssets: elenco (anche vuoto)");
  }
  return errors;
}

export function toCatalogEntry(m: GameManifest): CatalogEntry {
  const { slug, title, version, category, tags, description, aspect, usesStorage } = m;
  return { slug, title, version, category, tags, description, aspect, usesStorage };
}
