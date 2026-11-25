import { useState, type FormEvent } from "react";
import { api, errorText, usePolling, waitForTask } from "../api";
import type { ImprovableComponent, Proposal } from "../types";
import { Badge, Card, Empty, ErrorBanner, formatDate, Loading, PageHeader } from "../ui";

const STATUS: Record<Proposal["status"], { label: string; tone: "info" | "ok" | "bad" | "muted" | "accent" }> = {
  proposed: { label: "proposta", tone: "info" },
  evaluated: { label: "valutata", tone: "accent" },
  promoted: { label: "promossa", tone: "ok" },
  rejected: { label: "rifiutata", tone: "bad" },
  rolled_back: { label: "annullata", tone: "muted" },
};
const pct = (x: number | null | undefined) => (x == null ? "—" : `${(x * 100).toFixed(1)}%`);

export function Improvement() {
  const components = usePolling(() => api<ImprovableComponent[]>("/api/improvement/components"), 3000);
  const proposals = usePolling(() => api<Proposal[]>("/api/improvement/proposals"), 3000);
  const [error, setError] = useState<string | null>(null);
  const refresh = () => Promise.all([components.refresh(), proposals.refresh()]);

  async function act(path: string, question: string, body: unknown = {}) {
    if (!window.confirm(question)) return;
    setError(null);
    try {
      await api(path, { body });
      await refresh();
    } catch (e) {
      setError(errorText(e));
    }
  }

  return (
    <>
      <PageHeader title="Auto-miglioramento" subtitle="Una versione candidata diventa ufficiale solo con un miglioramento dimostrato nel laboratorio, nessun peggioramento dimostrato e la tua approvazione. Permessi, sicurezza e costi non sono modificabili." />
      <ErrorBanner message={error ?? components.error ?? proposals.error} />
      <Card title="Componenti migliorabili">
        {!components.data ? <Loading /> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Componente</th><th>Versione attiva</th><th>Benchmark</th><th /></tr></thead>
              <tbody>
                {components.data.map((c) => (
                  <tr key={c.name}>
                    <td><span className="strong">{c.name}</span><p className="note">{c.description}</p></td>
                    <td><Badge tone="accent">attiva {c.active}</Badge> <span className="muted">versioni: {c.versions.join(", ")}</span></td>
                    <td className="mono">{c.benchmarks.join(", ")}</td>
                    <td className="actions">
                      {c.previous && (
                        <button type="button" className="button button-small button-quiet"
                                onClick={() => act(`/api/improvement/components/${c.name}/rollback`, `Tornare a ${c.name}@${c.previous}?`)}>
                          Torna a {c.previous}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {components.data && <StartCycle components={components.data} onDone={refresh} onError={setError} />}
      <Card title="Proposte">
        {!proposals.data ? <Loading /> : proposals.data.length === 0 ? <Empty>Nessuna proposta. Avvia un ciclo qui sopra.</Empty> : (
          <ul className="approval-list">
            {proposals.data.map((p) => (
              <li key={p.id} className="approval">
                <div>
                  <p className="strong">{p.component}: {p.stable} → {p.candidate} <Badge tone={STATUS[p.status].tone}>{STATUS[p.status].label}</Badge></p>
                  <p className="note">{formatDate(p.created_at)} · {p.problem}</p>
                  <p className="note">Causa: {p.cause}</p>
                  {p.evaluation && (
                    <>
                      <div className="table-wrap">
                        <table>
                          <thead><tr><th>Benchmark</th><th>Stabile</th><th>Candidata</th><th>Verdetto</th></tr></thead>
                          <tbody>
                            {p.evaluation.results.map((r) => (
                              <tr key={r.dataset}><td className="mono">{r.dataset}</td><td>{pct(r.accuracy_stable)}</td><td>{pct(r.accuracy_candidate)}</td><td>{r.verdict}</td></tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      <div className={`banner ${p.evaluation.promotable ? "banner-ok" : "banner-info"}`}>
                        <p className="strong">Raccomandazione: {p.evaluation.recommendation}</p>
                        <p className="note">{p.evaluation.caveat}</p>
                      </div>
                    </>
                  )}
                  {p.decision && <p className="note">Decisione: {p.decision}</p>}
                </div>
                {p.status === "evaluated" && (
                  <div className="actions">
                    {p.evaluation?.promotable && (
                      <button type="button" className="button button-primary"
                              onClick={() => act(`/api/improvement/proposals/${p.id}/approve`, `Promuovere ${p.component}@${p.candidate}? Il router la userà subito.`)}>
                        Approva e promuovi
                      </button>
                    )}
                    <button type="button" className="button button-danger"
                            onClick={() => act(`/api/improvement/proposals/${p.id}/reject`, "Rifiutare la proposta?", { reason: "rifiutata dall'interfaccia" })}>
                      Rifiuta
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}

function StartCycle({ components, onDone, onError }: { components: ImprovableComponent[]; onDone: () => Promise<unknown>; onError: (m: string | null) => void }) {
  const [name, setName] = useState(components[0]?.name ?? "");
  const component = components.find((c) => c.name === name);
  const candidates = component?.versions.filter((v) => v !== component.active) ?? [];
  const [candidate, setCandidate] = useState("");
  const [busy, setBusy] = useState(false);
  const chosen = candidates.includes(candidate) ? candidate : candidates[0] ?? "";

  async function submit(event: FormEvent) {
    event.preventDefault();
    onError(null);
    setBusy(true);
    try {
      const task = await api<{ id: string }>("/api/tasks", { body: { kind: "improve.cycle", payload: { component: name, candidate: chosen } } });
      await waitForTask(task.id, 120000);
      await onDone();
    } catch (e) {
      onError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Avvia un ciclo di miglioramento">
      <form className="form-row" onSubmit={submit}>
        <label>
          <span>Componente</span>
          <select value={name} onChange={(e) => setName(e.target.value)}>
            {components.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
          </select>
        </label>
        <label>
          <span>Versione candidata</span>
          <select value={chosen} onChange={(e) => setCandidate(e.target.value)}>
            {candidates.map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
        </label>
        <button className="button button-primary" type="submit" disabled={busy || !chosen}>
          {busy ? "Misurazione in corso…" : "Rileva, proponi e valuta"}
        </button>
      </form>
      <p className="note">Il ciclo misura la versione attiva, raccoglie gli errori, prova la candidata sugli stessi dati e confronta. Non promuove nulla senza la tua approvazione.</p>
    </Card>
  );
}
