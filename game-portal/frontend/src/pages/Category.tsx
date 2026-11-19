import { useParams } from "react-router";
import { CATEGORIES, type Category as Cat } from "@tabluo/shared";
import { GameGrid } from "../components/GameCard";
import { CATALOG, CATEGORY_LABELS } from "../lib/catalog";
import { NotFound } from "./NotFound";
import { useTitle } from "./useTitle";

export function Category() {
  const { category = "" } = useParams();
  const valid = (CATEGORIES as readonly string[]).includes(category);
  const label = valid ? CATEGORY_LABELS[category as Cat] : "";
  useTitle(label, label ? `${label} you can play free in your browser on Tabluo.` : undefined);
  if (!valid) return <NotFound />;
  const games = CATALOG.filter((g) => g.category === category);
  return (
    <section>
      <h1>{label}</h1>
      {games.length ? <GameGrid games={games} /> : <p>New games in this category are on the way.</p>}
    </section>
  );
}
