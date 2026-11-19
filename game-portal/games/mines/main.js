import { sdk, stopwatch, store } from "../sdk/sdk.js";
import { LEVELS, chord, createBoard, flagsLeft, reveal, toggleFlag } from "./logic.js";

const $ = (/** @type {string} */ id) => /** @type {HTMLElement} */ (document.getElementById(id));
const boardEl = $("board");
const levelEl = /** @type {HTMLSelectElement} */ ($("level"));
const flagModeEl = $("flag-mode");
const msgEl = $("message");
const timer = stopwatch();
const rng = Math.random;

/** @type {keyof typeof LEVELS} */
let level = /** @type {keyof typeof LEVELS} */ (store.get("mines.level") ?? "easy");
if (!(level in LEVELS)) level = "easy";
levelEl.value = level;
let board = createBoard(LEVELS[level].rows, LEVELS[level].cols, LEVELS[level].mines);
let flagMode = false;
/** @type {number | undefined} */
let tick;

function newGame() {
  const L = LEVELS[level];
  board = createBoard(L.rows, L.cols, L.mines);
  timer.reset();
  clearInterval(tick);
  $("time").textContent = "0:00";
  msgEl.textContent = "";
  msgEl.className = "message";
  render(true);
}

function fmt(/** @type {number} */ s) {
  const t = Math.floor(s);
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
}

function render(rebuild = false) {
  const size = Math.max(22, Math.min(36, Math.floor((Math.min(window.innerWidth, 900) - 32) / board.cols) - 2));
  boardEl.style.setProperty("--size", `${size}px`);
  boardEl.style.gridTemplateColumns = `repeat(${board.cols}, ${size}px)`;
  if (rebuild) {
    boardEl.replaceChildren(
      ...board.cells.map((_, i) => {
        const b = document.createElement("button");
        b.type = "button";
        b.dataset.i = String(i);
        b.setAttribute("role", "gridcell");
        return b;
      }),
    );
  }
  board.cells.forEach((c, i) => {
    const b = /** @type {HTMLButtonElement} */ (boardEl.children[i]);
    b.className = c.open ? (c.mine ? "open mine" : "open") : "";
    b.textContent = c.open ? (c.mine ? "✹" : c.near ? String(c.near) : "") : c.flag ? "🚩" : "";
    b.dataset.n = c.open && !c.mine ? String(c.near) : "";
    const r = Math.floor(i / board.cols) + 1;
    const col = (i % board.cols) + 1;
    const state = c.open ? (c.mine ? "mine" : c.near ? `${c.near} mines nearby` : "empty") : c.flag ? "flagged" : "hidden";
    b.setAttribute("aria-label", `Row ${r}, column ${col}: ${state}`);
  });
  $("flags").textContent = String(flagsLeft(board));
}

function finish() {
  clearInterval(tick);
  const secs = timer.seconds();
  const won = board.state === "won";
  msgEl.textContent = won ? `Cleared in ${fmt(secs)}!` : "Boom! Try again.";
  msgEl.className = `message ${won ? "win" : "lose"}`;
  sdk.complete(won, secs);
}

function act(/** @type {number} */ i, /** @type {boolean} */ flag) {
  if (board.state !== "playing") return;
  if (!timer.running()) {
    timer.start();
    tick = window.setInterval(() => { $("time").textContent = fmt(timer.seconds()); }, 500);
  }
  const c = board.cells[i];
  if (!c) return;
  if (flag) toggleFlag(board, i);
  else if (c.open) chord(board, i, rng);
  else reveal(board, i, rng);
  render();
  if (board.state !== "playing") finish();
}

boardEl.addEventListener("click", (e) => {
  const t = /** @type {HTMLElement} */ (e.target).closest("button");
  if (t?.dataset.i) act(Number(t.dataset.i), flagMode);
});
boardEl.addEventListener("contextmenu", (e) => {
  e.preventDefault();
  const t = /** @type {HTMLElement} */ (e.target).closest("button");
  if (t?.dataset.i) act(Number(t.dataset.i), true);
});
boardEl.addEventListener("keydown", (e) => {
  const t = /** @type {HTMLElement} */ (e.target).closest("button");
  if (t?.dataset.i && (e.key === "f" || e.key === "F")) act(Number(t.dataset.i), true);
});
flagModeEl.addEventListener("click", () => {
  flagMode = !flagMode;
  flagModeEl.setAttribute("aria-pressed", String(flagMode));
});
levelEl.addEventListener("change", () => {
  level = /** @type {keyof typeof LEVELS} */ (levelEl.value);
  store.set("mines.level", level);
  newGame();
});
$("new").addEventListener("click", newGame);
window.addEventListener("resize", () => render());

newGame();
sdk.ready();
