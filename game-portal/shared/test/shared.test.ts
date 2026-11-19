import { describe, expect, it } from "vitest";
import { canPublish, daysToExpiry, parseGameMessage, PROTOCOL, validateManifest, type LicenseRecord } from "../src";

const good = {
  slug: "mines",
  title: "Mines",
  version: "1.0.0",
  category: "logic",
  tags: ["classic"],
  description: "Trova le mine.",
  aspect: "1:1",
  usesStorage: true,
  license: { type: "internal", rightsHolder: "Tabluo", thirdPartyAssets: [] },
};

describe("validateManifest", () => {
  it("accetta un manifest valido", () => expect(validateManifest(good)).toEqual([]));
  it("rifiuta slug, versione e categoria non validi", () => {
    const errs = validateManifest({ ...good, slug: "Bad Slug", version: "1.0", category: "casino" });
    expect(errs.some((e) => e.startsWith("slug"))).toBe(true);
    expect(errs.some((e) => e.startsWith("version"))).toBe(true);
    expect(errs.some((e) => e.startsWith("category"))).toBe(true);
  });
  it("richiede la licenza e lo SPDX per l'open source", () => {
    expect(validateManifest({ ...good, license: undefined })).toContain("license: obbligatoria");
    expect(validateManifest({ ...good, license: { ...good.license, type: "open_source" } })).toContain(
      "license.spdx obbligatorio per open source",
    );
  });
  it("rifiuta input non oggetto", () => expect(validateManifest(null)).toHaveLength(1));
});

const lic: LicenseRecord = {
  approvalStatus: "approved",
  hostingRights: true,
  monetizationRights: true,
  startDate: "2026-01-01",
  endDate: null,
  territory: "WORLD",
};

describe("canPublish", () => {
  it("consente una licenza approvata e valida", () => expect(canPublish(lic, "2026-11-19").ok).toBe(true));
  it("blocca senza licenza", () => expect(canPublish(null, "2026-11-19").ok).toBe(false));
  it("blocca stato non approvato, diritti mancanti, scadenza e territorio", () => {
    const r = canPublish(
      { ...lic, approvalStatus: "under_review", hostingRights: false, endDate: "2026-11-18", territory: "HR" },
      "2026-11-19",
    );
    expect(r.ok).toBe(false);
    expect(r.reasons).toHaveLength(4);
  });
  it("blocca prima della data di inizio", () => expect(canPublish({ ...lic, startDate: "2027-01-01" }, "2026-11-19").ok).toBe(false));
  it("calcola i giorni alla scadenza", () => {
    expect(daysToExpiry({ endDate: "2026-12-19" }, "2026-11-19")).toBe(30);
    expect(daysToExpiry({ endDate: null }, "2026-11-19")).toBeNull();
  });
});

describe("parseGameMessage", () => {
  it("accetta i messaggi del protocollo", () => {
    expect(parseGameMessage({ protocol: PROTOCOL, type: "ready" })).toEqual({ protocol: PROTOCOL, type: "ready" });
    expect(parseGameMessage({ protocol: PROTOCOL, type: "score", value: 12.7 })).toMatchObject({ value: 12 });
    expect(parseGameMessage({ protocol: PROTOCOL, type: "complete", won: true, seconds: 61.4 })).toMatchObject({ seconds: 61 });
  });
  it("rifiuta protocolli, tipi e valori estranei", () => {
    expect(parseGameMessage({ protocol: "x", type: "ready" })).toBeNull();
    expect(parseGameMessage({ protocol: PROTOCOL, type: "steal-cookies" })).toBeNull();
    expect(parseGameMessage({ protocol: PROTOCOL, type: "score", value: Number.NaN })).toBeNull();
    expect(parseGameMessage({ protocol: PROTOCOL, type: "complete", won: true, seconds: -1 })).toBeNull();
    expect(parseGameMessage("ready")).toBeNull();
  });
  it("tronca i messaggi di errore lunghi", () => {
    const m = parseGameMessage({ protocol: PROTOCOL, type: "error", message: "x".repeat(500) });
    expect(m && m.type === "error" && m.message.length).toBe(200);
  });
});
