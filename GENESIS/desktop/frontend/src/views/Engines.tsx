import { useState, type FormEvent } from "react";
import { api, errorText, usePolling, waitForTask } from "../api";
import type { GenesisEngineManifest, ModelsResponse } from "../types";
import { Badge, Card, ErrorBanner, gb, Loading, PageHeader } from "../ui";

const KIND_TONE = { algoritmo: "ok", strumento: "info", "modello esterno": "warn" } as const;
const VERDICT_TONE: Record<string, "ok" | "warn" | "bad"> = { eseguibile: "ok", "al limite": "warn", "non eseguibile": "bad" };

export function Engines() {
  const engines = usePolling(() => api<GenesisEngineManifest[]>("/api/genesis-engines"), 0);
  const models = usePolling(() => api<ModelsResponse>("/api/models"), 0);
  return (
    <>
      <PageHeader title="Motori e modelli" subtitle="Ogni motore dichiara cosa è un algoritmo scritto in GÉNESIS, cosa è uno strumento e cosa sarebbe un modello esterno." />
      <ErrorBanner message={engines.error ?? models.error} />
      {engines.data && <TryEngine engines={engines.data} />}
      <div className="grid grid-2">
        {!engines.data ? <Loading /> : engines.data.map((e) => (
          <Card key={e.id} title={e.name} actions={<Badge tone={e.uses_external_model ? "warn" : "ok"}>{e.uses_external_model ? "usa un modello esterno" : "solo algoritmi propri"}</Badge>}>
            <p className="note">{e.description} · v{e.version}</p>
            <ul className="plain-list">
              {e.components.map((c) => (
                <li key={c.name}>
                  <Badge tone={c.available ? KIND_TONE[c.kind] : "muted"}>{c.kind}{c.available ? "" : " · non disponibile"}</Badge>{" "}
                  <span className="strong">{c.name}</span>
                  <p className="note">{c.description}</p>
                </li>
              ))}
            </ul>
            <p className="note">Operazioni: {e.operations.map((o) => o.name).join(", ")}</p>
          </Card>
        ))}
      </div>
      <Card title="Modelli aperti (Fase 8)">
        {!models.data ? <Loading /> : (
          <>
            <p className="note">
              Questo PC: RAM {gb(models.data.hardware.ram_mb)} · VRAM {models.data.hardware.vram_mb} MB · profilo {models.data.hardware.profile}.
              Stime indicative; i dati dei modelli non sono verificati: controllare sempre la scheda ufficiale.
            </p>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Modello</th><th>Parametri</th><th>Licenza</th><th>Su questo PC</th></tr></thead>
                <tbody>
                  {models.data.models.map((m) => (
                    <tr key={m.id}>
                      <td><a className="link" href={m.source} target="_blank" rel="noreferrer noopener">{m.id}</a></td>
                      <td>{m.params_b} miliardi</td>
                      <td>{m.license}</td>
                      <td>
                        <Badge tone={VERDICT_TONE[m.best.verdict] ?? "muted"}>{m.best.verdict}</Badge>{" "}
                        <span className="muted">{m.best.quant} · {m.best.need.total_gb} GB · {m.best.where}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Card>
    </>
  );
}

function TryEngine({ engines }: { engines: GenesisEngineManifest[] }) {
  const [engineId, setEngineId] = useState(engines[0]?.id ?? "");
  const engine = engines.find((e) => e.id === engineId);
  const [opName, setOpName] = useState(engine?.operations[0]?.name ?? "");
  const op = engine?.operations.find((o) => o.name === opName) ?? engine?.operations[0];
  const [payload, setPayload] = useState('{"text": "Quanto fa 15 per 4?"}');
  const [result, setResult] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setResult(null);
    let parsed: unknown;
    try {
      parsed = JSON.parse(payload);
    } catch {
      setError("Il payload deve essere JSON valido.");
      return;
    }
    setBusy(true);
    try {
      const task = await api<{ id: string }>("/api/tasks", { body: { kind: "engines.run", payload: { engine: engineId, op: op?.name, payload: parsed } } });
      setResult(await waitForTask(task.id));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Prova un motore">
      <form className="form-grid" onSubmit={submit}>
        <label>
          <span>Motore</span>
          <select value={engineId} onChange={(e) => { setEngineId(e.target.value); setOpName(engines.find((x) => x.id === e.target.value)?.operations[0]?.name ?? ""); }}>
            {engines.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
          </select>
        </label>
        <label>
          <span>Operazione</span>
          <select value={op?.name ?? ""} onChange={(e) => setOpName(e.target.value)}>
            {engine?.operations.map((o) => <option key={o.name} value={o.name}>{o.name}</option>)}
          </select>
        </label>
        <label className="span-all">
          <span>Payload (JSON) — esempio: {op?.params}</span>
          <textarea rows={2} value={payload} onChange={(e) => setPayload(e.target.value)} spellCheck={false} />
        </label>
        {op && <p className="note span-all">{op.description} · livello {op.level}</p>}
        {error && <p className="field-error span-all" role="alert">{error}</p>}
        <div className="span-all"><button className="button button-primary" type="submit" disabled={busy}>{busy ? "In esecuzione…" : "Esegui"}</button></div>
      </form>
      {result !== null && <pre className="pre" aria-label="Risultato del motore">{JSON.stringify(result, null, 2)}</pre>}
    </Card>
  );
}
