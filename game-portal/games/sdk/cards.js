// Carte da gioco: modello condiviso dai solitari (Klondike, FreeCell, Spider).

/** @typedef {{ suit: number, rank: number, up: boolean }} Card  suit 0..3 = ♠ ♥ ♦ ♣, rank 1..13 */

export const SUITS = ["♠", "♥", "♦", "♣"];
export const RANKS = ["", "A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"];

/** @param {Card} c */
export const isRed = (c) => c.suit === 1 || c.suit === 2;

/** @param {Card} c */
export const label = (c) => `${RANKS[c.rank]}${SUITS[c.suit]}`;

const NAMES = ["", "Ace", "2", "3", "4", "5", "6", "7", "8", "9", "10", "Jack", "Queen", "King"];
const SUIT_NAMES = ["spades", "hearts", "diamonds", "clubs"];
/** @param {Card} c */
export const spoken = (c) => `${NAMES[c.rank]} of ${SUIT_NAMES[c.suit]}`;

/** Mazzo ordinato di 52 carte coperte. @returns {Card[]} */
export function newDeck() {
  /** @type {Card[]} */
  const deck = [];
  for (let suit = 0; suit < 4; suit++) for (let rank = 1; rank <= 13; rank++) deck.push({ suit, rank, up: false });
  return deck;
}

/** Copia profonda di uno stato serializzabile (per undo). @template T @param {T} v @returns {T} */
export const clone = (v) => /** @type {T} */ (JSON.parse(JSON.stringify(v)));
