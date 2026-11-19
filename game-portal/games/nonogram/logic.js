// Nonogram: logica pura. Una soluzione è valida se rispetta TUTTI gli indizi
// (anche se diversa da quella generata), quindi non serve l'unicità.
import { hashString, mulberry32 } from "../sdk/random.js";

/** @typedef {0 | 1} Bit */

/** Lunghezze dei gruppi di celle piene. @param {ArrayLike<number>} line @returns {number[]} */
export function lineClues(line) {
  /** @type {number[]} */
  const out = [];
  let run = 0;
  for (let i = 0; i < line.length; i++) {
    if (line[i] === 1) run++;
    else if (run) { out.push(run); run = 0; }
  }
  if (run) out.push(run);
  return out;
}

/** @param {Bit[]} cells @param {number} size */
export function rows(cells, size) {
  return Array.from({ length: size }, (_, r) => cells.slice(r * size, r * size + size));
}

/** @param {Bit[]} cells @param {number} size */
export function cols(cells, size) {
  return Array.from({ length: size }, (_, c) => Array.from({ length: size }, (_, r) => /** @type {number} */ (cells[r * size + c])));
}

/** @param {Bit[]} cells @param {number} size */
export function clues(cells, size) {
  return { rows: rows(cells, size).map(lineClues), cols: cols(cells, size).map(lineClues) };
}

/** Griglia casuale con densità controllata; nessuna riga o colonna vuota. @param {() => number} rng @param {number} size */
export function generate(rng, size, density = 0.58) {
  for (let attempt = 0; attempt < 100; attempt++) {
    /** @type {Bit[]} */
    const cells = Array.from({ length: size * size }, () => (rng() < density ? 1 : 0));
    const cl = clues(cells, size);
    if (cl.rows.every((r) => r.length) && cl.cols.every((c) => c.length)) return { cells, clues: cl };
  }
  throw new Error("generazione fallita");
}

/** Puzzle del giorno: stesso puzzle per tutti nella stessa data UTC. @param {string} day @param {number} size */
export function daily(day, size) {
  return generate(mulberry32(hashString(`nonogram:${size}:${day}`)), size);
}

/** @param {number[][]} a @param {number[][]} b */
const sameClues = (a, b) => a.length === b.length && a.every((x, i) => x.join(",") === (b[i] ?? []).join(","));

/** @param {Bit[]} cells @param {number} size @param {{ rows: number[][], cols: number[][] }} target */
export function isSolved(cells, size, target) {
  const cl = clues(cells, size);
  return sameClues(cl.rows, target.rows) && sameClues(cl.cols, target.cols);
}
