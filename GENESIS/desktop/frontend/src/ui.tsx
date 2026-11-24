import type { ReactNode } from "react";
import type { TaskStatus } from "./types";

export const STATUS_LABEL: Record<TaskStatus, string> = {
  pending: "In coda",
  running: "In esecuzione",
  succeeded: "Completato",
  failed: "Fallito",
  cancelled: "Annullato",
};

const STATUS_TONE: Record<TaskStatus, Tone> = {
  pending: "info",
  running: "accent",
  succeeded: "ok",
  failed: "bad",
  cancelled: "muted",
};

export const LEVEL_LABEL: Record<number, string> = {
  1: "lettura",
  2: "scrittura di lavoro",
  3: "esecuzione",
  4: "modifica di sistema",
  5: "irreversibile",
};

type Tone = "ok" | "warn" | "bad" | "info" | "accent" | "muted";

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString("it-IT", { dateStyle: "short", timeStyle: "medium" });
}

export function gb(mb: number | null | undefined): string {
  return mb == null ? "non rilevata" : `${(mb / 1024).toFixed(1)} GB`;
}

export function Badge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function StatusBadge({ status }: { status: TaskStatus }) {
  return <Badge tone={STATUS_TONE[status]}>{STATUS_LABEL[status]}</Badge>;
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="subtitle">{subtitle}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}

export function Card({
  title,
  children,
  actions,
  className = "",
}: {
  title?: string;
  children: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <div className="card-head">
          {title && <h2>{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function Meter({ used, total, label }: { used: number; total: number; label: string }) {
  const ratio = total > 0 ? Math.min(1, Math.max(0, used / total)) : 0;
  const tone = ratio > 0.9 ? "bad" : ratio > 0.75 ? "warn" : "ok";
  return (
    <div className="meter" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100}
         aria-valuenow={Math.round(ratio * 100)}>
      <div className={`meter-fill meter-${tone}`} style={{ width: `${(ratio * 100).toFixed(1)}%` }} />
    </div>
  );
}

export function ErrorBanner({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className="banner banner-bad" role="alert">
      {message}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>;
}

export function Facts({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="facts">
      {rows.map(([key, value]) => (
        <div key={key}>
          <dt>{key}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Loading() {
  return <p className="empty">Caricamento…</p>;
}
