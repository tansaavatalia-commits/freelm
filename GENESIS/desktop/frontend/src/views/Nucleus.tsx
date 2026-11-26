import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { api, errorText, usePolling } from "../api";
import { agentColor, GlobeRenderer, MAX_AGENTS, type GlobeStats } from "../globe/renderer";
import type { Agent, AgentRun, Status, Task } from "../types";

const RECENT_MINUTES = 15;
// Upper bound of lights per execution profile; below it the globe adapts to the measured frame rate.
// A 4 GB PC must keep CPU for GÉNESIS itself (measured on the owner's PC, see TEST_REPORT.md).
const MAX_LIGHTS: Record<string, number> = { "lite-4gb": 120_000, standard: 1_000_000, gpu: 2_000_000 };
const DIRECTOR = "director";

/** 0..1 per agent from real runs: 1 while running, then fading over RECENT_MINUTES; 0.15 at rest. */
export function activityFrom(agents: Agent[], runs: AgentRun[], now = Date.now()): number[] {
  return agents.map((a) => {
    let level = 0.15;
    for (const r of runs) {
      if (r.agent_id !== a.id) continue;
      if (r.status === "running") return 1;
      const ageMin = (now - Date.parse(r.created_at)) / 60000;
      if (ageMin >= 0) level = Math.max(level, 0.15 + 0.85 * Math.exp(-ageMin / RECENT_MINUTES));
    }
    return level;
  });
}

function time(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
}

const RUN_LABEL: Record<AgentRun["status"], string> = { running: "in corso", succeeded: "riuscita", failed: "fallita" };

interface Sent {
  text: string;
  target: string;
  at: number;
}

export function Nucleus({ status }: { status: Status | null }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const rendererRef = useRef<GlobeRenderer | null>(null);
  const seenRuns = useRef<Set<string> | null>(null);
  const [stats, setStats] = useState<GlobeStats | null>(null);
  const [glError, setGlError] = useState<string | null>(null);
  const [target, setTarget] = useState(DIRECTOR);
  const [text, setText] = useState("");
  const [isPrivate, setPrivate] = useState(false);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState<Sent | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const agents = usePolling(() => api<Agent[]>("/api/agents"), 0);
  const runs = usePolling(() => api<AgentRun[]>("/api/agent-runs?limit=50"), sent ? 1500 : 3000, [sent !== null]);

  const list = useMemo(() => (agents.data ?? []).slice(0, MAX_AGENTS), [agents.data]);
  const levels = useMemo(() => activityFrom(list, runs.data ?? []), [list, runs.data]);
  const names = useMemo(() => new Map(list.map((a) => [a.id, a.name])), [list]);
  const indexOf = useMemo(() => new Map(list.map((a, i) => [a.id, i])), [list]);

  const profile = status?.profile ?? null;
  useEffect(() => {
    const canvas = canvasRef.current, overlay = overlayRef.current;
    if (!canvas || !overlay || list.length === 0 || profile === null) return undefined;
    let renderer: GlobeRenderer;
    try {
      renderer = new GlobeRenderer(canvas, overlay, list, setStats, (id) => {
        setTarget(id);
        inputRef.current?.focus();
      }, MAX_LIGHTS[profile] ?? MAX_LIGHTS.standard);
    } catch (e) {
      setGlError(e instanceof Error ? e.message : String(e));
      return undefined;
    }
    rendererRef.current = renderer;
    renderer.start();
    const observer = new ResizeObserver(() => renderer.resize());
    observer.observe(canvas);
    return () => {
      observer.disconnect();
      renderer.destroy();
      rendererRef.current = null;
    };
  }, [list, profile]);

  useEffect(() => {
    rendererRef.current?.activity.set(levels);
  }, [levels]);

  useEffect(() => {
    rendererRef.current?.select(indexOf.get(target) ?? -1);
  }, [target, indexOf, stats === null]);

  // A run that appears while the page is open (from here, the Agents page or the CLI) sends a shockwave.
  useEffect(() => {
    if (!runs.data) return;
    const ids = new Set(runs.data.map((r) => r.id));
    if (seenRuns.current) {
      for (const r of runs.data) {
        if (!seenRuns.current.has(r.id)) rendererRef.current?.burst(indexOf.get(r.agent_id) ?? -1);
      }
    }
    seenRuns.current = ids;
  }, [runs.data, indexOf]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const goal = text.trim();
    if (!goal) return;
    setSending(true);
    setSendError(null);
    const body = target === DIRECTOR
      ? { kind: "agents.direct", payload: { goal, private: isPrivate } }
      : { kind: "agents.run", payload: { agent: target, goal, private: isPrivate } };
    try {
      await api<Task>("/api/tasks", { body });
      rendererRef.current?.burst(indexOf.get(target) ?? 0);
      setSent({ text: goal, target, at: Date.now() });
      setText("");
      await runs.refresh();
    } catch (e) {
      setSendError(errorText(e));
    } finally {
      setSending(false);
    }
  }

  // The run that answers the last request: same text, created after it was sent (small clock margin).
  const answer = sent
    ? (runs.data ?? []).find((r) => r.goal === sent.text && Date.parse(r.created_at) >= sent.at - 60_000)
    : undefined;

  const running = (runs.data ?? []).filter((r) => r.status === "running").length;
  const recent = (runs.data ?? []).slice(0, 5);
  const targetName = target === DIRECTOR ? "Director" : names.get(target) ?? target;

  return (
    <section className="nucleus" aria-label="Núcleo: mappa degli agenti">
      <canvas ref={canvasRef} className="nucleus-canvas" aria-hidden="true" />
      <div className="nucleus-grid" aria-hidden="true" />
      <div className="nucleus-scan" aria-hidden="true" />
      <div ref={overlayRef} className="nucleus-labels" />

      <div className="hud hud-tl">
        <h1 className="hud-title">GÉNESIS</h1>
        <p className="hud-k">Núcleo // mappa degli agenti</p>
        <p className="hud-k">Ogni luce appartiene a un agente; una regione si accende quando il suo agente lavora.</p>
        <span className={`hud-tag ${running ? "hud-tag-live" : ""}`}>
          {running ? `${running} agenti al lavoro` : (runs.data ?? []).length ? "Attività reale" : "A riposo: nessuna attività recente"}
        </span>
      </div>

      <div className="hud hud-tr">
        <dl className="hud-facts">
          <div><dt>Luci</dt><dd>{stats ? stats.lights.toLocaleString("it-IT") : "—"}</dd></div>
          <div><dt>Fotogrammi/s</dt><dd>{stats?.fps ?? "—"}</dd></div>
          <div><dt>Profilo</dt><dd>{status?.profile ?? "—"}</dd></div>
          <div><dt>RAM GÉNESIS</dt><dd>{status?.memory.process_rss_mb != null ? `${status.memory.process_rss_mb} MB` : "—"}</dd></div>
          <div><dt>Compiti</dt><dd>{status ? `${status.tasks.running} in corso · ${status.tasks.pending} in coda` : "—"}</dd></div>
          <div><dt>Audit</dt><dd>{status ? (status.audit_chain_ok ? "integro" : "da verificare") : "—"}</dd></div>
          <div><dt>Grafica</dt><dd className="hud-ellipsis">{stats?.renderer ?? "—"}</dd></div>
        </dl>
        <ul className="hud-agents" aria-label="Attività degli agenti: clic per scrivere a un agente">
          {list.map((a, i) => (
            <li key={a.id} style={{ color: agentColor(i) }}>
              <button type="button" onClick={() => { setTarget(a.id); inputRef.current?.focus(); }} title={a.objective}
                      aria-pressed={target === a.id}>
                <span className="hud-k">{a.name}</span>
                <span className="hud-bar"><b style={{ width: `${Math.round(levels[i] * 100)}%` }} /></span>
                <i aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="hud hud-bl">
        <p className="hud-k">Ultime attività</p>
        {recent.length === 0 ? (
          <p className="hud-k">Nessuna richiesta agli agenti finora.</p>
        ) : (
          <ul className="hud-feed">
            {recent.map((r) => (
              <li key={r.id}>
                <span className="hud-k">{time(r.created_at)}</span> {names.get(r.agent_id) ?? r.agent_id}{" "}
                <span className={`hud-run hud-run-${r.status}`}>{RUN_LABEL[r.status]}</span>
                <span className="hud-goal">{r.goal}</span>
              </li>
            ))}
          </ul>
        )}
        <a className="hud-link" href="#/agenti">Tutte le esecuzioni →</a>
      </div>

      <div className="hud hud-console">
        {sent && (
          <div className="hud-answer" role="status" aria-live="polite">
            <div className="hud-answer-head">
              <span className="hud-k">Risposta · {sent.target === DIRECTOR ? "Director" : names.get(sent.target) ?? sent.target}</span>
              {answer && <span className={`hud-run hud-run-${answer.status}`}>{RUN_LABEL[answer.status]}</span>}
              <button type="button" className="hud-close" onClick={() => setSent(null)} aria-label="Chiudi la risposta">×</button>
            </div>
            <p className="hud-q">› {sent.text}</p>
            <pre className="hud-out">{answer?.output ?? (answer ? "…" : "In coda: l'esecutore la prende tra pochi secondi…")}</pre>
          </div>
        )}
        {sendError && <p className="hud-error" role="alert">{sendError}</p>}
        <form className="hud-form" onSubmit={submit}>
          <label className="hud-target">
            <span className="hud-k">A</span>
            <select value={target} onChange={(e) => setTarget(e.target.value)} aria-label="Destinatario">
              <option value={DIRECTOR}>Director (sceglie e delega)</option>
              {list.filter((a) => a.id !== DIRECTOR).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </label>
          <input
            ref={inputRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={`Scrivi una richiesta a ${targetName}…`}
            aria-label="Richiesta"
            maxLength={2000}
          />
          <label className="hud-private" title="La richiesta non esce da questo PC">
            <input type="checkbox" checked={isPrivate} onChange={(e) => setPrivate(e.target.checked)} />
            <span className="hud-k">privata</span>
          </label>
          <button type="submit" disabled={sending || !text.trim()}>{sending ? "…" : "Invia"}</button>
        </form>
        <p className="hud-k hud-hint">Trascina per ruotare · rotella per zoom · clic su un nome per scegliere il destinatario</p>
      </div>

      {(glError || agents.error) && (
        <div className="hud hud-center" role="alert">
          <p>{glError ? `Il globo non può essere disegnato: ${glError}.` : agents.error}</p>
          <a className="hud-link" href="#/dashboard">Apri il pannello classico</a>
        </div>
      )}
    </section>
  );
}
