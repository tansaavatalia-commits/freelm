import { useState, type FormEvent } from "react";
import { api, ApiError, errorText, usePolling } from "../api";
import type { Agent, AgentRun } from "../types";
import { Badge, Card, Empty, ErrorBanner, formatDate, Loading, PageHeader } from "../ui";

const MODES = {
  agent: { kind: "agents.run", label: "Un agente" },
  direct: { kind: "agents.direct", label: "Director (scompone e delega)" },
  council: { kind: "agents.council", label: "Consiglio di specialisti" },
} as const;
type Mode = keyof typeof MODES;

export function Agents() {
  const agents = usePolling(() => api<Agent[]>("/api/agents"), 0);
  const runs = usePolling(() => api<AgentRun[]>("/api/agent-runs?limit=20"), 3000);
  const [mode, setMode] = useState<Mode>("agent");
  const [agent, setAgent] = useState("analyst");
  const [text, setText] = useState("");
  const [isPrivate, setPrivate] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    const payload =
      mode === "agent" ? { agent, goal: text, private: isPrivate }
      : mode === "direct" ? { goal: text, private: isPrivate }
      : { question: text, private: isPrivate };
    try {
      await api("/api/tasks", { body: { kind: MODES[mode].kind, payload } });
      setNotice("In coda: il risultato compare qui sotto tra pochi secondi.");
      setText("");
      await runs.refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : errorText(e));
    }
  }

  return (
    <>
      <PageHeader title="Agenti" subtitle="Specialisti con permessi propri. Ogni risposta passa dal router (solo motori gratuiti) e da controlli deterministici." />
      <ErrorBanner message={error ?? agents.error ?? runs.error} />
      {notice && <div className="banner banner-ok" role="status">{notice}</div>}
      <Card title="Nuova richiesta">
        <form className="form-grid" onSubmit={submit}>
          <label>
            <span>Modalità</span>
            <select value={mode} onChange={(e) => setMode(e.target.value as Mode)}>
              {Object.entries(MODES).map(([k, m]) => <option key={k} value={k}>{m.label}</option>)}
            </select>
          </label>
          {mode === "agent" && (
            <label>
              <span>Agente</span>
              <select value={agent} onChange={(e) => setAgent(e.target.value)}>
                {agents.data?.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </label>
          )}
          <label className="toggle">
            <input type="checkbox" checked={isPrivate} onChange={(e) => setPrivate(e.target.checked)} />
            <span>Privata (resta su questo PC)</span>
          </label>
          <label className="span-all">
            <span>{mode === "direct" ? "Obiettivo (un sotto-compito per riga, oppure separati da ;)" : "Richiesta"}</span>
            <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} required />
          </label>
          <div className="span-all">
            <button className="button button-primary" type="submit" disabled={!text.trim()}>Invia</button>
          </div>
        </form>
      </Card>

      <Card title="Ultime esecuzioni">
        {!runs.data ? <Loading /> : runs.data.length === 0 ? <Empty>Nessuna esecuzione.</Empty> : (
          <ul className="approval-list">
            {runs.data.map((r) => (
              <li key={r.id} className="approval">
                <div>
                  <p className="strong">{r.goal}</p>
                  <p className="note">{r.mode} · {r.agent_id} v{r.agent_version} · {formatDate(r.created_at)}</p>
                  {open === r.id && <pre className="pre">{r.output ?? "…"}</pre>}
                </div>
                <div className="actions">
                  <Badge tone={r.status === "succeeded" ? "ok" : r.status === "failed" ? "bad" : "info"}>
                    {r.status === "succeeded" ? "riuscita" : r.status === "failed" ? "non riuscita" : "in corso"}
                  </Badge>
                  <button type="button" className="button button-small" onClick={() => setOpen(open === r.id ? null : r.id)}>
                    {open === r.id ? "Chiudi" : "Risultato"}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Catalogo">
        {!agents.data ? <Loading /> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Agente</th><th>Obiettivo</th><th>Tipi</th><th>Livello</th></tr></thead>
              <tbody>
                {agents.data.map((a) => (
                  <tr key={a.id}>
                    <td className="strong">{a.name} <span className="muted">v{a.version}</span></td>
                    <td>{a.objective}</td>
                    <td className="mono">{a.task_types.join(", ")}</td>
                    <td>{a.level}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
