import { sdk, stopwatch, store } from "../sdk/sdk.js";
import { RANKS, SUITS, isRed, spoken } from "../sdk/cards.js";
import { autoFinish, canAutoFinish, clone, deal, drawCards, isWon, move, pick, toFoundation } from "./logic.js";

/** @typedef {import("./logic.js").State} State @typedef {import("./logic.js").Loc} Loc @typedef {import("../sdk/cards.js").Card} Card */

const $ = (/** @type {string} */ id) => /** @type {HTMLElement} */ (document.getElementById(id));
const drawEl = /** @type {HTMLSelectElement} */ ($("draw"));
const msgEl = $("message");
const undoEl = /** @type {HTMLButtonElement} */ ($("undo"));
const autoEl = /** @type {HTMLButtonElement} */ ($("auto"));
const timer = stopwatch();

const savedDraw = store.get("klondike.draw");
drawEl.value = savedDraw === 3 ? "3" : "1";

/** @type {State} */ let s = deal(Math.random, drawEl.value === "3" ? 3 : 1);
/** @type {State[]} */ let history = [];
/** @type {Loc | null} */ let sel = null;
let done = false;
/** @type {number | undefined} */ let tick;
const fmt = (/** @type {number} */ x) => `${Math.floor(x / 60)}:${String(Math.floor(x % 60)).padStart(2, "0")}`;

function newGame() {
  s = deal(Math.random, drawEl.value === "3" ? 3 : 1);
  history = [];
  sel = null;
  done = false;
  timer.reset();
  clearInterval(tick);
  $("time").textContent = "0:00";
  msgEl.textContent = "";
  msgEl.className = "message";
  render();
}

function startClock() {
  if (timer.running()) return;
  timer.start();
  tick = window.setInterval(() => { $("time").textContent = fmt(timer.seconds()); }, 500);
}

/** Esegue un'azione che modifica lo stato, con undo. @param {(st: State) => boolean} fn */
function act(fn) {
  if (done) return false;
  const before = clone(s);
  if (!fn(s)) return false;
  history.push(before);
  if (history.length > 200) history.shift();
  startClock();
  sel = null;
  render();
  if (isWon(s)) {
    done = true;
    clearInterval(tick);
    const secs = timer.seconds();
    msgEl.textContent = `You won in ${s.moves} moves and ${fmt(secs)}!`;
    msgEl.className = "message win";
    sdk.complete(true, secs);
  }
  return true;
}

/** @param {Card} c @param {boolean} selected */
function cardEl(c, selected) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = `card${c.up ? (isRed(c) ? " red" : "") : " down"}${selected ? " sel" : ""}`;
  if (c.up) {
    b.innerHTML = `<span>${RANKS[c.rank]}${SUITS[c.suit]}</span><span class="big">${SUITS[c.suit]}</span>`;
    b.setAttribute("aria-label", spoken(c));
  } else {
    b.setAttribute("aria-label", "Face-down card");
    b.tabIndex = -1;
  }
  return b;
}

/** @param {Loc | null} a @param {Loc} b */
const sameLoc = (a, b) => !!a && a.type === b.type && (a.type === "waste" || /** @type {any} */ (a).index === /** @type {any} */ (b).index);

function render() {
  const stock = $("stock");
  stock.classList.toggle("empty", s.stock.length === 0);
  stock.replaceChildren(...(s.stock.length ? [cardEl(s.stock[s.stock.length - 1] ?? { suit: 0, rank: 1, up: false }, false)] : []));
  stock.setAttribute("aria-label", s.stock.length ? `Stock, ${s.stock.length} cards. Draw.` : "Stock empty. Recycle waste.");

  const waste = $("waste");
  const shown = s.waste.slice(-Math.min(s.draw, 3));
  waste.replaceChildren(
    ...shown.map((c, i) => {
      const el = cardEl(c, i === shown.length - 1 && sel?.type === "waste");
      el.style.left = `calc(var(--cw) * ${i * 0.22})`;
      if (i === shown.length - 1) el.dataset.loc = JSON.stringify({ type: "waste" });
      else el.tabIndex = -1;
      return el;
    }),
  );

  document.querySelectorAll(".foundation").forEach((el) => {
    const f = Number(/** @type {HTMLElement} */ (el).dataset.f);
    const pile = s.foundations[f] ?? [];
    const t = pile[pile.length - 1];
    const kids = [];
    if (t) {
      const c = cardEl(t, sel?.type === "foundation" && sel.index === f);
      c.dataset.loc = JSON.stringify({ type: "foundation", index: f });
      kids.push(c);
    }
    el.replaceChildren(...kids);
    /** @type {HTMLElement} */ (el).dataset.drop = JSON.stringify({ type: "foundation", index: f });
  });

  const tab = $("tableau");
  tab.replaceChildren(
    ...s.tableau.map((col, ci) => {
      const div = document.createElement("div");
      div.className = col.length ? "col" : "col empty";
      div.dataset.drop = JSON.stringify({ type: "tableau", index: ci });
      div.setAttribute("aria-label", `Column ${ci + 1}`);
      col.forEach((c, k) => {
        const selected = sel?.type === "tableau" && sel.index === ci && (sel.card ?? col.length - 1) <= k;
        const el = cardEl(c, selected);
        el.style.top = `calc(${col.slice(0, k).reduce((acc, x) => acc + (x.up ? 1 : 0), 0)} * var(--peek) + ${col.slice(0, k).reduce((acc, x) => acc + (x.up ? 0 : 1), 0)} * var(--peek-down))`;
        if (c.up) el.dataset.loc = JSON.stringify({ type: "tableau", index: ci, card: k });
        div.append(el);
      });
      const ups = col.filter((c) => c.up).length;
      const downs = col.length - ups;
      div.style.height = col.length ? `calc(var(--ch) + ${Math.max(0, ups - 1)} * var(--peek) + ${downs} * var(--peek-down))` : "";
      return div;
    }),
  );

  $("moves").textContent = `${s.moves} moves`;
  undoEl.disabled = history.length === 0 || done;
  autoEl.hidden = done || !canAutoFinish(s);
}

/** @param {HTMLElement} el @returns {Loc | null} */
function locOf(el) {
  const raw = el.closest("[data-loc]")?.getAttribute("data-loc");
  return raw ? /** @type {Loc} */ (JSON.parse(raw)) : null;
}
/** @param {HTMLElement} el @returns {Loc | null} */
function dropOf(el) {
  const loc = locOf(el);
  if (loc && loc.type !== "waste") return loc.type === "tableau" ? { type: "tableau", index: loc.index } : loc;
  const raw = el.closest("[data-drop]")?.getAttribute("data-drop");
  return raw ? /** @type {Loc} */ (JSON.parse(raw)) : null;
}

$("table").addEventListener("click", (e) => {
  const target = /** @type {HTMLElement} */ (e.target);
  if (target.closest("#stock")) {
    act((st) => drawCards(st));
    return;
  }
  const loc = locOf(target);
  if (sel) {
    const dest = dropOf(target);
    if (dest && !sameLoc(sel, dest)) {
      const from = sel;
      if (act((st) => move(st, from, dest))) return;
    }
    // clic sulla stessa carta selezionata = prova la fondazione
    if (loc && sameLoc(sel, loc) && JSON.stringify(sel) === JSON.stringify(loc)) {
      const from = sel;
      sel = null;
      if (!act((st) => toFoundation(st, from))) render();
      return;
    }
    sel = loc && pick(s, loc).length ? loc : null;
    render();
    return;
  }
  if (loc && pick(s, loc).length) {
    sel = loc;
    render();
  }
});

$("table").addEventListener("dblclick", (e) => {
  const loc = locOf(/** @type {HTMLElement} */ (e.target));
  if (!loc) return;
  sel = null;
  act((st) => toFoundation(st, loc.type === "tableau" ? { type: "tableau", index: loc.index } : loc));
});

undoEl.addEventListener("click", () => {
  const prev = history.pop();
  if (!prev) return;
  s = prev;
  sel = null;
  render();
});
autoEl.addEventListener("click", () => act((st) => autoFinish(st) > 0));
drawEl.addEventListener("change", () => {
  store.set("klondike.draw", Number(drawEl.value));
  newGame();
});
$("new").addEventListener("click", newGame);
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "z") { e.preventDefault(); undoEl.click(); }
  if (e.key === "Escape") { sel = null; render(); }
});

newGame();
sdk.ready();
