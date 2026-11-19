/** Origin separato da cui vengono serviti i giochi (isolamento: nessun cookie del portale). */
export const GAMES_ORIGIN: string = (import.meta.env.VITE_GAMES_ORIGIN as string | undefined) ?? "http://localhost:5174";
/** Base dell'API; vuoto = stesso origin (proxy in sviluppo, routing Pages/Worker in produzione). */
export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";
