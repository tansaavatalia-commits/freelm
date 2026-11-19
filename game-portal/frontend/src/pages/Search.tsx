import { useSearchParams } from "react-router";
import { GameGrid } from "../components/GameCard";
import { CATALOG } from "../lib/catalog";
import { searchGames } from "../lib/search";
import { useTitle } from "./useTitle";

export function Search() {
  const [params] = useSearchParams();
  const q = params.get("q") ?? "";
  useTitle(q ? `Search: ${q}` : "Search");
  const results = searchGames(CATALOG, q);
  return (
    <section>
      <h1>Search</h1>
      {q === "" ? (
        <p>Type the name of a game, a category or a word like “daily”.</p>
      ) : results.length ? (
        <>
          <p role="status">{results.length} {results.length === 1 ? "game" : "games"} for “{q}”</p>
          <GameGrid games={results} />
        </>
      ) : (
        <p role="status">No games match “{q}”.</p>
      )}
    </section>
  );
}
