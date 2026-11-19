import type { CSSProperties } from "react";
import { Link } from "react-router";
import type { CatalogEntry } from "@tabluo/shared";
import { ART, CATEGORY_LABELS } from "../lib/catalog";

export function GameCover({ slug, title, large = false }: { slug: string; title: string; large?: boolean }) {
  const art = ART[slug] ?? { glyph: title.charAt(0), hue: 40 };
  return (
    <div className={large ? "cover cover-large" : "cover"} style={{ "--hue": art.hue } as CSSProperties} aria-hidden="true">
      <span>{art.glyph}</span>
    </div>
  );
}

export function GameCard({ game }: { game: CatalogEntry }) {
  return (
    <Link to={`/play/${game.slug}`} className="card">
      <GameCover slug={game.slug} title={game.title} />
      <span className="card-title">{game.title}</span>
      <span className="card-meta">{CATEGORY_LABELS[game.category]}</span>
    </Link>
  );
}

export function GameGrid({ games }: { games: readonly CatalogEntry[] }) {
  return (
    <ul className="grid" role="list">
      {games.map((g) => (
        <li key={g.slug}>
          <GameCard game={g} />
        </li>
      ))}
    </ul>
  );
}
