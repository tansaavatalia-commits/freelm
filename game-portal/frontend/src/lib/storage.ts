// Preferiti e cronologia SOLO nel browser dell'utente (nessun account, nessun invio al server).

const FAV = "tabluo.favorites";
const HIST = "tabluo.history";
const MAX_HISTORY = 30;

function read(key: string): string[] {
  try {
    const v: unknown = JSON.parse(window.localStorage.getItem(key) ?? "[]");
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function write(key: string, value: string[]) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage non disponibile (navigazione privata): funziona comunque senza memoria */
  }
}

export const favorites = {
  list: () => read(FAV),
  has: (slug: string) => read(FAV).includes(slug),
  toggle(slug: string): boolean {
    const cur = read(FAV);
    const on = !cur.includes(slug);
    write(FAV, on ? [slug, ...cur] : cur.filter((s) => s !== slug));
    return on;
  },
};

export const history = {
  list: () => read(HIST),
  add(slug: string) {
    write(HIST, [slug, ...read(HIST).filter((s) => s !== slug)].slice(0, MAX_HISTORY));
  },
  clear: () => write(HIST, []),
};
