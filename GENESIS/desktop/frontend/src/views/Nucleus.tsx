import { useEffect, useMemo, useRef, useState } from "react";
import { api, usePolling } from "../api";
import { agentColor, GlobeRenderer, MAX_AGENTS, type GlobeStats } from "../globe/renderer";
import type { Agent, AgentRun, Status } from "../types";
import { CHAT, ChatPanel } from "./ChatPanel";

const RECENT_MINUTES = 15;
// Upper bound of lights per execution profile; below it the globe adapts to the measured frame rate.
// A 4 GB PC must keep CPU for GÉNESIS itself (measured on the owner's PC, see TEST_REPORT.md).
const MAX_LIGHTS: Record<string, number> = { "lite-4gb": 120_000, standard: 1_000_000, gpu: 2_000_000 };
const PANEL_WIDTH = 440; // keep in sync with .chat in styles.css
const PANEL_LEFT = 22;
const WIDE = 820;

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

export function Nucleus({ status }: { status: Status | null }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const rendererRef = useRef<GlobeRenderer | null>(null);
  const seenRuns = useRef<Set<string> | null>(null);
  const lastBurst = useRef(0);
  const [stats, setStats] = useState<GlobeStats | null>(null);
  const [glError, setGlError] = useState<string | null>(null);
  const [target, setTarget] = useState(CHAT);
  const agents = usePolling(() => api<Agent[]>("/api/agents"), 0);
  const runs = usePolling(() => api<AgentRun[]>("/api/agent-runs?limit=50"), 2500);

  const list = useMemo(() => (agents.data ?? []).slice(0, MAX_AGENTS), [agents.data]);
  const levels = useMemo(() => activityFrom(list, runs.data ?? []), [list, runs.data]);
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
    const layout = () => {
      renderer.resize();
      renderer.setShift(window.innerWidth > WIDE ? (PANEL_WIDTH + PANEL_LEFT) / 2 : 0);
    };
    layout();
    renderer.start();
    const observer = new ResizeObserver(layout);
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
    rendererRef.current?.select(target === CHAT ? -1 : indexOf.get(target) ?? -1);
  }, [target, indexOf, stats === null]);

  // A run that appears while the page is open (from here, the Agents page or the CLI) sends a shockwave.
  useEffect(() => {
    if (!runs.data) return;
    if (seenRuns.current) {
      for (const r of runs.data) {
        if (!seenRuns.current.has(r.id)) rendererRef.current?.burst(indexOf.get(r.agent_id) ?? -1);
      }
    }
    seenRuns.current = new Set(runs.data.map((r) => r.id));
  }, [runs.data, indexOf]);

  function onActivity(agentId: string | null) {
    const now = performance.now();
    if (now - lastBurst.current < 1200) return; // while an answer streams: one wave every 1.2 s
    lastBurst.current = now;
    rendererRef.current?.burst(agentId === null ? 0 : indexOf.get(agentId) ?? 0);
    if (agentId !== null) void runs.refresh();
  }

  const running = (runs.data ?? []).filter((r) => r.status === "running").length;

  return (
    <section className="nucleus" aria-label="Núcleo: GÉNESIS e i suoi agenti">
      <canvas ref={canvasRef} className="nucleus-canvas" aria-hidden="true" />
      <div className="nucleus-grid" aria-hidden="true" />
      <div className="nucleus-scan" aria-hidden="true" />
      <div ref={overlayRef} className="nucleus-labels" />

      <div className="hud hud-tl">
        <h1 className="hud-title">GÉNESIS</h1>
        <p className="hud-k">Núcleo // mappa degli agenti</p>
      </div>

      <ChatPanel agents={list} runs={runs.data ?? []} target={target} setTarget={setTarget}
                 onActivity={onActivity} inputRef={inputRef} />

      <div className="hud hud-tr">
        <span className={`hud-tag ${running ? "hud-tag-live" : ""}`}>
          {running ? `${running} agenti al lavoro` : "Agenti pronti"}
        </span>
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
        <a className="hud-link" href="#/agenti">Tutte le esecuzioni →</a>
      </div>

      <div className="hud hud-br">
        <p className="hud-k">Trascina il globo per ruotarlo · rotella per lo zoom · clic su un nome per scrivergli</p>
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
