import { sdk, stopwatch, store } from "../sdk/sdk.js";
import { DIFFICULTY, conflicts, generate, isSolved } from "./logic.js";

const $ = (/** @type {string} */ id) => /** @type {HTMLElement} */ (document.getElementById(id));
const gridEl = $("grid");
const levelEl = /** @type {HTMLSelectElement} */ ($("level"));
const notesEl = $("notes");
const msgEl = $("message");
const timer = stopwatch();

/** @type {keyof typeof DIFFICULTY} */
let level = /** @type {keyof typeof DIFFICULTY} */ (store.get("sudoku.level") ?? "easy");
if (!(level in DIFFICULTY)) level = "easy";
levelEl.value = level;

/** @type {number[]} */ let puzzle = [];
/** @type {number[]} */ let values = [];
/** @type {Set<number>[]} */ let notes = [];
let sel = 0;
let noteMode = false;
let done = false;
/** @type {number | undefined} */ let tick;

const fmt = (/** @type {number} */ s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

function newGame() {
  ({ puzzle } = generate(Math.random, level));
  values = puzzle.slice();
  notes = Array.from({ length: 81 }, () => new Set());
  sel = puzzle.findIndex((v) => v === 0);
  done = false;
  timer.reset();
  timer.start();
  clearInterval(tick);
  tick = window.setInterval(() => { $("time").textContent = fmt(timer.seconds()); }, 500);
  msgEl.textContent = "";
  msgEl.className = "message";
  build();
  render();
}

function build() {
  gridEl.replaceChildren(
    ...values.map((_, i) => {
      const b = document.createElement("button");
      b.type = "button";
      b.dataset.i = String(i);
      b.setAttribute("role", "gridcell");
      const c = i % 9;
      const r = Math.floor(i / 9);
      if (c === 2 || c === 5) b.classList.add("br");
      if (r === 2 || r === 5) b.classList.add("bb");
      return b;
    }),
  );
}

function render() {
  const bad = conflicts(values);
  const sr = Math.floor(sel / 9);
  const sc = sel % 9;
  const selVal = values[sel] ?? 0;
  values.forEach((v, i) => {
    const b = /** @type {HTMLButtonElement} */ (gridEl.children[i]);
    const r = Math.floor(i / 9);
    const c = i % 9;
    const peer = r === sr || c === sc || (Math.floor(r / 3) === Math.floor(sr / 3) && Math.floor(c / 3) === Math.floor(sc / 3));
    b.classList.toggle("given", puzzle[i] !== 0);
    b.classList.toggle("user", puzzle[i] === 0 && v !== 0);
    b.classList.toggle("sel", i === sel);
    b.classList.toggle("peer", peer && i !== sel);
    b.classList.toggle("same", selVal !== 0 && v === selVal && i !== sel);
    b.classList.toggle("bad", bad.has(i) && puzzle[i] === 0);
    b.tabIndex = i === sel ? 0 : -1;
    const ns = notes[i] ?? new Set();
    if (v === 0 && ns.size) {
      const box = document.createElement("span");
      box.className = "notes";
      for (let n = 1; n <= 9; n++) box.append(Object.assign(document.createElement("span"), { textContent: ns.has(n) ? String(n) : "" }));
      b.replaceChildren(box);
    } else b.textContent = v ? String(v) : "";
    b.setAttribute("aria-label", `Row ${r + 1}, column ${c + 1}: ${v ? v : "empty"}${puzzle[i] ? " (given)" : ""}`);
  });
}

function input(/** @type {number} */ v) {
  if (done || puzzle[sel] !== 0) return;
  if (noteMode && v !== 0) {
    const ns = /** @type {Set<number>} */ (notes[sel]);
    if (ns.has(v)) ns.delete(v); else ns.add(v);
  } else {
    values[sel] = values[sel] === v ? 0 : v;
    if (v !== 0) {
      // rimuove la nota v da riga, colonna e riquadro
      const r = Math.floor(sel / 9), c = sel % 9;
      notes.forEach((ns, i) => {
        const rr = Math.floor(i / 9), cc = i % 9;
        if (rr === r || cc === c || (Math.floor(rr / 3) === Math.floor(r / 3) && Math.floor(cc / 3) === Math.floor(c / 3))) ns.delete(v);
      });
    }
  }
  render();
  if (isSolved(values)) {
    done = true;
    clearInterval(tick);
    const secs = timer.seconds();
    msgEl.textContent = `Solved in ${fmt(secs)}!`;
    msgEl.className = "message win";
    sdk.complete(true, secs);
  }
}

function focusSel() {
  render();
  /** @type {HTMLElement} */ (gridEl.children[sel]).focus();
}

gridEl.addEventListener("click", (e) => {
  const t = /** @type {HTMLElement} */ (e.target).closest("button");
  if (t?.dataset.i) { sel = Number(t.dataset.i); render(); }
});
gridEl.addEventListener("keydown", (e) => {
  const moves = { ArrowUp: -9, ArrowDown: 9, ArrowLeft: -1, ArrowRight: 1 };
  if (e.key in moves) {
    e.preventDefault();
    const d = moves[/** @type {keyof typeof moves} */ (e.key)];
    const next = sel + d;
    if (next >= 0 && next < 81 && !(Math.abs(d) === 1 && Math.floor(next / 9) !== Math.floor(sel / 9))) sel = next;
    focusSel();
  } else if (/^[1-9]$/.test(e.key)) input(Number(e.key));
  else if (e.key === "Backspace" || e.key === "Delete" || e.key === "0") input(0);
  else if (e.key === "n" || e.key === "N") notesEl.click();
});

const pad = $("pad");
for (let n = 1; n <= 9; n++) {
  const b = document.createElement("button");
  b.type = "button";
  b.textContent = String(n);
  b.addEventListener("click", () => input(n));
  pad.append(b);
}
const erase = document.createElement("button");
erase.type = "button";
erase.textContent = "⌫";
erase.setAttribute("aria-label", "Erase");
erase.addEventListener("click", () => input(0));
pad.append(erase);

notesEl.addEventListener("click", () => {
  noteMode = !noteMode;
  notesEl.setAttribute("aria-pressed", String(noteMode));
});
levelEl.addEventListener("change", () => {
  level = /** @type {keyof typeof DIFFICULTY} */ (levelEl.value);
  store.set("sudoku.level", level);
  newGame();
});
$("new").addEventListener("click", newGame);

newGame();
sdk.ready();
