import { Fragment, useState, type FormEvent } from "react";
import { api, ApiError, errorText, usePolling } from "../api";
import { navigate, type Route } from "../router";
import { TASK_STATUSES, type Project, type Task, type TaskKind, type TaskStatus } from "../types";
import { Card, Empty, ErrorBanner, formatDate, LEVEL_LABEL, Loading, PageHeader, STATUS_LABEL, StatusBadge } from "../ui";

export function Tasks({ route }: { route: Route }) {
  const statusFilter = (route.params.get("stato") ?? "") as TaskStatus | "";
  const projectFilter = route.params.get("progetto") ?? "";
  const query = new URLSearchParams({ limit: "100" });
  if (statusFilter) query.set("status", statusFilter);
  if (projectFilter) query.set("project", projectFilter);

  const tasks = usePolling(() => api<Task[]>(`/api/tasks?${query.toString()}`), 2000, [statusFilter, projectFilter]);
  const kinds = usePolling(() => api<TaskKind[]>("/api/task-kinds"), 0);
  const projects = usePolling(() => api<Project[]>("/api/projects?all=1"), 0);
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const projectName = (id: string | null) => projects.data?.find((p) => p.id === id)?.name ?? "—";

  function setFilter(key: "stato" | "progetto", value: string) {
    const params: Record<string, string> = {};
    if (statusFilter) params.stato = statusFilter;
    if (projectFilter) params.progetto = projectFilter;
    if (value) params[key] = value;
    else delete params[key];
    navigate("compiti", params);
  }

  async function cancel(task: Task) {
    setError(null);
    try {
      await api(`/api/tasks/${task.id}/cancel`, { body: {} });
      await tasks.refresh();
    } catch (e) {
      setError(errorText(e));
    }
  }

  return (
    <>
      <PageHeader title="Compiti" subtitle="Vengono eseguiti uno alla volta, in ordine di priorità. Si aggiorna da solo." />
      <ErrorBanner message={error ?? tasks.error ?? kinds.error} />
      {kinds.data && projects.data && (
        <SubmitForm kinds={kinds.data} projects={projects.data.filter((p) => p.status === "active")}
                    defaultProject={projectFilter} onDone={tasks.refresh} />
      )}

      <Card
        title="Coda e storico"
        actions={
          <div className="filters">
            <select aria-label="Filtra per stato" value={statusFilter} onChange={(e) => setFilter("stato", e.target.value)}>
              <option value="">Tutti gli stati</option>
              {TASK_STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
            </select>
            <select aria-label="Filtra per progetto" value={projectFilter} onChange={(e) => setFilter("progetto", e.target.value)}>
              <option value="">Tutti i progetti</option>
              {projects.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
        }
      >
        {!tasks.data ? (
          <Loading />
        ) : tasks.data.length === 0 ? (
          <Empty>Nessun compito con questi filtri.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Stato</th><th>Tipo</th><th>Progetto</th><th>Creato</th><th>Tentativi</th><th /></tr>
              </thead>
              <tbody>
                {tasks.data.map((t) => (
                  <Fragment key={t.id}>
                    <tr>
                      <td><StatusBadge status={t.status} /></td>
                      <td className="mono">{t.kind}</td>
                      <td>{projectName(t.project_id)}</td>
                      <td>{formatDate(t.created_at)}</td>
                      <td>{t.attempts}/{t.max_attempts}</td>
                      <td className="actions">
                        <button type="button" className="button button-small" aria-expanded={open === t.id}
                                onClick={() => setOpen(open === t.id ? null : t.id)}>
                          {open === t.id ? "Chiudi" : "Dettagli"}
                        </button>
                        {(t.status === "pending" || (t.status === "running" && !t.cancel_requested)) && (
                          <button type="button" className="button button-small button-quiet" onClick={() => cancel(t)}>
                            Annulla
                          </button>
                        )}
                      </td>
                    </tr>
                    {open === t.id && (
                      <tr className="details-row">
                        <td colSpan={6}><TaskDetails task={t} /></td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}

function TaskDetails({ task }: { task: Task }) {
  return (
    <div className="details">
      <dl className="facts">
        <div><dt>Id</dt><dd className="mono">{task.id}</dd></div>
        <div><dt>Livello</dt><dd>{task.level} — {LEVEL_LABEL[task.level]}</dd></div>
        <div><dt>Avviato</dt><dd>{formatDate(task.started_at)}</dd></div>
        <div><dt>Concluso</dt><dd>{formatDate(task.finished_at)}</dd></div>
      </dl>
      {task.error && <><h3>Errore</h3><pre className="pre pre-bad">{task.error}</pre></>}
      <h3>Dati in ingresso</h3>
      <pre className="pre">{JSON.stringify(task.payload, null, 2)}</pre>
      {task.result !== null && <><h3>Risultato</h3><pre className="pre">{JSON.stringify(task.result, null, 2)}</pre></>}
    </div>
  );
}

function SubmitForm({ kinds, projects, defaultProject, onDone }: {
  kinds: TaskKind[];
  projects: Project[];
  defaultProject: string;
  onDone: () => Promise<void>;
}) {
  const [kind, setKind] = useState(kinds[0]?.kind ?? "");
  const [project, setProject] = useState(defaultProject);
  const [payload, setPayload] = useState("{}");
  const [priority, setPriority] = useState(0);
  const [attempts, setAttempts] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const selected = kinds.find((k) => k.kind === kind);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    let parsed: unknown;
    try {
      parsed = JSON.parse(payload || "{}");
    } catch {
      setError("I dati in ingresso devono essere JSON valido, per esempio {} oppure {\"testo\": \"ciao\"}.");
      return;
    }
    setBusy(true);
    try {
      await api<Task>("/api/tasks", {
        body: { kind, payload: parsed, project: project || null, priority, attempts },
      });
      await onDone();
    } catch (e) {
      setError(e instanceof ApiError && e.approvalId
        ? `${e.message} — vai in Approvazioni per decidere.`
        : errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Nuovo compito">
      <form className="form-grid" onSubmit={submit}>
        <label>
          <span>Tipo</span>
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            {kinds.map((k) => <option key={k.kind} value={k.kind}>{k.kind}</option>)}
          </select>
        </label>
        <label>
          <span>Progetto</span>
          <select value={project} onChange={(e) => setProject(e.target.value)}>
            <option value="">Nessuno</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
        <label>
          <span>Priorità</span>
          <input type="number" value={priority} onChange={(e) => setPriority(Number(e.target.value) || 0)} />
        </label>
        <label>
          <span>Tentativi massimi</span>
          <input type="number" min={1} max={10} value={attempts}
                 onChange={(e) => setAttempts(Math.min(10, Math.max(1, Number(e.target.value) || 1)))} />
        </label>
        <label className="span-all">
          <span>Dati in ingresso (JSON)</span>
          <textarea rows={2} value={payload} onChange={(e) => setPayload(e.target.value)} spellCheck={false} />
        </label>
        {selected && (
          <p className="note span-all">
            {selected.description} Livello {selected.level} ({LEVEL_LABEL[selected.level]}).
          </p>
        )}
        {error && <p className="field-error span-all" role="alert">{error}</p>}
        <div className="span-all">
          <button className="button button-primary" type="submit" disabled={busy || !kind}>
            {busy ? "Invio…" : "Metti in coda"}
          </button>
        </div>
      </form>
    </Card>
  );
}
