import { useState } from "react";
import { api, errorText, usePolling } from "../api";
import type { Approval } from "../types";
import { Badge, Card, Empty, ErrorBanner, formatDate, LEVEL_LABEL, Loading, PageHeader } from "../ui";

const STATUS: Record<Approval["status"], { label: string; tone: "info" | "ok" | "bad" | "muted" }> = {
  pending: { label: "in attesa", tone: "info" },
  approved: { label: "approvata", tone: "ok" },
  denied: { label: "negata", tone: "bad" },
  used: { label: "usata", tone: "muted" },
};

export function Approvals({ onChange }: { onChange: () => Promise<void> }) {
  const approvals = usePolling(() => api<Approval[]>("/api/approvals"), 3000);
  const [error, setError] = useState<string | null>(null);

  async function decide(approval: Approval, approve: boolean) {
    const verb = approve ? "Approvare" : "Negare";
    if (!window.confirm(`${verb} «${approval.action}» (livello ${approval.level})?`)) return;
    setError(null);
    try {
      await api(`/api/approvals/${approval.id}/${approve ? "approve" : "deny"}`, { body: {} });
      await Promise.all([approvals.refresh(), onChange()]);
    } catch (e) {
      setError(errorText(e));
    }
  }

  const pending = approvals.data?.filter((a) => a.status === "pending") ?? [];
  const history = approvals.data?.filter((a) => a.status !== "pending").reverse() ?? [];

  return (
    <>
      <PageHeader
        title="Approvazioni"
        subtitle="Le azioni di livello 4 (modifiche di sistema) e 5 (spese, pubblicazioni, cancellazioni) aspettano qui la tua decisione. Ogni approvazione vale una sola volta."
      />
      <ErrorBanner message={error ?? approvals.error} />
      <Card title="In attesa">
        {!approvals.data ? (
          <Loading />
        ) : pending.length === 0 ? (
          <Empty>Nessuna richiesta in attesa.</Empty>
        ) : (
          <ul className="approval-list">
            {pending.map((a) => (
              <li key={a.id} className="approval">
                <div>
                  <p className="strong">{a.action}</p>
                  <p className="note">
                    Richiesta da <span className="mono">{a.principal}</span> · livello {a.level} ({LEVEL_LABEL[a.level]}) ·{" "}
                    {formatDate(a.created_at)}
                  </p>
                  {Object.keys(a.details).length > 0 && <pre className="pre">{JSON.stringify(a.details, null, 2)}</pre>}
                </div>
                <div className="actions">
                  <button type="button" className="button button-primary" onClick={() => decide(a, true)}>Approva</button>
                  <button type="button" className="button button-danger" onClick={() => decide(a, false)}>Nega</button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="Storico">
        {history.length === 0 ? (
          <Empty>Nessuna decisione presa finora.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Azione</th><th>Livello</th><th>Stato</th><th>Richiesta</th><th>Decisa</th></tr>
              </thead>
              <tbody>
                {history.map((a) => (
                  <tr key={a.id}>
                    <td className="mono">{a.action}</td>
                    <td>{a.level}</td>
                    <td><Badge tone={STATUS[a.status].tone}>{STATUS[a.status].label}</Badge></td>
                    <td>{formatDate(a.created_at)}</td>
                    <td>{formatDate(a.decided_at)}</td>
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
