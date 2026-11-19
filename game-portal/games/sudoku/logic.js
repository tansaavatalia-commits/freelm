// Sudoku: generatore con soluzione unica (verificata dal risolutore). Griglia = 81 numeri, 0 = vuoto.
import { shuffle } from "../sdk/random.js";

/** @typedef {number[]} Grid */

export const DIFFICULTY = { easy: 40, medium: 32, hard: 26 }; // indizi da lasciare (obiettivo)

/** @param {Grid} g @param {number} i */
const at = (g, i) => /** @type {number} */ (g[i]);

/** @param {Grid} g @param {number} i @param {number} v */
export function canPlace(g, i, v) {
  const r = Math.floor(i / 9);
  const c = i % 9;
  const br = r - (r % 3);
  const bc = c - (c % 3);
  for (let k = 0; k < 9; k++) {
    if (k !== c && at(g, r * 9 + k) === v) return false;
    if (k !== r && at(g, k * 9 + c) === v) return false;
    const bi = (br + Math.floor(k / 3)) * 9 + bc + (k % 3);
    if (bi !== i && at(g, bi) === v) return false;
  }
  return true;
}

/** Cella vuota con meno candidati (euristica MRV). @param {Grid} g */
function bestEmpty(g) {
  let best = -1;
  /** @type {number[]} */
  let bestCands = [];
  for (let i = 0; i < 81; i++) {
    if (at(g, i) !== 0) continue;
    const cands = [];
    for (let v = 1; v <= 9; v++) if (canPlace(g, i, v)) cands.push(v);
    if (best === -1 || cands.length < bestCands.length) {
      best = i;
      bestCands = cands;
      if (cands.length <= 1) break;
    }
  }
  return { i: best, cands: bestCands };
}

/** Conta le soluzioni fino a `limit`. Non modifica `grid`. @param {Grid} grid @param {number} [limit] */
export function countSolutions(grid, limit = 2) {
  const g = grid.slice();
  let count = 0;
  const solve = () => {
    const { i, cands } = bestEmpty(g);
    if (i === -1) {
      count++;
      return count >= limit;
    }
    for (const v of cands) {
      g[i] = v;
      if (solve()) return true;
    }
    g[i] = 0;
    return false;
  };
  solve();
  return count;
}

/** Griglia completa casuale. @param {() => number} rng @returns {Grid} */
export function solvedGrid(rng) {
  /** @type {Grid} */
  const g = new Array(81).fill(0);
  const fill = () => {
    const { i, cands } = bestEmpty(g);
    if (i === -1) return true;
    for (const v of shuffle(cands, rng)) {
      g[i] = v;
      if (fill()) return true;
    }
    g[i] = 0;
    return false;
  };
  fill();
  return g;
}

/** @param {() => number} rng @param {keyof typeof DIFFICULTY} level */
export function generate(rng, level) {
  const solution = solvedGrid(rng);
  const puzzle = solution.slice();
  const target = DIFFICULTY[level];
  let clues = 81;
  for (const i of shuffle([...Array(81).keys()], rng)) {
    if (clues <= target) break;
    const keep = at(puzzle, i);
    puzzle[i] = 0;
    if (countSolutions(puzzle, 2) !== 1) puzzle[i] = keep;
    else clues--;
  }
  return { puzzle, solution };
}

/** Celle in conflitto con altre (per evidenziare gli errori). @param {Grid} g @returns {Set<number>} */
export function conflicts(g) {
  const out = new Set();
  for (let i = 0; i < 81; i++) {
    const v = at(g, i);
    if (v !== 0 && !canPlace(g, i, v)) out.add(i);
  }
  return out;
}

/** @param {Grid} g */
export function isSolved(g) {
  return g.every((v) => v !== 0) && conflicts(g).size === 0;
}
