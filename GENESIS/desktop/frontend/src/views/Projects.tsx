import { useState, type FormEvent } from "react";
import { api, errorText, usePolling } from "../api";
import { navigate } from "../router";
import type { Project } from "../types";
import { Badge, Card, Empty, ErrorBanner, formatDate, Loading, PageHeader } from "../ui";

export function Projects() {
  const [showArchived, setShowArchived] = useState(false);
  const projects = usePolling(() => api<Project[]>(`/api/projects${showArchived ? "?all=1" : ""}`), 0, [showArchived]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api<Project>("/api/projects", { body: { name, description } });
      setName("");
      setDescription("");
      await projects.refresh();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function archive(project: Project) {
    if (!window.confirm(`Archiviare il progetto «${project.name}»? I suoi compiti restano consultabili.`)) return;
    setError(null);
    try {
      await api<Project>(`/api/projects/${project.id}/archive`, { body: {} });
      await projects.refresh();
    } catch (e) {
      setError(errorText(e));
    }
  }

  return (
    <>
      <PageHeader title="Progetti" subtitle="Contenitori per compiti e, nelle prossime fasi, memoria e agenti." />
      <ErrorBanner message={error ?? projects.error} />
      <Card title="Nuovo progetto">
        <form className="form-row" onSubmit={create}>
          <label>
            <span>Nome</span>
            <input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} required />
          </label>
          <label className="grow">
            <span>Descrizione (facoltativa)</span>
            <input value={description} onChange={(e) => setDescription(e.target.value)} maxLength={500} />
          </label>
          <button className="button button-primary" type="submit" disabled={busy || !name.trim()}>
            {busy ? "Creazione…" : "Crea progetto"}
          </button>
        </form>
      </Card>

      <Card
        title="Elenco"
        actions={
          <label className="toggle">
            <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
            <span>Mostra archiviati</span>
          </label>
        }
      >
        {!projects.data ? (
          <Loading />
        ) : projects.data.length === 0 ? (
          <Empty>Nessun progetto. Creane uno qui sopra.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Nome</th><th>Descrizione</th><th>Creato</th><th>Stato</th><th /></tr>
              </thead>
              <tbody>
                {projects.data.map((p) => (
                  <tr key={p.id}>
                    <td className="strong">{p.name}</td>
                    <td>{p.description || <span className="muted">—</span>}</td>
                    <td>{formatDate(p.created_at)}</td>
                    <td><Badge tone={p.status === "active" ? "ok" : "muted"}>{p.status === "active" ? "attivo" : "archiviato"}</Badge></td>
                    <td className="actions">
                      <button type="button" className="button button-small" onClick={() => navigate("compiti", { progetto: p.id })}>
                        Compiti
                      </button>
                      {p.status === "active" && (
                        <button type="button" className="button button-small button-quiet" onClick={() => archive(p)}>
                          Archivia
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
    </>
  );
}
