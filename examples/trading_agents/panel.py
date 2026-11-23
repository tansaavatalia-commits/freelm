"""Panel HTML autónomo: cómo va la prueba en papel y cuánto aciertan las señales.

``python bot.py panel`` genera un solo archivo ``panel.html`` (sin internet, sin
librerías) con:

- capital en papel frente a la cesta comprar y mantener (gráfico SVG);
- posiciones actuales y estado (días, caída, detenido o no);
- tarjeta de aciertos EN VIVO (señales registradas, puntuadas con precios posteriores);
- señales de los últimos días y avisos del diario de decisiones.

Se abre con doble clic en el navegador (el asistente de Windows lo hace), y GitHub
Actions lo regenera cada día en la rama ``momentum-state``. Todo valor se escapa:
el panel no ejecuta nada que venga de los datos.
"""
from __future__ import annotations

import html
import json
import os
import time
from typing import Dict, List, Sequence

PAPER_DAYS = 20


def _e(x: object) -> str:
    return html.escape(str(x), quote=True)


def _day(ms: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ms / 1000))


def _pct(x: float, signed: bool = True) -> str:
    return f"{x:+.2%}" if signed else f"{x:.1%}"


def _load_jsonl(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def _chart(track: Sequence[dict], w: int = 520, h: int = 240) -> str:
    if len(track) < 2:
        return '<p class="muted">El gráfico aparece a partir del segundo día de la prueba.</p>'
    eq = [r["equity"] / track[0]["equity"] - 1 for r in track]
    bk = [r.get("basket", 0.0) for r in track]
    lo, hi = min(eq + bk + [0.0]), max(eq + bk + [0.0])
    span = (hi - lo) or 0.01
    pad, left = 24, 58

    def xy(i: int, v: float) -> str:
        x = left + (w - left - pad) * i / (len(track) - 1)
        y = pad + (h - 2 * pad) * (hi - v) / span
        return f"{x:.1f},{y:.1f}"

    zero = pad + (h - 2 * pad) * (hi - 0.0) / span
    def line(vals: Sequence[float], cls: str) -> str:
        pts = " ".join(xy(i, v) for i, v in enumerate(vals))
        return f'<polyline class="{cls}" fill="none" stroke-width="2.5" points="{pts}"/>'

    labels = (f'<text x="{left}" y="{h - 4}" class="axis">{_e(_day(track[0]["t"] * 1000))}</text>'
              f'<text x="{w - pad}" y="{h - 4}" class="axis" text-anchor="end">{_e(_day(track[-1]["t"] * 1000))}</text>'
              f'<text x="{left - 6}" y="{pad + 4}" class="axis" text-anchor="end">{_e(_pct(hi))}</text>'
              f'<text x="{left - 6}" y="{h - pad + 4}" class="axis" text-anchor="end">{_e(_pct(lo))}</text>')
    return (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Capital en papel frente a la cesta">'
            f'<line x1="{left}" x2="{w - pad}" y1="{zero:.1f}" y2="{zero:.1f}" class="zero"/>'
            f'{line(bk, "basket")}{line(eq, "equity")}{labels}</svg>'
            '<p class="legend"><span class="sw equity"></span>Bot en papel <span class="sw basket"></span>'
            'Cesta comprar y mantener</p>')


def _card_table(card: Dict[str, Dict], horizons: Sequence[int] = (1, 7, 30)) -> str:
    if not card:
        return '<p class="muted">Todavía no hay señales puntuables (hace falta al menos 1 día).</p>'
    head = "".join(f"<th>{h} d: acierto</th><th>base</th><th>ventaja</th>" for h in horizons)
    rows = []
    order = (["conjunto"] if "conjunto" in card else []) + sorted(k for k in card if k != "conjunto")
    for k in order:
        v = card[k]
        cells = []
        for h in horizons:
            r = v.get(h) or v.get(str(h))
            if not r or not r.get("n"):
                cells.append('<td class="muted">—</td><td></td><td></td>')
                continue
            good = "good" if r.get("edge_real") else ""
            hit, base, n = format(r["hit"], ".0%"), format(r["base"], ".0%"), r["n"]
            cells.append(f"<td>{_e(hit)} <small>(n={_e(n)})</small></td>"
                         f"<td>{_e(base)}</td><td class='{good}'>{_e(_pct(r['edge']))}</td>")
        cls = ' class="total"' if k == "conjunto" else ""
        rows.append(f"<tr{cls}><th>{_e(k)}</th>{''.join(cells)}</tr>")
    return f'<div class="scroll"><table><tr><th>señal</th>{head}</tr>{"".join(rows)}</table></div>'


def build(directory: str) -> str:
    import signals as sg
    track = _load_jsonl(os.path.join(directory, "momentum_track.jsonl"))
    state: dict = {}
    sp = os.path.join(directory, "momentum_state.json")
    if os.path.exists(sp):
        with open(sp, encoding="utf-8") as fh:
            state = json.load(fh)
    recs = sg.load(os.path.join(directory, "senales.jsonl"))
    card = sg.score_records(recs) if recs else {}
    journal_dir = os.path.join(directory, "diario")
    events: List[dict] = []
    if os.path.isdir(journal_dir):
        for f in sorted(os.listdir(journal_dir))[-10:]:
            events += [r for r in _load_jsonl(os.path.join(journal_dir, f))
                       if r.get("tipo") in ("aviso", "orden_papel", "reinicio") and r.get("estrategia") == "momentum"]
    # tras un reinicio por cambio de configuración, solo lo posterior
    marks = [i for i, r in enumerate(events) if r.get("tipo") == "reinicio"]
    if marks:
        events = events[marks[-1]:]
    start = state.get("start_day")
    if start is not None:  # solo lo de la prueba actual (tras un reinicio por cambio de configuración)
        recs = [r for r in recs if r["day"] >= start]
        card = sg.score_records(recs) if recs else {}
    cash0 = state.get("cash0", 100.0)
    equity = state.get("equity", cash0)
    peak, mdd = (track[0]["equity"] if track else cash0), 0.0
    for r in track:
        peak = max(peak, r["equity"])
        mdd = max(mdd, 1 - r["equity"] / peak)
    days = state.get("days", 0)
    basket = track[-1].get("basket", 0.0) if track else 0.0
    weights = state.get("weights", {})
    pos = ", ".join(f"{_e(s)} {w:.0%}" for s, w in sorted(weights.items(), key=lambda kv: -kv[1])) or "ninguna (liquidez)"
    status = "DETENIDO (caída > 10 %)" if state.get("halted") else (
        "prueba completa" if days >= PAPER_DAYS else "en marcha")
    last_sig = []
    for rec in recs[-7:][::-1]:
        longs = sorted(set().union(*rec["signals"].values())) if rec["signals"] else []
        votes = {s: sum(s in v for v in rec["signals"].values()) for s in longs}
        txt = ", ".join(f"{_e(s)} ({votes[s]}/10)" for s in longs) or '<span class="muted">todas «fuera»</span>'
        last_sig.append(f"<tr><th>{_e(_day(rec['day']))}</th><td>{txt}</td></tr>")
    ev = "".join(f"<li><b>{_e(r.get('utc', ''))}</b> {_e(r.get('tipo'))}: "
                 f"{_e(r.get('motivo') or (str(r.get('simbolo', '')) + ' ' + str(r.get('lado', ''))))}</li>"
                 for r in events[-12:][::-1]) or '<li class="muted">sin avisos</li>'
    updated = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Panel del bot</title>
<style>
:root{{--bg:#f6f7f9;--card:#fff;--fg:#1d2330;--muted:#6b7280;--line:#e3e6eb;--eq:#2563eb;--bk:#9ca3af;--good:#15803d;--warn:#b45309}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#0f1218;--card:#171b23;--fg:#e6e9ef;--muted:#9aa3b2;--line:#2a303b;--eq:#60a5fa;--bk:#6b7280;--good:#4ade80;--warn:#fbbf24}}}}
:root[data-theme="dark"]{{--bg:#0f1218;--card:#171b23;--fg:#e6e9ef;--muted:#9aa3b2;--line:#2a303b;--eq:#60a5fa;--bk:#6b7280;--good:#4ade80;--warn:#fbbf24}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
main{{max-width:900px;margin:0 auto;padding:20px 16px 40px}}h1{{font-size:22px;margin:0 0 4px}}h2{{font-size:16px;margin:0 0 10px}}
.muted{{color:var(--muted)}}section{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-top:14px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}}.kpi b{{display:block;font-size:22px}}
svg{{width:100%;height:auto}}.equity{{stroke:var(--eq)}}.basket{{stroke:var(--bk)}}.zero{{stroke:var(--line)}}.axis{{fill:var(--muted);font-size:13px}}
.legend{{font-size:13px;color:var(--muted)}}.sw{{display:inline-block;width:14px;height:3px;margin:0 6px 3px 10px;vertical-align:middle}}
.sw.equity{{background:var(--eq)}}.sw.basket{{background:var(--bk)}}
.scroll{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}}
tr.total th,tr.total td{{font-weight:600}}.good{{color:var(--good);font-weight:600}}.warn{{color:var(--warn)}}ul{{margin:0;padding-left:18px}}
</style></head><body><main>
<h1>Bot de trading · prueba en papel</h1>
<p class="muted">Momentum combinado, 100 € simulados. Nunca opera con dinero real. Actualizado {_e(updated)}.</p>
<section class="kpis">
<div class="kpi"><span class="muted">Día</span><b>{_e(days)}/{PAPER_DAYS}</b><span class="muted">{_e(status)}</span></div>
<div class="kpi"><span class="muted">Capital</span><b>{_e(format(equity, ".2f"))} €</b><span class="muted">{_e(_pct(equity / cash0 - 1))}</span></div>
<div class="kpi"><span class="muted">Cesta (comprar y mantener)</span><b>{_e(_pct(basket))}</b></div>
<div class="kpi"><span class="muted">Caída máxima</span><b class="{'warn' if mdd > 0.05 else ''}">{_e(_pct(mdd, False))}</b><span class="muted">límite 10 %</span></div>
</section>
<section><h2>Capital frente a la cesta</h2>{_chart(track)}<p>Posiciones: {pos}</p></section>
<section><h2>Tarjeta de aciertos EN VIVO</h2>
<p class="muted">Cada señal se puntúa con precios posteriores, se opere o no. Acierto = % de «largo» tras los que la moneda
subió; base = % de veces que subió sin señal; ventaja = retorno tras «largo» menos tras «fuera» (en verde si es
significativa al 95 %).</p>{_card_table(card)}</section>
<section><h2>Señales de los últimos días</h2><div class="scroll"><table>{''.join(last_sig) or '<tr><td class="muted">sin señales registradas</td></tr>'}</table></div></section>
<section><h2>Diario: órdenes en papel y avisos</h2><ul>{ev}</ul></section>
</main></body></html>"""


def write(directory: str, out: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(build(directory))
    return out
