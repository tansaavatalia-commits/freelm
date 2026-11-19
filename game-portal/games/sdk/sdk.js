// Tabluo game SDK (protocollo "tabluo/1"). Unico canale tra gioco e portale.
// I messaggi non contengono dati personali, quindi targetOrigin "*" è accettabile:
// il portale valida comunque origine, sorgente e schema di ogni messaggio.

const PROTOCOL = "tabluo/1";

/** @param {Record<string, unknown>} msg */
function post(msg) {
  try {
    if (window.parent !== window) window.parent.postMessage({ protocol: PROTOCOL, ...msg }, "*");
  } catch {
    /* il gioco deve funzionare anche fuori dal portale */
  }
}

export const sdk = {
  ready: () => post({ type: "ready" }),
  /** @param {number} value */
  score: (value) => post({ type: "score", value }),
  /** @param {boolean} won @param {number} seconds */
  complete: (won, seconds) => post({ type: "complete", won, seconds }),
  /** @param {string} message */
  error: (message) => post({ type: "error", message: String(message).slice(0, 200) }),
};

window.addEventListener("error", (e) => sdk.error(e.message || "error"));

/** localStorage protetto: nel sandbox senza allow-same-origin lancia eccezioni. */
export const store = {
  /** @param {string} key @returns {unknown} */
  get(key) {
    try {
      const v = window.localStorage.getItem(key);
      return v === null ? null : JSON.parse(v);
    } catch {
      return null;
    }
  },
  /** @param {string} key @param {unknown} value */
  set(key, value) {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* ignorato */
    }
  },
};

/** Cronometro semplice per la durata della partita. */
export function stopwatch() {
  let start = 0;
  return {
    start() { start = performance.now(); },
    seconds() { return start ? (performance.now() - start) / 1000 : 0; },
    running() { return start !== 0; },
    reset() { start = 0; },
  };
}
