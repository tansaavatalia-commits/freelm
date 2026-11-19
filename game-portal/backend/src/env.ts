export interface Env {
  DB: D1Database;
  /** Token admin (>= 32 caratteri). Temporaneo: sarà sostituito da passkey + MFA (FASE 7). */
  ADMIN_TOKEN?: string;
  /** "on" abilita il riempimento da rete pubblicitaria (D-015). */
  AD_NETWORK?: string;
}

export type AppEnv = { Bindings: Env };
