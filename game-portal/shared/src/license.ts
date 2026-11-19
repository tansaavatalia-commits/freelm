/** Regola bloccante di pubblicazione (docs/LICENSE_MANAGEMENT.md). Pura: nessun I/O. */

export type ApprovalStatus = "draft" | "under_review" | "approved" | "rejected" | "expired" | "revoked";

export interface LicenseRecord {
  approvalStatus: ApprovalStatus;
  hostingRights: boolean;
  monetizationRights: boolean;
  /** ISO date (YYYY-MM-DD) o null se perpetua. */
  startDate: string;
  endDate: string | null;
  /** "WORLD" oppure codici ISO 3166-1 alpha-2 separati da virgola. */
  territory: string;
}

export interface PublishCheck {
  ok: boolean;
  reasons: string[];
}

/** `today` è una data ISO (YYYY-MM-DD) passata dall'esterno: la funzione resta deterministica. */
export function canPublish(lic: LicenseRecord | null, today: string): PublishCheck {
  if (!lic) return { ok: false, reasons: ["nessuna licenza registrata"] };
  const reasons: string[] = [];
  if (lic.approvalStatus !== "approved") reasons.push(`licenza in stato "${lic.approvalStatus}"`);
  if (!lic.hostingRights) reasons.push("diritti di hosting assenti");
  if (!lic.monetizationRights) reasons.push("diritti di monetizzazione assenti");
  if (lic.startDate > today) reasons.push(`licenza valida solo dal ${lic.startDate}`);
  if (lic.endDate !== null && lic.endDate < today) reasons.push(`licenza scaduta il ${lic.endDate}`);
  if (lic.territory.trim().toUpperCase() !== "WORLD") reasons.push("territorio non mondiale: serve geo-restrizione (non ancora supportata)");
  return { ok: reasons.length === 0, reasons };
}

/** Giorni mancanti alla scadenza (negativo = già scaduta, null = perpetua). */
export function daysToExpiry(lic: Pick<LicenseRecord, "endDate">, today: string): number | null {
  if (lic.endDate === null) return null;
  const ms = Date.parse(`${lic.endDate}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`);
  return Math.round(ms / 86_400_000);
}
