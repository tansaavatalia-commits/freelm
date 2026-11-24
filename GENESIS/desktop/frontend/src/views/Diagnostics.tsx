import { api, usePolling } from "../api";
import type { AuditResponse, Backup, Check, Doctor } from "../types";
import { Badge, Card, Empty, ErrorBanner, Facts, formatDate, gb, Loading, PageHeader } from "../ui";

const CHECK_TONE: Record<Check["status"], "ok" | "warn" | "bad"> = { ok: "ok", warn: "warn", fail: "bad" };
const CHECK_LABEL: Record<Check["status"], string> = { ok: "OK", warn: "Attenzione", fail: "Errore" };

export function Diagnostics() {
  const doctor = usePolling(() => api<Doctor>("/api/doctor"), 0);
  const audit = usePolling(() => api<AuditResponse>("/api/audit?n=50"), 5000);
  const backups = usePolling(() => api<Backup[]>("/api/backups"), 5000);
  const hw = doctor.data?.hardware;

  return (
    <>
      <PageHeader title="Diagnostica" subtitle="Controlli di salute, hardware rilevato e registro di audit." />
      <ErrorBanner message={doctor.error ?? audit.error ?? backups.error} />
      <div className="grid grid-2">
        <Card title="Controlli" actions={<button type="button" className="button button-small" onClick={doctor.refresh}>Ripeti</button>}>
          {!doctor.data ? <Loading /> : (
            <ul className="checks">
              {doctor.data.checks.map((c) => (
                <li key={c.check}>
                  <Badge tone={CHECK_TONE[c.status]}>{CHECK_LABEL[c.status]}</Badge>
                  <div>
                    <p className="strong">{c.check}</p>
                    <p className="note">{c.detail}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Hardware rilevato">
          {!hw ? <Loading /> : (
            <>
              <Facts rows={[
                ["Sistema", `${hw.os_name} ${hw.os_release} (${hw.os_version})`],
                ["Architettura", hw.machine],
                ["Processore", hw.cpu_model ?? "non rilevato"],
                ["Thread logici", hw.cpu_logical ?? "?"],
                ["RAM", `${gb(hw.ram_total_mb)} totali`],
                ["Disco", hw.disk_total_gb != null ? `${hw.disk_free_gb} GB liberi su ${hw.disk_total_gb} GB` : "non rilevato"],
                ["GPU", hw.gpus == null ? "non rilevata" : hw.gpus.length === 0 ? "nessuna"
                  : hw.gpus.map((g) => (g.vram_mb ? `${g.name} (${g.vram_mb} MB)` : g.name)).join(", ")],
                ["Profilo", `${doctor.data?.profile} — ${doctor.data?.profile_reason}`],
              ]} />
              {hw.notes.map((n) => <p key={n} className="note">Nota: {n}</p>)}
            </>
          )}
        </Card>
      </div>

      <Card
        title="Registro di audit"
        actions={audit.data && (
          <Badge tone={audit.data.chain_ok ? "ok" : "bad"}>
            {audit.data.chain_ok ? `Catena integra · ${audit.data.total} voci` : `Catena interrotta alla voce ${audit.data.first_bad_seq}`}
          </Badge>
        )}
      >
        {!audit.data ? <Loading /> : audit.data.entries.length === 0 ? <Empty>Nessuna voce.</Empty> : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>#</th><th>Quando</th><th>Chi</th><th>Azione</th><th>Livello</th><th>Esito</th></tr>
              </thead>
              <tbody>
                {[...audit.data.entries].reverse().map((e) => (
                  <tr key={e.seq}>
                    <td>{e.seq}</td>
                    <td>{formatDate(e.ts)}</td>
                    <td className="mono">{e.principal}</td>
                    <td className="mono">{e.action}</td>
                    <td>{e.level ?? "—"}</td>
                    <td><Badge tone={e.outcome === "denied" ? "bad" : e.outcome === "pending" ? "info" : "ok"}>{e.outcome}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Backup">
        {!backups.data ? <Loading /> : backups.data.length === 0 ? (
          <Empty>Nessun backup. Puoi crearne uno dalla Dashboard.</Empty>
        ) : (
          <ul className="plain-list">
            {backups.data.map((b) => (
              <li key={b.name}><span className="mono">{b.name}</span> <span className="muted">{b.size_kb} KB</span></li>
            ))}
          </ul>
        )}
        <p className="note">Il ripristino si fa dalla riga di comando (genesis backup restore … --confirm): sostituisce tutti i dati.</p>
      </Card>
    </>
  );
}
