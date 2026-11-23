"""Sincronización opcional con Supabase (base de datos gratuita en la nube).

Sube a Supabase lo que el bot ya guarda en disco, para verlo desde cualquier
sitio (panel, móvil, tabla de Supabase):

- ``paper_days``: un día de la prueba en papel (capital, cesta, posiciones);
- ``signals``: las señales de cada día (variante x moneda, «largo» o no, precio);
- ``scorecard``: la última tarjeta de aciertos en vivo.

Se activa SOLO si existen ``SUPABASE_URL`` y ``SUPABASE_KEY`` en el entorno.
La clave debe ser la *secret key* (o la *service_role*) del proyecto: se lee del
entorno, nunca se escribe en disco ni en el registro. Sin esas variables no hace
nada. Cada subida es un *upsert*: repetirla no duplica filas.

El esquema de las tablas, con la lectura pública de solo lectura activada por
RLS, está en ``deploy/supabase.sql``.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional, Sequence

import httpx

TABLES = {"paper_days": "day", "signals": "day,variant,symbol", "scorecard": "id"}


def configured(env: Optional[Dict[str, str]] = None) -> bool:
    env = os.environ if env is None else env
    return bool(env.get("SUPABASE_URL") and env.get("SUPABASE_KEY"))


def _day(ms: int) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ms / 1000))


def rows_from_state(directory: str) -> Dict[str, List[dict]]:
    """Convierte los archivos del bot (papel + señales) en filas para las tablas."""
    import signals as sg
    out: Dict[str, List[dict]] = {t: [] for t in TABLES}
    track = os.path.join(directory, "momentum_track.jsonl")
    if os.path.exists(track):
        with open(track, encoding="utf-8") as fh:
            rows = [json.loads(x) for x in fh if x.strip()]
        for r in rows:
            out["paper_days"].append({
                "day": _day(int(r["t"] * 1000)), "equity": r["equity"], "basket": r.get("basket", 0.0),
                "positions": r.get("weights", {}), "halted": bool(r.get("halted", False))})
    recs = sg.load(os.path.join(directory, "senales.jsonl"))
    for rec in recs:
        longs = {v: set(c) for v, c in rec["signals"].items()}
        for v, coins in longs.items():
            for s, price in rec["prices"].items():
                out["signals"].append({"day": _day(rec["day"]), "variant": v, "symbol": s,
                                       "is_long": s in coins, "price": price})
    if recs:
        card = sg.score_records(recs)
        out["scorecard"].append({"id": "live", "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                 "card": json.loads(json.dumps(card, default=list))})
    return out


def upsert(table: str, rows: Sequence[dict], url: str, key: str, http: Any = None, chunk: int = 500) -> int:
    """Inserta o actualiza ``rows`` (PostgREST, ``Prefer: resolution=merge-duplicates``)."""
    if not rows:
        return 0
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json",
               "Prefer": "resolution=merge-duplicates,return=minimal"}
    post = http.post if http is not None else httpx.post
    endpoint = f"{url.rstrip('/')}/rest/v1/{table}?on_conflict={TABLES[table]}"
    sent = 0
    for i in range(0, len(rows), chunk):
        part = list(rows[i:i + chunk])
        r = post(endpoint, headers=headers, content=json.dumps(part), timeout=20)
        code = getattr(r, "status_code", 200)
        if code >= 300:
            # nunca se imprime la clave: solo la tabla, el código y el principio de la respuesta
            raise RuntimeError(f"Supabase {table}: HTTP {code}: {str(getattr(r, 'text', ''))[:200]}")
        sent += len(part)
    return sent


def sync(directory: str, env: Optional[Dict[str, str]] = None, http: Any = None) -> Dict[str, int]:
    env = os.environ if env is None else env
    if not configured(env):
        return {}
    rows = rows_from_state(directory)
    return {t: upsert(t, rs, env["SUPABASE_URL"], env["SUPABASE_KEY"], http) for t, rs in rows.items()}
