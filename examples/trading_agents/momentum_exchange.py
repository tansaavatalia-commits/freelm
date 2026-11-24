"""Momentum combinado con órdenes de verdad en el exchange (de momento, solo TESTNET).

La prueba en papel (``momentum_paper``) decide cada día los pesos objetivo. Este
módulo los ejecuta en el exchange con un **libro propio**:

- ``cash``: lo que el bot puede usar (como mucho ``max_capital``);
- ``qty``: lo que el bot compró de cada moneda.

El libro hace falta porque la cuenta de la testnet de Binance viene con saldos
ficticios de muchas monedas, y en una cuenta real puede haber otras cosas tuyas.
El bot solo mueve lo que él compró y nunca más capital del tope.

Cada día, tras el cierre, se lleva el libro a los pesos objetivo: primero las
ventas (liberan liquidez) y después las compras. Una diferencia menor que el
mínimo de orden no se opera. Los ids de orden son deterministas por moneda y día,
así que un reintento tras un corte de red no duplica nada. Un día que falla no
se marca como hecho, y se reintenta en la siguiente ejecución.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List

MIN_ORDER = 6.0  # USDT: algo por encima del mínimo de Binance (5) para no rozarlo


def new_book(cash: float) -> dict:
    return {"cash": round(cash, 8), "qty": {}, "last_day": None, "cash0": round(cash, 8)}


def book_equity(book: dict, prices: Dict[str, float]) -> float:
    return book["cash"] + sum(q * prices.get(s, 0.0) for s, q in book["qty"].items())


def rebalance(executor: Any, book: dict, weights: Dict[str, float], prices: Dict[str, float], day_ms: int,
              fee: float = 0.001, min_order: float = MIN_ORDER,
              log: Callable[[str], None] = lambda m: None) -> List[dict]:
    """Lleva el libro a ``weights`` (fracción del capital del libro). Devuelve las órdenes hechas."""
    if hasattr(executor, "step_time"):
        executor.step_time = day_ms  # ids de orden por día: un reintento no duplica
    equity = book_equity(book, prices)
    fills: List[dict] = []
    # 1) ventas
    for s in sorted(book["qty"]):
        q, px = book["qty"][s], prices.get(s)
        if not px or q <= 0:
            continue
        target = weights.get(s, 0.0) * equity
        diff = target - q * px
        if target <= 0 or diff < -min_order:
            sell_q = q if target <= 0 else min(q, -diff / px)
            if sell_q * px < min_order and target > 0:
                continue
            avg = executor.sell(s, sell_q, px)
            book["qty"][s] = max(0.0, q - sell_q)
            book["cash"] += sell_q * avg * (1 - fee)
            fills.append({"symbol": s, "side": "venta", "qty": sell_q, "price": avg})
            log(f"VENTA {s} {sell_q:.6g} a {avg:.6g}")
            if book["qty"][s] * px < 1e-9 or book["qty"][s] * px < min_order / 10:
                book["qty"].pop(s, None)
    # 2) compras
    for s in sorted(weights):
        px = prices.get(s)
        if not px:
            continue
        cur = book["qty"].get(s, 0.0) * px
        diff = weights[s] * equity - cur
        spend = min(diff, book["cash"] / (1 + fee))
        if spend < min_order:
            continue
        got, avg = executor.buy(s, spend / px, px)
        if got <= 0:
            continue
        book["qty"][s] = book["qty"].get(s, 0.0) + got
        book["cash"] -= got * avg * (1 + fee)
        fills.append({"symbol": s, "side": "compra", "qty": got, "price": avg})
        log(f"COMPRA {s} {got:.6g} a {avg:.6g}")
    book["cash"] = max(0.0, book["cash"])
    book["last_day"] = day_ms
    return fills
