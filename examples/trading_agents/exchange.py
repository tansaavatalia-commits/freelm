"""Conexión con el exchange vía ccxt (github.com/ccxt/ccxt, más de 100 exchanges).

Tres modos, de menos a más riesgo:

    papel    dinero simulado, datos reales (por defecto)
    testnet  órdenes reales en el entorno de pruebas del exchange (dinero ficticio)
    real     dinero real. BLOQUEADO hasta superar la prueba de 20 días.

La puerta del dinero real (``check_gate``) lee el historial del modo papel en
vivo y exige TODO esto:

- al menos 20 días de funcionamiento;
- rendimiento total positivo;
- caída máxima no superior al 10 %;
- al menos 5 operaciones cerradas.

Además, el modo real requiere ``--confirm-real-money`` y respeta un tope duro de
capital (``--max-capital``, 100 por defecto): el bot nunca usa más que eso,
aunque la cuenta tenga más saldo.

Claves: ``FREELM_EXCHANGE_KEY`` / ``FREELM_EXCHANGE_SECRET`` en el entorno.
Créalas en el exchange **solo con permiso de trading**, nunca de retirada, y
a ser posible restringidas a tu IP.
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

GATE_DAYS = 20
GATE_MAX_DD = 0.10
GATE_MIN_TRADES = 5


def to_market(symbol: str, quote: str = "USDT") -> str:
    s = symbol.upper()
    return s if "/" in s else f"{s[: -len(quote)]}/{quote}" if s.endswith(quote) else s


class CcxtExecutor:
    """Mismo interfaz que ``engine.PaperExecutor``: buy / sell / protect."""

    def __init__(self, exchange_id: str = "binance", testnet: bool = True, max_capital: float = 100.0,
                 quote: str = "USDT", client: Any = None, log: Any = None) -> None:
        self.testnet = testnet
        self.real_money = not testnet
        self.max_capital = max_capital
        self.quote = quote
        self.log = log or (lambda m: print(m, file=sys.stderr))
        self.name = f"{exchange_id} ({'testnet' if testnet else 'DINERO REAL'})"
        self.stop_orders: Dict[str, str] = {}
        if client is not None:
            self.ex = client
        else:
            try:
                import ccxt  # type: ignore[import-not-found]
            except ImportError as e:  # pragma: no cover - depende del entorno
                raise SystemExit("falta ccxt: pip install ccxt") from e
            key, secret = os.environ.get("FREELM_EXCHANGE_KEY"), os.environ.get("FREELM_EXCHANGE_SECRET")
            if not key or not secret:
                raise SystemExit("define FREELM_EXCHANGE_KEY y FREELM_EXCHANGE_SECRET (permiso de trading, "
                                 "SIN permiso de retirada)")
            self.ex = getattr(ccxt, exchange_id)({"apiKey": key, "secret": secret, "enableRateLimit": True})
            if testnet:
                self.ex.set_sandbox_mode(True)
        self.ex.load_markets()

    # ------------------------------------------------------------ saldo
    def free_quote(self) -> float:
        return float(self.ex.fetch_balance().get(self.quote, {}).get("free", 0.0) or 0.0)

    def free_base(self, symbol: str) -> float:
        base = to_market(symbol, self.quote).split("/")[0]
        return float(self.ex.fetch_balance().get(base, {}).get("free", 0.0) or 0.0)

    def starting_cash(self) -> float:
        """Capital con el que trabaja el bot: el saldo libre, con el tope duro."""
        return min(self.max_capital, self.free_quote())

    # ------------------------------------------------------------ órdenes
    def _min_ok(self, m: str, qty: float, price: float) -> bool:
        lim = self.ex.markets.get(m, {}).get("limits", {})
        min_amt = (lim.get("amount") or {}).get("min") or 0
        min_cost = (lim.get("cost") or {}).get("min") or 0
        return qty >= min_amt and qty * price >= min_cost

    def buy(self, symbol: str, qty: float, price: float) -> Tuple[float, float]:
        m = to_market(symbol, self.quote)
        qty = float(self.ex.amount_to_precision(m, qty))
        if qty <= 0 or not self._min_ok(m, qty, price):
            self.log(f"[exchange] {m}: orden por debajo del mínimo del exchange, se omite")
            return 0.0, price
        o = self.ex.create_order(m, "market", "buy", qty)
        filled = float(o.get("filled") or qty)
        avg = float(o.get("average") or o.get("price") or price)
        fee_base = sum(float(f.get("cost") or 0) for f in (o.get("fees") or [])
                       if f.get("currency") == m.split("/")[0])
        self.log(f"[exchange] COMPRA {m} {filled} a {avg}")
        return max(0.0, filled - fee_base), avg

    def protect(self, symbol: str, qty: float, stop: float) -> None:
        """Coloca (o sube) un stop-loss EN EL EXCHANGE: protege aunque el bot se caiga."""
        m = to_market(symbol, self.quote)
        self._cancel_stop(symbol)
        try:
            q = float(self.ex.amount_to_precision(m, qty))
            sp = float(self.ex.price_to_precision(m, stop))
            lp = float(self.ex.price_to_precision(m, stop * 0.99))
            o = self.ex.create_order(m, "limit", "sell", q, lp, {"stopLossPrice": sp})
            self.stop_orders[symbol] = o["id"]
        except Exception as e:  # noqa: BLE001 - si el exchange no admite el stop, queda el stop local
            self.log(f"[exchange] aviso: no se pudo colocar el stop en {m} ({type(e).__name__}: {e}); "
                     "queda solo el stop del bot")

    def _cancel_stop(self, symbol: str) -> None:
        oid = self.stop_orders.pop(symbol, None)
        if oid:
            try:
                self.ex.cancel_order(oid, to_market(symbol, self.quote))
            except Exception:  # noqa: BLE001 - puede que ya se haya ejecutado
                pass

    def sell(self, symbol: str, qty: float, price: float) -> float:
        m = to_market(symbol, self.quote)
        self._cancel_stop(symbol)
        have = self.free_base(symbol)
        q = float(self.ex.amount_to_precision(m, min(qty, have)))
        if q <= 0 or not self._min_ok(m, q, price):
            self.log(f"[exchange] {m}: no queda saldo que vender (¿saltó el stop del exchange?)")
            return price
        o = self.ex.create_order(m, "market", "sell", q)
        avg = float(o.get("average") or o.get("price") or price)
        self.log(f"[exchange] VENTA {m} {q} a {avg}")
        return avg


# ---------------------------------------------------------------- historial y puerta

def record_equity(path: str, equity: float, mode: str, now: Optional[float] = None) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps({"t": now if now is not None else time.time(), "equity": equity, "mode": mode}) + "\n")


def load_track(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def check_gate(track: List[dict], closed_trades: int) -> Tuple[bool, List[str]]:
    """¿Está el bot listo para dinero real? Devuelve (ok, motivos)."""
    rows = [r for r in track if r.get("mode") == "papel"]
    notes: List[str] = []
    if len(rows) < 2:
        return False, ["sin historial en vivo todavía: ejecuta `live` en modo papel"]
    days = (rows[-1]["t"] - rows[0]["t"]) / 86_400
    eq = [r["equity"] for r in rows]
    peak, mdd = eq[0], 0.0
    for e in eq:
        peak = max(peak, e)
        mdd = max(mdd, 1 - e / peak)
    ret = eq[-1] / eq[0] - 1
    ok = True
    for cond, msg in (
        (days >= GATE_DAYS, f"días en vivo: {days:.1f} / {GATE_DAYS}"),
        (ret > 0, f"rendimiento: {ret:+.2%} (debe ser positivo)"),
        (mdd <= GATE_MAX_DD, f"caída máxima: {mdd:.2%} (máximo {GATE_MAX_DD:.0%})"),
        (closed_trades >= GATE_MIN_TRADES, f"operaciones cerradas: {closed_trades} / {GATE_MIN_TRADES}"),
    ):
        notes.append(("OK    " if cond else "FALTA ") + msg)
        ok = ok and cond
    weeks = days / 7
    if weeks > 0 and ret > -1:
        notes.append(f"info  rendimiento semanal equivalente: {(1 + ret) ** (1 / weeks) - 1:+.2%} "
                     "(tu meta: +18 %)")
    return ok, notes
