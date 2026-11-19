import { describe, expect, it } from "vitest";
import { hashString, mulberry32, shuffle } from "../sdk/random.js";
import * as mines from "../mines/logic.js";
import * as sudoku from "../sudoku/logic.js";
import * as nono from "../nonogram/logic.js";

describe("random", () => {
  it("è deterministico per seed", () => {
    const a = mulberry32(42), b = mulberry32(42);
    expect([a(), a(), a()]).toEqual([b(), b(), b()]);
  });
  it("produce valori in [0, 1)", () => {
    const r = mulberry32(7);
    for (let i = 0; i < 1000; i++) { const v = r(); expect(v >= 0 && v < 1).toBe(true); }
  });
  it("hash stabile e shuffle permutazione", () => {
    expect(hashString("2026-11-19")).toBe(hashString("2026-11-19"));
    expect(hashString("a")).not.toBe(hashString("b"));
    expect(shuffle([1, 2, 3, 4, 5], mulberry32(1)).sort()).toEqual([1, 2, 3, 4, 5]);
  });
});

describe("mines", () => {
  it("la prima mossa è sicura e apre un'area", () => {
    for (let seed = 1; seed <= 50; seed++) {
      const b = mines.createBoard(9, 9, 10);
      mines.reveal(b, 40, mulberry32(seed));
      expect(b.state).not.toBe("lost");
      expect(b.cells.filter((c) => c.mine)).toHaveLength(10);
      expect(b.cells[40]?.near).toBe(0);
    }
  });
  it("vince aprendo tutte le celle sicure", () => {
    const b = mines.createBoard(9, 9, 10);
    const rng = mulberry32(3);
    mines.reveal(b, 0, rng);
    b.cells.forEach((c, i) => { if (!c.mine) mines.reveal(b, i, rng); });
    expect(b.state).toBe("won");
    expect(mines.flagsLeft(b)).toBe(0);
  });
  it("perde toccando una mina e non accetta altre mosse", () => {
    const b = mines.createBoard(9, 9, 10);
    const rng = mulberry32(5);
    mines.reveal(b, 0, rng);
    const mine = b.cells.findIndex((c) => c.mine);
    mines.reveal(b, mine, rng);
    expect(b.state).toBe("lost");
    const opened = b.opened;
    mines.reveal(b, b.cells.findIndex((c) => !c.open), rng);
    expect(b.opened).toBe(opened);
  });
  it("le bandierine bloccano l'apertura e il chord apre le vicine", () => {
    const b = mines.createBoard(9, 9, 10);
    const rng = mulberry32(11);
    mines.reveal(b, 40, rng);
    const num = b.cells.findIndex((c, i) => c.open && c.near > 0 && mines.neighbors(b, i).some((n) => !b.cells[n]?.open));
    const ns = mines.neighbors(b, num);
    ns.filter((n) => b.cells[n]?.mine).forEach((n) => mines.toggleFlag(b, n));
    mines.chord(b, num, rng);
    expect(ns.every((n) => b.cells[n]?.open || b.cells[n]?.flag)).toBe(true);
    expect(b.state).not.toBe("lost");
  });
  it("rifiuta griglie con troppe mine", () => expect(() => mines.createBoard(3, 3, 5)).toThrow());
});

describe("sudoku", () => {
  it("genera griglie complete valide", () => {
    const g = sudoku.solvedGrid(mulberry32(9));
    expect(sudoku.isSolved(g)).toBe(true);
  });
  for (const level of /** @type {const} */ (["easy", "medium", "hard"])) {
    it(`il puzzle ${level} ha soluzione unica coerente`, () => {
      const { puzzle, solution } = sudoku.generate(mulberry32(level.length * 101), level);
      expect(sudoku.countSolutions(puzzle, 2)).toBe(1);
      puzzle.forEach((v, i) => { if (v) expect(v).toBe(solution[i]); });
      const clues = puzzle.filter((v) => v).length;
      expect(clues).toBeGreaterThanOrEqual(sudoku.DIFFICULTY[level]);
      expect(clues).toBeLessThan(81);
    });
  }
  it("rileva conflitti e griglie incomplete", () => {
    const g = sudoku.solvedGrid(mulberry32(2));
    const bad = g.slice();
    bad[1] = bad[0] ?? 1;
    expect(sudoku.conflicts(bad).size).toBeGreaterThan(0);
    expect(sudoku.isSolved(bad)).toBe(false);
    const holes = g.slice();
    holes[0] = 0;
    expect(sudoku.isSolved(holes)).toBe(false);
  });
});

describe("nonogram", () => {
  it("calcola gli indizi di una riga", () => {
    expect(nono.lineClues([1, 1, 0, 1, 0, 0, 1, 1, 1])).toEqual([2, 1, 3]);
    expect(nono.lineClues([0, 0, 0])).toEqual([]);
  });
  it("il puzzle del giorno è stabile e cambia con la data", () => {
    const a = nono.daily("2026-11-19", 10), b = nono.daily("2026-11-19", 10), c = nono.daily("2026-11-20", 10);
    expect(a.cells).toEqual(b.cells);
    expect(a.cells).not.toEqual(c.cells);
  });
  it("nessuna riga o colonna vuota e la soluzione generata è valida", () => {
    for (let seed = 1; seed <= 30; seed++) {
      const p = nono.generate(mulberry32(seed), 10);
      expect(p.clues.rows.every((r) => r.length > 0)).toBe(true);
      expect(p.clues.cols.every((r) => r.length > 0)).toBe(true);
      expect(nono.isSolved(p.cells, 10, p.clues)).toBe(true);
    }
  });
  it("rifiuta una griglia vuota o sbagliata", () => {
    const p = nono.generate(mulberry32(4), 5);
    expect(nono.isSolved(new Array(25).fill(0), 5, p.clues)).toBe(false);
    const wrong = p.cells.slice();
    wrong[0] = wrong[0] ? 0 : 1;
    expect(nono.isSolved(wrong, 5, p.clues)).toBe(false);
  });
});
