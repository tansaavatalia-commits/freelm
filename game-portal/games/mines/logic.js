// Mines: logica pura (nessun DOM). Prima mossa sempre sicura.

/**
 * @typedef {{ mine: boolean, open: boolean, flag: boolean, near: number }} Cell
 * @typedef {{ rows: number, cols: number, mines: number, cells: Cell[], placed: boolean,
 *             state: "playing" | "won" | "lost", opened: number }} Board
 */

export const LEVELS = {
  easy: { rows: 9, cols: 9, mines: 10 },
  medium: { rows: 16, cols: 16, mines: 40 },
  hard: { rows: 16, cols: 30, mines: 99 },
};

/** @param {number} rows @param {number} cols @param {number} mines @returns {Board} */
export function createBoard(rows, cols, mines) {
  if (mines >= rows * cols - 9) throw new Error("troppe mine per la griglia");
  const cells = Array.from({ length: rows * cols }, () => ({ mine: false, open: false, flag: false, near: 0 }));
  return { rows, cols, mines, cells, placed: false, state: "playing", opened: 0 };
}

/** @param {Board} b @param {number} i @returns {number[]} */
export function neighbors(b, i) {
  const r = Math.floor(i / b.cols);
  const c = i % b.cols;
  /** @type {number[]} */
  const out = [];
  for (let dr = -1; dr <= 1; dr++)
    for (let dc = -1; dc <= 1; dc++) {
      if (dr === 0 && dc === 0) continue;
      const rr = r + dr;
      const cc = c + dc;
      if (rr >= 0 && rr < b.rows && cc >= 0 && cc < b.cols) out.push(rr * b.cols + cc);
    }
  return out;
}

/** @param {Board} b @param {number} i @returns {Cell} */
function cell(b, i) {
  const c = b.cells[i];
  if (!c) throw new RangeError(`cella ${i} fuori griglia`);
  return c;
}

/** Piazza le mine evitando la cella `safe` e le sue vicine. @param {Board} b @param {number} safe @param {() => number} rng */
export function placeMines(b, safe, rng) {
  const forbidden = new Set([safe, ...neighbors(b, safe)]);
  const candidates = b.cells.map((_, i) => i).filter((i) => !forbidden.has(i));
  for (let k = 0; k < b.mines; k++) {
    const j = k + Math.floor(rng() * (candidates.length - k));
    const tmp = /** @type {number} */ (candidates[k]);
    candidates[k] = /** @type {number} */ (candidates[j]);
    candidates[j] = tmp;
    cell(b, /** @type {number} */ (candidates[k])).mine = true;
  }
  b.cells.forEach((c, i) => {
    c.near = neighbors(b, i).filter((n) => cell(b, n).mine).length;
  });
  b.placed = true;
}

/** Apre una cella (flood fill sugli zeri). @param {Board} b @param {number} i @param {() => number} rng */
export function reveal(b, i, rng) {
  if (b.state !== "playing") return;
  if (!b.placed) placeMines(b, i, rng);
  const start = cell(b, i);
  if (start.open || start.flag) return;
  if (start.mine) {
    start.open = true;
    b.state = "lost";
    b.cells.forEach((c) => { if (c.mine) c.open = true; });
    return;
  }
  const stack = [i];
  while (stack.length) {
    const k = /** @type {number} */ (stack.pop());
    const c = cell(b, k);
    if (c.open || c.flag) continue;
    c.open = true;
    b.opened++;
    if (c.near === 0) for (const n of neighbors(b, k)) if (!cell(b, n).open) stack.push(n);
  }
  if (b.opened === b.rows * b.cols - b.mines) {
    b.state = "won";
    b.cells.forEach((c) => { if (c.mine) c.flag = true; });
  }
}

/** Apertura rapida: se le bandierine vicine eguagliano il numero, apre le altre vicine. @param {Board} b @param {number} i @param {() => number} rng */
export function chord(b, i, rng) {
  const c = cell(b, i);
  if (b.state !== "playing" || !c.open || c.near === 0) return;
  const ns = neighbors(b, i);
  if (ns.filter((n) => cell(b, n).flag).length !== c.near) return;
  for (const n of ns) reveal(b, n, rng);
}

/** @param {Board} b @param {number} i */
export function toggleFlag(b, i) {
  const c = cell(b, i);
  if (b.state !== "playing" || c.open) return;
  c.flag = !c.flag;
}

/** @param {Board} b */
export function flagsLeft(b) {
  return b.mines - b.cells.filter((c) => c.flag).length;
}
