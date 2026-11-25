"""Genesis Data Engine: CSV profiling and grouped aggregation with the standard library."""

from __future__ import annotations

import csv
import io
import statistics
from collections import Counter, defaultdict
from typing import Any, Callable

from .. import __version__
from .base import Component, EngineOpError, GenesisEngine, Operation, text_arg

MAX_ROWS = 100_000
FUNCS = ("count", "sum", "mean", "min", "max")


def _number(value: str) -> float | None:
    v = value.strip().replace(" ", "")
    if not v:
        return None
    if v.count(",") == 1 and "." not in v:
        v = v.replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return None


def read_csv(text: str) -> tuple[list[str], list[dict[str, str]]]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise EngineOpError("CSV senza intestazione")
    rows = []
    for i, row in enumerate(reader):
        if i >= MAX_ROWS:
            raise EngineOpError(f"troppe righe (massimo {MAX_ROWS})")
        rows.append({k: (v or "") for k, v in row.items() if k is not None})
    return [h.strip() for h in reader.fieldnames], rows


def profile(text: str) -> dict[str, Any]:
    headers, rows = read_csv(text)
    columns = []
    for h in headers:
        values = [r.get(h, "").strip() for r in rows]
        present = [v for v in values if v]
        numbers = [n for n in (_number(v) for v in present) if n is not None]
        col: dict[str, Any] = {"name": h, "missing": len(values) - len(present), "unique": len(set(present))}
        if present and len(numbers) == len(present):
            col.update(type="numerico", min=min(numbers), max=max(numbers), mean=round(statistics.fmean(numbers), 6),
                       median=statistics.median(numbers),
                       stdev=round(statistics.stdev(numbers), 6) if len(numbers) > 1 else 0.0)
        else:
            col.update(type="testo", top=[{"value": v, "count": c} for v, c in Counter(present).most_common(5)])
        columns.append(col)
    return {"rows": len(rows), "columns": columns}


def aggregate(text: str, group_by: str, column: str | None, fn: str) -> dict[str, Any]:
    headers, rows = read_csv(text)
    if group_by not in headers or (column is not None and column not in headers):
        raise EngineOpError(f"colonne disponibili: {', '.join(headers)}")
    if fn not in FUNCS:
        raise EngineOpError(f"funzione non valida (ammesse: {', '.join(FUNCS)})")
    if fn != "count" and column is None:
        raise EngineOpError("serve 'column' per sum/mean/min/max")
    groups: dict[str, list[float]] = defaultdict(list)
    skipped = 0
    for r in rows:
        key = r.get(group_by, "").strip()
        if fn == "count":
            groups[key].append(1.0)
            continue
        n = _number(r.get(column or "", ""))
        if n is None:
            skipped += 1
        else:
            groups[key].append(n)
    reducer = {"count": len, "sum": sum, "mean": statistics.fmean, "min": min, "max": max}[fn]
    table = [{"group": k, "value": round(reducer(v), 6)} for k, v in sorted(groups.items()) if v]
    return {"group_by": group_by, "column": column, "function": fn, "rows": table, "skipped_non_numeric": skipped}


class DataEngine(GenesisEngine):
    id, name, version = "data", "Genesis Data Engine", f"1.0@{__version__}"
    description = "Profilo delle colonne e aggregazioni di file CSV."
    components = (
        Component("lettore CSV", "algoritmo", "riconosce il separatore (, ; tab |) e la virgola decimale"),
        Component("statistiche", "algoritmo", "conteggi, valori mancanti, min/max/media/mediana/deviazione standard"),
        Component("aggregazione per gruppi", "algoritmo", "count, sum, mean, min, max"),
    )
    operations = (
        Operation("profile", 1, "profilo di un CSV", '{"text": "..."} | {"path": "file.csv"}'),
        Operation("aggregate", 1, "aggregazione per gruppi",
                  '{"path": "file.csv", "group_by": "colonna", "column": "colonna", "fn": "sum"}'),
    )

    def __init__(self, read_file: Callable[[str], str] | None = None) -> None:
        self._read = read_file

    def run(self, op: str, payload: dict[str, Any], principal: str = "owner") -> Any:
        if "path" in payload:
            if self._read is None:
                raise EngineOpError("lettura di file non disponibile")
            text = self._read(str(payload["path"]))
        else:
            text = text_arg(payload)
        if op == "profile":
            return profile(text)
        if op == "aggregate":
            return aggregate(text, str(payload.get("group_by", "")), payload.get("column"), str(payload.get("fn", "count")))
        raise EngineOpError(f"operazione sconosciuta: {op}")
