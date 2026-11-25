// Klondike Solitaire: logica pura. Pescata da 1 o da 3, rimescolamenti illimitati.
import { clone, isRed, newDeck } from "../sdk/cards.js";
import { shuffle } from "../sdk/random.js";

/**
 * @typedef {import("../sdk/cards.js").Card} Card
 * @typedef {{ stock: Card[], waste: Card[], foundations: Card[][], tableau: Card[][], draw: 1 | 3, moves: number }} State
 * @typedef {{ type: "waste" } | { type: "foundation", index: number } | { type: "tableau", index: number, card?: number }} Loc
 */

/** @template T @param {T[]} a @returns {T | undefined} */
const top = (a) => a[a.length - 1];

/** @param {() => number} rng @param {1 | 3} draw @returns {State} */
export function deal(rng, draw = 1) {
  const deck = shuffle(newDeck(), rng);
  /** @type {Card[][]} */
  const tableau = [];
  for (let col = 0; col < 7; col++) {
    const pile = deck.splice(0, col + 1);
    const last = top(pile);
    if (last) last.up = true;
    tableau.push(pile);
  }
  return { stock: deck, waste: [], foundations: [[], [], [], []], tableau, draw, moves: 0 };
}

/** Pesca dal mazzo; se vuoto rimette gli scarti nel mazzo (coperti, ordine invertito). @param {State} s */
export function drawCards(s) {
  if (s.stock.length === 0) {
    if (s.waste.length === 0) return false;
    s.stock = s.waste.reverse().map((c) => ({ ...c, up: false }));
    s.waste = [];
  } else {
    for (let i = 0; i < s.draw && s.stock.length; i++) {
      const c = /** @type {Card} */ (s.stock.pop());
      c.up = true;
      s.waste.push(c);
    }
  }
  s.moves++;
  return true;
}

/** Si può mettere `c` sopra `onto` nel tableau? @param {Card} c @param {Card | undefined} onto */
export function canStack(c, onto) {
  if (!onto) return c.rank === 13;
  return onto.up && isRed(onto) !== isRed(c) && onto.rank === c.rank + 1;
}

/** Si può mettere `c` sulla fondazione `pile`? @param {Card} c @param {Card[]} pile */
export function canFound(c, pile) {
  const t = top(pile);
  return t ? t.suit === c.suit && t.rank + 1 === c.rank : c.rank === 1;
}

/** Carte che partirebbero da `from` (vuoto se la presa non è valida). @param {State} s @param {Loc} from @returns {Card[]} */
export function pick(s, from) {
  if (from.type === "waste") return s.waste.length ? [/** @type {Card} */ (top(s.waste))] : [];
  if (from.type === "foundation") {
    const p = s.foundations[from.index];
    return p && p.length ? [/** @type {Card} */ (top(p))] : [];
  }
  const col = s.tableau[from.index];
  if (!col || col.length === 0) return [];
  const i = from.card ?? col.length - 1;
  const run = col.slice(i);
  if (run.length === 0 || !run.every((c) => c.up)) return [];
  for (let k = 1; k < run.length; k++) if (!canStack(/** @type {Card} */ (run[k]), run[k - 1])) return [];
  return run;
}

/** Esegue la mossa se valida. @param {State} s @param {Loc} from @param {Loc} to @returns {boolean} */
export function move(s, from, to) {
  const cards = pick(s, from);
  const first = cards[0];
  if (!first || to.type === "waste") return false;
  if (from.type !== "waste" && from.type === to.type && from.index === to.index) return false; // stessa pila
  if (to.type === "foundation") {
    const pile = s.foundations[to.index];
    if (!pile || cards.length !== 1 || !canFound(first, pile)) return false;
  } else {
    const col = s.tableau[to.index];
    if (!col || !canStack(first, top(col))) return false;
  }
  // rimozione dalla sorgente
  if (from.type === "waste") s.waste.pop();
  else if (from.type === "foundation") s.foundations[from.index]?.pop();
  else {
    const col = /** @type {Card[]} */ (s.tableau[from.index]);
    col.splice(col.length - cards.length, cards.length);
    const t = top(col);
    if (t) t.up = true;
  }
  // aggiunta alla destinazione
  const dest = to.type === "foundation" ? s.foundations[to.index] : s.tableau[to.index];
  /** @type {Card[]} */ (dest).push(...cards);
  s.moves++;
  return true;
}

/** Prova a mandare la carta in cima a `from` su una fondazione. @param {State} s @param {Loc} from */
export function toFoundation(s, from) {
  for (let f = 0; f < 4; f++) if (move(s, from, { type: "foundation", index: f })) return true;
  return false;
}

/** Ripete le mosse sicure verso le fondazioni finché possibile (fine partita). Restituisce quante. @param {State} s */
export function autoFinish(s) {
  let n = 0;
  let moved = true;
  while (moved) {
    moved = false;
    if (toFoundation(s, { type: "waste" })) { moved = true; n++; continue; }
    for (let c = 0; c < 7; c++) if (toFoundation(s, { type: "tableau", index: c })) { moved = true; n++; break; }
  }
  return n;
}

/** Tutte le carte scoperte e mazzo vuoto: la vittoria è garantita con autoFinish. @param {State} s */
export function canAutoFinish(s) {
  return s.stock.length === 0 && s.waste.length === 0 && s.tableau.every((col) => col.every((c) => c.up));
}

/** @param {State} s */
export function isWon(s) {
  return s.foundations.every((p) => p.length === 13);
}

export { clone };
