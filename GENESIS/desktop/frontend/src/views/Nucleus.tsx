import { useEffect, useMemo, useRef, useState } from "react";
import { api, usePolling } from "../api";
import { agentColor, GlobeRenderer, MAX_AGENTS, type GlobeStats } from "../globe/renderer";
import { navigate } from "../router";
import type { Agent, AgentRun, Status } from "../types";

const RECENT_MINUTES = 15;
// Upper bound of lights per execution profile; below it the globe adapts to the measured frame rate.
// A 4 GB PC must keep CPU for GÉNESIS itself (measured on the owner's PC, see TEST_REPORT.md).
const MAX_LIGHTS: Record<string, number> = { "lite-4gb": 120_000, standard: 1_000_000, gpu: 2_000_000 };

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

export function Nucleus({ status }: { status: Status | null }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<GlobeRenderer | null>(null);
  const [stats, setStats] = useState<GlobeStats | null>(null);
  const [glError, setGlError] = useState<string | null>(null);
  const agents = usePolling(() => api<Agent[]>("/api/agents"), 0);
  const runs = usePolling(() => api<AgentRun[]>("/api/agent-runs?limit=50"), 3000);

  const list = useMemo(() => (agents.data ?? []).slice(0, MAX_AGENTS), [agents.data]);
  const levels = useMemo(() => activityFrom(list, runs.data ?? []), [list, runs.data]);
  const names = useMemo(() => new Map(list.map((a) => [a.id, a.name])), [list]);

  const profile = status?.profile ?? null;
  useEffect(() => {
    const canvas = canvasRef.current, overlay = overlayRef.current;
    if (!canvas || !overlay || list.length === 0 || profile === null) return undefined;
    let renderer: GlobeRenderer;
    try {
      renderer = new GlobeRenderer(canvas, overlay, list, setStats, (id) => navigate("agenti", { agente: id }),
                                   MAX_LIGHTS[profile] ?? MAX_LIGHTS.standard);
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

  const running = (runs.data ?? []).filter((r) => r.status === "running").length;
  const recent = (runs.data ?? []).slice(0, 6);

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
        </dl>
        <ul className="hud-agents" aria-label="Attività degli agenti">
          {list.map((a, i) => (
            <li key={a.id} style={{ color: agentColor(i) }}>
              <button type="button" onClick={() => navigate("agenti", { agente: a.id })} title={a.objective}>
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
        <a className="hud-link" href="#/agenti">Invia una richiesta agli agenti →</a>
      </div>

      <div className="hud hud-br">
        <p className="hud-k">Trascina per ruotare · rotella per zoom · clic su un nome per aprire l'agente</p>
        <p className="hud-k">{stats ? `${stats.renderer} · luci adattate alla potenza del PC` : "Avvio del globo…"}</p>
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
