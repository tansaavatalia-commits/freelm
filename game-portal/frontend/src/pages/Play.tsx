import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { AdSlot } from "../components/AdSlot";
import { GameGrid } from "../components/GameCard";
import { Player } from "../components/Player";
import { CATEGORY_LABELS, findGame, related } from "../lib/catalog";
import { favorites, history } from "../lib/storage";
import { NotFound } from "./NotFound";
import { useTitle } from "./useTitle";

export function Play() {
  const { slug = "" } = useParams();
  const game = findGame(slug);
  const [fav, setFav] = useState(false);
  useTitle(game ? `${game.title} — play free online` : "Not found", game?.description);

  useEffect(() => {
    if (!game) return;
    setFav(favorites.has(game.slug));
    history.add(game.slug);
  }, [game]);

  if (!game) return <NotFound />;
  return (
    <article className="play">
      <div className="play-head">
        <div>
          <p className="crumbs">
            <Link to={`/c/${game.category}`}>{CATEGORY_LABELS[game.category]}</Link>
          </p>
          <h1>{game.title}</h1>
        </div>
        <button type="button" className="fav" aria-pressed={fav} onClick={() => setFav(favorites.toggle(game.slug))}>
          {fav ? "★ Saved" : "☆ Save"}
        </button>
      </div>
      <Player key={game.slug} game={game} />
      <p className="lead">{game.description}</p>
      <AdSlot placement="game-below" category={game.category} />
      <section aria-labelledby="more">
        <h2 id="more">You might also like</h2>
        <GameGrid games={related(game)} />
      </section>
    </article>
  );
}
