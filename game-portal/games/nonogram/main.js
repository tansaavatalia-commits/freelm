import { sdk, stopwatch, store } from "../sdk/sdk.js";
import { mulberry32, utcDay } from "../sdk/random.js";
import { daily, generate, isSolved, lineClues, rows, cols } from "./logic.js";

const $ = (/** @type {string} */ id) => /** @type {HTMLElement} */ (document.getElementById(id));
const board = /** @type {HTMLTableElement} */ ($("board"));
const modeEl = /** @type {HTMLSelectElement} */ ($("mode"));
const markEl = $("mark");
const msgEl = $("message");
const timer = stopwatch();

let size = 10;
/** @type {{ rows: number[][], cols: number[][] }} */ let target = { rows: [], cols: [] };
/** @type {(0 | 1)[]} */ let cells = [];
/** @type {boolean[]} */ let marks = [];
let markMode = false;
let done = false;
/** @type {number | undefined} */ let tick;
const fmt = (/** @type {number} */ s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

const savedMode = store.get("nonogram.mode");
if (typeof savedMode === "string" && [...modeEl.options].some((o) => o.value === savedMode)) modeEl.value = savedMode;

function newGame() {
  const mode = modeEl.value;
  size = mode === "daily" ? 10 : Number(mode);
  const p = mode === "daily" ? daily(utcDay(), size) : generate(mulberry32((Math.random() * 2 ** 32) >>> 0), size);
  target = p.clues;
  cells = new Array(size * size).fill(0);
  marks = new Array(size * size).fill(false);
  done = false;
  timer.reset();
  timer.start();
  clearInterval(tick);
  tick = window.setInterval(() => { $("time").textContent = fmt(timer.seconds()); }, 500);
  msgEl.textContent = mode === "daily" ? `Daily puzzle — ${utcDay()}` : "";
  msgEl.className = "message";
  build();
  render();
}

function build() {
  const s = Math.max(18, Math.min(30, Math.floor((Math.min(window.innerWidth, 700) - 120) / size)));
  board.style.setProperty("--s", `${s}px`);
  const head = document.createElement("tr");
  head.append(document.createElement("th"));
  target.cols.forEach((cl, c) => {
    const th = document.createElement("th");
    th.className = "col";
    th.dataset.c = String(c);
    th.innerHTML = "";
    cl.forEach((n, k) => { if (k) th.append(document.createElement("br")); th.append(String(n)); });
    head.append(th);
  });
  const trs = target.rows.map((cl, r) => {
    const tr = document.createElement("tr");
    if (r % 5 === 4 && r !== size - 1) tr.className = "b5";
    const th = document.createElement("th");
    th.className = "row";
    th.dataset.r = String(r);
    th.textContent = cl.join(" ");
    tr.append(th);
    for (let c = 0; c < size; c++) {
      const td = document.createElement("td");
      if (c % 5 === 4 && c !== size - 1) td.className = "b5";
      const b = document.createElement("button");
      b.type = "button";
      b.dataset.i = String(r * size + c);
      td.append(b);
      tr.append(td);
    }
    return tr;
  });
  board.replaceChildren(head, ...trs);
}

function render() {
  board.querySelectorAll("td button").forEach((el) => {
    const b = /** @type {HTMLButtonElement} */ (el);
    const i = Number(b.dataset.i);
    const filled = cells[i] === 1;
    b.className = filled ? "fill" : "";
    b.textContent = !filled && marks[i] ? "✕" : "";
    b.setAttribute("aria-label", `Row ${Math.floor(i / size) + 1}, column ${(i % size) + 1}: ${filled ? "filled" : marks[i] ? "marked empty" : "blank"}`);
  });
  rows(cells, size).forEach((line, r) => {
    board.querySelector(`th[data-r="${r}"]`)?.classList.toggle("ok", lineClues(line).join() === (target.rows[r] ?? []).join());
  });
  cols(cells, size).forEach((line, c) => {
    board.querySelector(`th[data-c="${c}"]`)?.classList.toggle("ok", lineClues(line).join() === (target.cols[c] ?? []).join());
  });
}

function act(/** @type {number} */ i, /** @type {boolean} */ mark) {
  if (done) return;
  if (mark) { marks[i] = !marks[i]; if (marks[i]) cells[i] = 0; }
  else { cells[i] = cells[i] ? 0 : 1; if (cells[i]) marks[i] = false; }
  render();
  if (isSolved(cells, size, target)) {
    done = true;
    clearInterval(tick);
    const secs = timer.seconds();
    msgEl.textContent = `Solved in ${fmt(secs)}!`;
    msgEl.className = "message win";
    sdk.complete(true, secs);
  }
}

board.addEventListener("click", (e) => {
  const t = /** @type {HTMLElement} */ (e.target).closest("button");
  if (t?.dataset.i) act(Number(t.dataset.i), markMode);
});
board.addEventListener("contextmenu", (e) => {
  const t = /** @type {HTMLElement} */ (e.target).closest("button");
  if (t?.dataset.i) { e.preventDefault(); act(Number(t.dataset.i), true); }
});
markEl.addEventListener("click", () => {
  markMode = !markMode;
  markEl.setAttribute("aria-pressed", String(markMode));
});
modeEl.addEventListener("change", () => { store.set("nonogram.mode", modeEl.value); newGame(); });
$("new").addEventListener("click", newGame);

newGame();
sdk.ready();
