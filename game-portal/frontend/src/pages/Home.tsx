import { Link } from "react-router";
import { AdSlot } from "../components/AdSlot";
import { GameGrid } from "../components/GameCard";
import { CATALOG, CATEGORY_LABELS, categoriesInUse } from "../lib/catalog";
import { useTitle } from "./useTitle";

export function Home() {
  useTitle("");
  return (
    <>
      <section className="hero">
        <h1>Classic games, calmly done.</h1>
        <p>Cards, puzzles and logic games that load in a blink. No downloads, no sign-up, no tracking cookies.</p>
        <Link to="/play/nonogram" className="button-primary">Play today’s daily puzzle</Link>
      </section>
      <AdSlot placement="home-top" />
      <section aria-labelledby="all-games">
        <h2 id="all-games">All games</h2>
        <GameGrid games={CATALOG} />
      </section>
      <section aria-labelledby="cats">
        <h2 id="cats">Categories</h2>
        <ul className="chips" role="list">
          {categoriesInUse().map((c) => (
            <li key={c}>
              <Link to={`/c/${c}`} className="chip">{CATEGORY_LABELS[c]}</Link>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
