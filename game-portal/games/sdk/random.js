// RNG deterministico (mulberry32) per puzzle riproducibili e "puzzle del giorno".

/** @param {number} seed @returns {() => number} numeri in [0, 1) */
export function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Hash FNV-1a a 32 bit di una stringa (es. "2026-11-19"). @param {string} s */
export function hashString(s) {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

/** Fisher-Yates in place. @template T @param {T[]} arr @param {() => number} rng @returns {T[]} */
export function shuffle(arr, rng) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    const tmp = /** @type {T} */ (arr[i]);
    arr[i] = /** @type {T} */ (arr[j]);
    arr[j] = tmp;
  }
  return arr;
}

/** Data UTC odierna YYYY-MM-DD. */
export function utcDay(now = new Date()) {
  return now.toISOString().slice(0, 10);
}
