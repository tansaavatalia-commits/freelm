import { useState } from "react";
import { api, errorText } from "../api";
import { navigate } from "../router";
import { TASK_STATUSES, type Status, type Task } from "../types";
import { Badge, Card, ErrorBanner, Facts, gb, Loading, Meter, STATUS_LABEL } from "../ui";

export function Dashboard({
  status,
  error,
  refresh,
}: {
  status: Status | null;
  error: string | null;
  refresh: () => Promise<void>;
}) {
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!status) return error ? <ErrorBanner message={error} /> : <Loading />;
  const hw = status.hardware;
  const mem = status.memory;
  const usedRam = mem.ram_total_mb != null && mem.ram_available_mb != null ? mem.ram_total_mb - mem.ram_available_mb : null;
  const gpus = hw.gpus == null ? "non rilevata" : hw.gpus.length === 0 ? "nessuna" : hw.gpus.map((g) => g.name).join(", ");

  async function backup() {
    setBusy(true);
    setActionError(null);
    try {
      await api<Task>("/api/tasks", { body: { kind: "memory.backup" } });
      setNotice("Backup messo in coda: lo trovi in Compiti tra pochi secondi.");
      await refresh();
    } catch (e) {
      setActionError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <section className="hero">
        <div className="hero-glow" aria-hidden="true" />
        <p className="hero-kicker">Piattaforma di intelligenza estensibile</p>
        <h1 className="hero-title">GÉNESIS</h1>
        <div className="hero-chips">
          <Badge tone="accent">Profilo {status.profile}</Badge>
          <Badge tone={status.worker_running ? "ok" : "bad"}>
            {status.worker_running ? "Esecutore dei compiti attivo" : "Esecutore dei compiti fermo"}
          </Badge>
          <Badge tone={status.audit_chain_ok ? "ok" : "bad"}>
            Audit {status.audit_chain_ok ? "integro" : "da verificare"}
          </Badge>
        </div>
      </section>
      <ErrorBanner message={error ?? actionError} />
      {notice && <div className="banner banner-ok" role="status">{notice}</div>}

      <div className="grid">
        <Card title="Memoria">
          <p className="figure">{usedRam != null ? gb(usedRam) : "—"} <span>usati su {gb(mem.ram_total_mb)}</span></p>
          {usedRam != null && mem.ram_total_mb != null && <Meter used={usedRam} total={mem.ram_total_mb} label="RAM in uso" />}
          <p className="note">GÉNESIS ora usa {mem.process_rss_mb != null ? `${mem.process_rss_mb} MB` : "una quantità non rilevabile"} di RAM.</p>
        </Card>

        <Card title="Disco">
          {hw.disk_total_gb != null && hw.disk_free_gb != null ? (
            <>
              <p className="figure">{hw.disk_free_gb} GB <span>liberi su {hw.disk_total_gb} GB</span></p>
              <Meter used={hw.disk_total_gb - hw.disk_free_gb} total={hw.disk_total_gb} label="Disco in uso" />
            </>
          ) : (
            <p className="figure">non rilevato</p>
          )}
          <p className="note">Dati in {status.home}</p>
        </Card>

        <Card title="Profilo di esecuzione">
          <p className="figure">{status.profile}</p>
          <p className="note">{status.profile_reason}</p>
          <Facts rows={[
            ["Compiti in parallelo", status.profile_details.max_workers],
            ["Chiamate IA in parallelo", status.profile_details.max_parallel_online],
            ["Modelli locali", status.profile_details.local_models ? "consentiti" : "disattivati"],
          ]} />
        </Card>

        <Card title="Compiti" actions={<a className="link" href="#/compiti">Apri</a>}>
          <ul className="counts">
            {TASK_STATUSES.map((s) => (
              <li key={s}>
                <button type="button" className="count-button" onClick={() => navigate("compiti", { stato: s })}>
                  <strong>{status.tasks[s]}</strong>
                  <span>{STATUS_LABEL[s]}</span>
                </button>
              </li>
            ))}
          </ul>
          {status.recovered_at_start > 0 && (
            <p className="note">{status.recovered_at_start} compiti interrotti sono stati ripresi all'avvio.</p>
          )}
        </Card>

        <Card title="Sicurezza" actions={<a className="link" href="#/diagnostica">Registro</a>}>
          <Facts rows={[
            ["Voci di audit", status.audit_entries],
            ["Catena di audit", status.audit_chain_ok ? "integra" : `interrotta alla voce ${status.audit_first_bad_seq}`],
            ["Approvazioni in attesa", status.pending_approvals],
          ]} />
          {status.pending_approvals > 0 && (
            <button type="button" className="button" onClick={() => navigate("approvazioni")}>Decidi ora</button>
          )}
        </Card>

        <Card title="Dati">
          <Facts rows={[
            ["Progetti attivi", status.projects],
            ["Backup", status.backups],
            ["Schema del database", `v${status.schema_version}`],
          ]} />
          <button type="button" className="button" onClick={backup} disabled={busy}>
            {busy ? "Invio…" : "Crea un backup"}
          </button>
        </Card>

        <Card title="Sistema">
          <Facts rows={[
            ["Sistema operativo", `${hw.os_name} ${hw.os_release}`],
            ["Processore", `${hw.cpu_model ?? "non rilevato"} · ${hw.cpu_logical ?? "?"} thread`],
            ["GPU", gpus],
            ["Python", hw.python],
          ]} />
        </Card>

        <Card title="Intelligenza artificiale">
          <p className="figure">Nessun provider</p>
          <p className="note">
            Il router dei modelli arriva nella Fase 3. Finché un provider non è verificato come gratuito resta
            disattivato.
          </p>
        </Card>
      </div>
    </>
  );
}
