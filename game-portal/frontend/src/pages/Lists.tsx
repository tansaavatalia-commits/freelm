import { useState } from "react";
import { GameGrid } from "../components/GameCard";
import { findGame } from "../lib/catalog";
import { favorites, history } from "../lib/storage";
import type { CatalogEntry } from "@tabluo/shared";
import { useTitle } from "./useTitle";

const resolve = (slugs: string[]) => slugs.map(findGame).filter((g): g is CatalogEntry => g !== undefined);

export function Favorites() {
  useTitle("Favorites");
  const games = resolve(favorites.list());
  return (
    <section>
      <h1>Favorites</h1>
      <p className="muted">Saved on this device only.</p>
      {games.length ? <GameGrid games={games} /> : <p>Tap “☆ Save” on any game to keep it here.</p>}
    </section>
  );
}

export function History() {
  useTitle("Recently played");
  const [games, setGames] = useState(() => resolve(history.list()));
  return (
    <section>
      <h1>Recently played</h1>
      <p className="muted">Stored on this device only.</p>
      {games.length ? (
        <>
          <GameGrid games={games} />
          <button type="button" onClick={() => { history.clear(); setGames([]); }}>Clear history</button>
        </>
      ) : (
        <p>Nothing here yet.</p>
      )}
    </section>
  );
}
