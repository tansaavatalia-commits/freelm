import { describe, expect, it } from "vitest";
import { label } from "../sdk/cards.js";
import { mulberry32 } from "../sdk/random.js";
import * as k from "../klondike/logic.js";

/** @param {number} suit @param {number} rank @param {boolean} [up] */
const c = (suit, rank, up = true) => ({ suit, rank, up });
/** Stato vuoto da riempire nei test. @returns {import("../klondike/logic.js").State} */
const empty = () => ({ stock: [], waste: [], foundations: [[], [], [], []], tableau: [[], [], [], [], [], [], []], draw: 1, moves: 0 });

describe("klondike: distribuzione", () => {
  it("52 carte uniche: 28 nel tableau (solo l'ultima scoperta), 24 nel mazzo", () => {
    const s = k.deal(mulberry32(1));
    expect(s.tableau.map((col) => col.length)).toEqual([1, 2, 3, 4, 5, 6, 7]);
    expect(s.tableau.every((col) => col.every((x, i) => x.up === (i === col.length - 1)))).toBe(true);
    expect(s.stock).toHaveLength(24);
    const all = [...s.stock, ...s.tableau.flat()].map(label);
    expect(new Set(all).size).toBe(52);
  });
  it("è deterministica per seed", () => {
    expect(k.deal(mulberry32(7)).stock).toEqual(k.deal(mulberry32(7)).stock);
  });
});

describe("klondike: mazzo e scarti", () => {
  it("pesca 1 o 3 carte e rimescola gli scarti quando il mazzo è vuoto", () => {
    const s = k.deal(mulberry32(2), 3);
    k.drawCards(s);
    expect(s.waste).toHaveLength(3);
    expect(s.waste.every((x) => x.up)).toBe(true);
    for (let i = 0; i < 7; i++) k.drawCards(s);
    expect(s.stock).toHaveLength(0);
    expect(s.waste).toHaveLength(24);
    const firstWaste = s.waste[0];
    k.drawCards(s);
    expect(s.waste).toHaveLength(0);
    expect(s.stock).toHaveLength(24);
    expect(s.stock.every((x) => !x.up)).toBe(true);
    expect(s.stock[s.stock.length - 1]).toMatchObject({ suit: firstWaste?.suit, rank: firstWaste?.rank });
  });
  it("non fa nulla con mazzo e scarti vuoti", () => {
    expect(k.drawCards(empty())).toBe(false);
  });
});

describe("klondike: regole", () => {
  it("impilamento a colori alterni e scala decrescente; solo il Re su colonna vuota", () => {
    expect(k.canStack(c(1, 6), c(0, 7))).toBe(true); // 6♥ su 7♠
    expect(k.canStack(c(0, 6), c(3, 7))).toBe(false); // stesso colore
    expect(k.canStack(c(1, 5), c(0, 7))).toBe(false); // salto di valore
    expect(k.canStack(c(0, 13), undefined)).toBe(true);
    expect(k.canStack(c(0, 12), undefined)).toBe(false);
    expect(k.canStack(c(1, 6), c(0, 7, false))).toBe(false); // carta coperta
  });
  it("fondazioni: Asso per primo, poi stesso seme in ordine", () => {
    expect(k.canFound(c(2, 1), [])).toBe(true);
    expect(k.canFound(c(2, 2), [])).toBe(false);
    expect(k.canFound(c(2, 2), [c(2, 1)])).toBe(true);
    expect(k.canFound(c(1, 2), [c(2, 1)])).toBe(false);
  });
  it("sposta una sequenza valida e scopre la carta sottostante", () => {
    const s = empty();
    s.tableau[0] = [c(3, 2, false), c(0, 9), c(1, 8)];
    s.tableau[1] = [c(2, 10)];
    expect(k.move(s, { type: "tableau", index: 0, card: 1 }, { type: "tableau", index: 1 })).toBe(true);
    expect(s.tableau[1]?.map(label)).toEqual(["10♦", "9♠", "8♥"]);
    expect(s.tableau[0]).toEqual([c(3, 2, true)]);
    expect(s.moves).toBe(1);
  });
  it("rifiuta prese non valide e mosse sulla stessa pila", () => {
    const s = empty();
    s.tableau[0] = [c(0, 9, false), c(1, 8)];
    s.tableau[1] = [c(2, 10)];
    expect(k.move(s, { type: "tableau", index: 0, card: 0 }, { type: "tableau", index: 1 })).toBe(false); // coperta
    expect(k.move(s, { type: "tableau", index: 0 }, { type: "tableau", index: 0 })).toBe(false);
    expect(k.move(s, { type: "tableau", index: 0 }, { type: "waste" })).toBe(false);
    expect(k.move(s, { type: "waste" }, { type: "tableau", index: 1 })).toBe(false); // scarti vuoti
    expect(s.moves).toBe(0);
  });
  it("non manda più carte insieme su una fondazione", () => {
    const s = empty();
    s.tableau[0] = [c(0, 2), c(1, 1)];
    expect(k.move(s, { type: "tableau", index: 0, card: 0 }, { type: "foundation", index: 0 })).toBe(false);
  });
  it("toFoundation trova la fondazione giusta e la carta può tornare nel tableau", () => {
    const s = empty();
    s.waste = [c(3, 1)];
    expect(k.toFoundation(s, { type: "waste" })).toBe(true);
    s.waste = [c(3, 2)];
    expect(k.toFoundation(s, { type: "waste" })).toBe(true);
    expect(s.foundations.find((p) => p.length === 2)?.map(label)).toEqual(["A♣", "2♣"]);
    s.tableau[2] = [c(1, 3)];
    const f = s.foundations.findIndex((p) => p.length === 2);
    expect(k.move(s, { type: "foundation", index: f }, { type: "tableau", index: 2 })).toBe(true);
  });
});

describe("klondike: fine partita", () => {
  it("autoFinish completa una partita con tutte le carte scoperte e dichiara la vittoria", () => {
    const s = empty();
    // 4 colonne K..A a colori alterni; ogni seme compare una sola volta per valore.
    // [seme per valori dispari, seme per valori pari]: ♠/♥, ♥/♠, ♦/♣, ♣/♦
    const pairs = [[0, 1], [1, 0], [2, 3], [3, 2]];
    pairs.forEach(([odd, even], col) => {
      s.tableau[col] = Array.from({ length: 13 }, (_, i) => {
        const rank = 13 - i;
        return c(/** @type {number} */ (rank % 2 ? odd : even), rank);
      });
    });
    expect(new Set(s.tableau.flat().map(label)).size).toBe(52);
    expect(k.canAutoFinish(s)).toBe(true);
    expect(k.isWon(s)).toBe(false);
    expect(k.autoFinish(s)).toBe(52);
    expect(k.isWon(s)).toBe(true);
  });
  it("non si può finire in automatico con carte coperte o mazzo non vuoto", () => {
    const s = k.deal(mulberry32(3));
    expect(k.canAutoFinish(s)).toBe(false);
  });
  it("una partita casuale giocata solo con mosse legali conserva sempre 52 carte", () => {
    const s = k.deal(mulberry32(99));
    const rng = mulberry32(5);
    for (let step = 0; step < 2000; step++) {
      if (rng() < 0.3) k.drawCards(s);
      const from = rng() < 0.3 ? { type: "waste" } : { type: "tableau", index: Math.floor(rng() * 7) };
      const to = rng() < 0.4 ? { type: "foundation", index: Math.floor(rng() * 4) } : { type: "tableau", index: Math.floor(rng() * 7) };
      k.move(s, /** @type {any} */ (from), /** @type {any} */ (to));
      const total = s.stock.length + s.waste.length + s.foundations.flat().length + s.tableau.flat().length;
      expect(total).toBe(52);
    }
    for (const p of s.foundations) p.forEach((x, i) => expect(x.rank).toBe(i + 1));
  });
});
