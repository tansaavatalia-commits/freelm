import { useState, type FormEvent } from "react";
import { api, errorText, usePolling } from "../api";
import type { LabComparison, LabDataset, LabDetail, LabExperiment } from "../types";
import { Badge, Card, Empty, ErrorBanner, Facts, formatDate, Loading, Meter, PageHeader } from "../ui";

const pct = (x: number | undefined | null) => (x == null ? "—" : `${(x * 100).toFixed(1)}%`);
const STATUS: Record<LabExperiment["status"], string> = {
  running: "in corso", completed: "completato", failed: "fallito", interrupted: "interrotto",
};

export function ResearchLab() {
  const datasets = usePolling(() => api<LabDataset[]>("/api/lab/datasets"), 0);
  const subjects = usePolling(() => api<string[]>("/api/lab/subjects"), 0);
  const experiments = usePolling(() => api<LabExperiment[]>("/api/lab/experiments?limit=50"), 3000);
  const [selected, setSelected] = useState<string[]>([]);
  const [comparison, setComparison] = useState<LabComparison | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  function toggle(id: string) {
    setComparison(null);
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id].slice(-2)));
  }

  async function compare() {
    setError(null);
    try {
      setComparison(await api<LabComparison>(`/api/lab/compare?a=${selected[0]}&b=${selected[1]}`));
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function reproduce(id: string) {
    setError(null);
    try {
      await api("/api/tasks", { body: { kind: "lab.reproduce", payload: { experiment_id: id } } });
      setNotice("Riproduzione in coda: comparirà come nuovo esperimento.");
    } catch (e) {
      setError(errorText(e));
    }
  }

  return (
    <>
      <PageHeader title="Research Lab" subtitle="Esperimenti registrati e riproducibili. Un miglioramento si dichiara solo con un confronto appaiato sullo stesso dataset e una differenza statisticamente dimostrata." />
      <ErrorBanner message={error ?? experiments.error ?? datasets.error} />
      {notice && <div className="banner banner-ok" role="status">{notice}</div>}
      {datasets.data && subjects.data && (
        <RunForm datasets={datasets.data} subjects={subjects.data} experiments={experiments.data ?? []}
                 onQueued={(msg) => { setNotice(msg); void experiments.refresh(); }} onError={setError} />
      )}

      <Card
        title="Esperimenti"
        actions={
          <button type="button" className="button button-primary button-small" disabled={selected.length !== 2} onClick={compare}>
            Confronta i 2 selezionati
          </button>
        }
      >
        <p className="note">Seleziona prima il riferimento (A), poi il candidato (B).</p>
        {comparison && <ComparisonView c={comparison} />}
        {!experiments.data ? <Loading /> : experiments.data.length === 0 ? <Empty>Nessun esperimento. Avviane uno qui sopra.</Empty> : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th /><th>Esperimento</th><th>Soggetto</th><th>Dataset</th><th>Accuratezza</th><th>Stato</th><th /></tr>
              </thead>
              <tbody>
                {experiments.data.map((e) => (
                  <ExperimentRow key={e.id} e={e} order={selected.indexOf(e.id)} onToggle={() => toggle(e.id)}
                                 open={open === e.id} onOpen={() => setOpen(open === e.id ? null : e.id)}
                                 onReproduce={() => reproduce(e.id)} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Dataset">
        {!datasets.data ? <Loading /> : (
          <ul className="plain-list">
            {datasets.data.map((d) => (
              <li key={d.ref}>
                <span className="strong mono">{d.ref}</span> <span className="muted">· {d.items} elementi · sha256 {d.hash.slice(0, 12)}</span>
                <p className="note">{d.description}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}

function RunForm({ datasets, subjects, experiments, onQueued, onError }: {
  datasets: LabDataset[];
  subjects: string[];
  experiments: LabExperiment[];
  onQueued: (msg: string) => void;
  onError: (msg: string | null) => void;
}) {
  const [dataset, setDataset] = useState(datasets.find((d) => d.name === "classify-it")?.ref ?? datasets[0]?.ref ?? "");
  const [subject, setSubject] = useState("classifier");
  const [seed, setSeed] = useState(0);
  const [sample, setSample] = useState("");
  const [remote, setRemote] = useState(false);
  const [objective, setObjective] = useState("");
  const [hypothesis, setHypothesis] = useState("");
  const [baseline, setBaseline] = useState("");
  const comparable = experiments.filter((e) => e.dataset === dataset && e.status === "completed");

  async function submit(event: FormEvent) {
    event.preventDefault();
    onError(null);
    try {
      await api("/api/tasks", {
        body: {
          kind: "lab.run",
          payload: { dataset, subject, seed, sample: sample ? Number(sample) : null, allow_remote: remote,
                     objective, hypothesis, baseline_id: baseline || null },
        },
      });
      onQueued(`Esperimento «${subject} su ${dataset}» in coda.`);
    } catch (e) {
      onError(errorText(e));
    }
  }

  return (
    <Card title="Nuovo esperimento">
      <form className="form-grid" onSubmit={submit}>
        <label>
          <span>Dataset</span>
          <select value={dataset} onChange={(e) => { setDataset(e.target.value); setBaseline(""); }}>
            {datasets.map((d) => <option key={d.ref} value={d.ref}>{d.ref} ({d.items})</option>)}
          </select>
        </label>
        <label>
          <span>Soggetto</span>
          <select value={subject} onChange={(e) => setSubject(e.target.value)}>
            {subjects.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <label>
          <span>Seed</span>
          <input type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value) || 0)} />
        </label>
        <label>
          <span>Campione (vuoto = tutto)</span>
          <input type="number" min={1} value={sample} onChange={(e) => setSample(e.target.value)} />
        </label>
        <label>
          <span>Confronta con (A)</span>
          <select value={baseline} onChange={(e) => setBaseline(e.target.value)}>
            <option value="">Nessuno</option>
            {comparable.map((e) => <option key={e.id} value={e.id}>{e.id.slice(0, 8)} · {e.subject} · {pct(e.metrics?.accuracy)}</option>)}
          </select>
        </label>
        <label className="toggle">
          <input type="checkbox" checked={remote} onChange={(e) => setRemote(e.target.checked)} />
          <span>Motore online (consuma quota gratuita)</span>
        </label>
        <label className="span-all">
          <span>Obiettivo</span>
          <input value={objective} onChange={(e) => setObjective(e.target.value)} />
        </label>
        <label className="span-all">
          <span>Ipotesi (verificata solo con un confronto)</span>
          <input value={hypothesis} onChange={(e) => setHypothesis(e.target.value)} />
        </label>
        <div className="span-all">
          <button className="button button-primary" type="submit" disabled={!dataset || !subject}>Avvia esperimento</button>
        </div>
      </form>
    </Card>
  );
}

function ExperimentRow({ e, order, onToggle, open, onOpen, onReproduce }: {
  e: LabExperiment;
  order: number;
  onToggle: () => void;
  open: boolean;
  onOpen: () => void;
  onReproduce: () => void;
}) {
  const tone = e.status === "completed" ? "ok" : e.status === "running" ? "info" : "bad";
  return (
    <>
      <tr>
        <td>
          <label className="toggle" aria-label={`Seleziona ${e.id.slice(0, 8)}`}>
            <input type="checkbox" checked={order >= 0} onChange={onToggle} disabled={e.status !== "completed"} />
            {order >= 0 && <Badge tone="accent">{order === 0 ? "A" : "B"}</Badge>}
          </label>
        </td>
        <td><span className="mono">{e.id.slice(0, 8)}</span><p className="note">{formatDate(e.created_at)}</p></td>
        <td className="mono">{e.subject}</td>
        <td className="mono">{e.dataset}</td>
        <td>
          {e.metrics ? (
            <>
              <span className="strong">{pct(e.metrics.accuracy)}</span> <span className="muted">{e.metrics.correct}/{e.metrics.n}</span>
              <Meter used={e.metrics.correct} total={e.metrics.n} label="Accuratezza" higherIsBetter />
            </>
          ) : "—"}
        </td>
        <td><Badge tone={tone}>{STATUS[e.status]}</Badge></td>
        <td className="actions">
          <button type="button" className="button button-small" onClick={onOpen}>{open ? "Chiudi" : "Dettagli"}</button>
          {e.status === "completed" && <button type="button" className="button button-small button-quiet" onClick={onReproduce}>Riproduci</button>}
        </td>
      </tr>
      {open && <tr className="details-row"><td colSpan={7}><ExperimentDetail id={e.id} /></td></tr>}
    </>
  );
}

function ExperimentDetail({ id }: { id: string }) {
  const detail = usePolling(() => api<LabDetail>(`/api/lab/experiments/${id}`), 0, [id]);
  if (detail.error) return <ErrorBanner message={detail.error} />;
  if (!detail.data) return <Loading />;
  const { experiment: x, results } = detail.data;
  const r = x.resources ?? {};
  return (
    <div className="details">
      <Facts rows={[
        ["Obiettivo", x.objective || "—"],
        ["Ipotesi", x.hypothesis || "—"],
        ["Modello e versione", x.subject_version],
        ["Dati", `${x.dataset} · sha256 ${x.dataset_hash.slice(0, 16)}…`],
        ["Seed", x.seed],
        ["Tempo", `${r.wall_s ?? "—"} s reali · ${r.cpu_s ?? "—"} s CPU · latenza media ${x.metrics?.latency_ms_mean ?? "—"} ms`],
        ["Risorse", `RAM ${r.rss_mb_before ?? "—"} → ${r.rss_mb_after ?? "—"} MB · picco processo ${r.peak_rss_mb_process ?? "—"} MB`],
        ["Riproducibilità", `${x.deterministic ? "deterministico" : "non deterministico"}${x.reproduced_from ? ` · riproduzione di ${x.reproduced_from.slice(0, 8)}` : ""}`],
      ]} />
      <h3>Valutazione</h3>
      <p>{x.evaluation}</p>
      <h3>Risultati per elemento</h3>
      <div className="table-wrap">
        <table>
          <thead><tr><th>#</th><th>Input</th><th>Atteso</th><th>Output</th><th>Esito</th></tr></thead>
          <tbody>
            {results.slice(0, 60).map((row) => (
              <tr key={row.item_idx}>
                <td>{row.item_idx}</td>
                <td>{row.input}</td>
                <td className="mono">{JSON.stringify(row.expected)}</td>
                <td className="mono">{row.output ?? <span className="muted">{row.error}</span>}</td>
                <td><Badge tone={row.correct ? "ok" : "bad"}>{row.correct ? "✓" : "✗"}</Badge></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ComparisonView({ c }: { c: LabComparison }) {
  return (
    <div className={`banner ${c.significant ? "banner-ok" : c.comparable ? "banner-info" : "banner-bad"}`} role="status">
      <p className="strong">{c.verdict}</p>
      {c.comparable && (
        <p className="note">
          A {c.a_subject}: {pct(c.accuracy_a)} · B {c.b_subject}: {pct(c.accuracy_b)} · {c.paired_items} elementi appaiati ·
          solo A corretto {c.only_a_correct}, solo B corretto {c.only_b_correct} · IC 95% della differenza [{c.diff_ci95?.join(", ")}]
        </p>
      )}
    </div>
  );
}
