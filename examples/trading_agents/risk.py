"""Gestión de riesgo y cartera de papel multi-símbolo (dinero simulado, NUNCA órdenes reales).

Reglas:
- Solo largo (spot), sin apalancamiento.
- Riesgo fijo por operación: ``risk_per_trade`` (1%) del capital entre la entrada
  y el stop (``stop_atr`` x ATR). Objetivo a ``target_atr`` x ATR, es decir, una
  relación beneficio/riesgo mínima de 2:1.
- Cuando el precio avanza 1R, el stop sube a la entrada (break-even); después
  persigue al máximo a ``stop_atr`` x ATR. Una operación ganadora no vuelve a pérdidas.
- Como mucho ``max_positions`` posiciones a la vez y ``max_exposure`` del capital
  en cada una.
- Tras ``max_losing_streak`` pérdidas seguidas, pausa de ``cooldown`` velas.
- Interruptor: si el capital cae ``max_drawdown`` desde su máximo, se cierra todo
  y se deja de operar.
- Comisión ``fee`` (0,1%) en cada lado.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class Position:
    symbol: str
    qty: float
    entry: float
    stop: float
    target: float
    risk_per_unit: float
    opened: int
    high: float
    reason: str
    risk_frac: float = 0.0  # fracción del capital arriesgada al abrir (qty * distancia al stop / capital)


@dataclass
class ClosedTrade:
    symbol: str
    opened: int
    closed: int
    entry: float
    exit: float
    qty: float
    pnl: float
    r: float
    why: str
    risk_frac: float = 0.0

    @property
    def equity_return(self) -> float:
        """Efecto de la operación sobre el capital (r x fracción arriesgada de verdad)."""
        return self.r * self.risk_frac


@dataclass
class Portfolio:
    cash: float = 10_000.0
    fee: float = 0.001
    positions: Dict[str, Position] = field(default_factory=dict)
    closed: List[ClosedTrade] = field(default_factory=list)

    def equity(self, prices: Dict[str, float]) -> float:
        return self.cash + sum(p.qty * prices.get(s, p.entry) for s, p in self.positions.items())

    def open(self, pos: Position) -> None:
        cost = pos.qty * pos.entry
        self.cash -= cost * (1 + self.fee)
        self.positions[pos.symbol] = pos

    def close(self, symbol: str, price: float, time: int, why: str) -> ClosedTrade:
        p = self.positions.pop(symbol)
        proceeds = p.qty * price * (1 - self.fee)
        self.cash += proceeds
        pnl = proceeds - p.qty * p.entry * (1 + self.fee)
        t = ClosedTrade(symbol, p.opened, time, p.entry, price, p.qty, pnl, pnl / (p.qty * p.risk_per_unit), why,
                        p.risk_frac)
        self.closed.append(t)
        return t


@dataclass
class RiskManager:
    risk_per_trade: float = 0.01
    stop_atr: float = 1.5
    target_atr: float = 3.0
    max_positions: int = 4
    max_exposure: float = 0.30
    max_drawdown: float = 0.12
    max_losing_streak: int = 3
    cooldown: int = 24
    exit_score: float = -0.2
    peak_equity: float = 0.0
    losing_streak: int = 0
    pause_left: int = 0
    halted: bool = False

    def levels(self, price: float, atr: float) -> tuple:
        return price - self.stop_atr * atr, price + self.target_atr * atr

    def can_open(self, pf: Portfolio) -> Optional[str]:
        if self.halted:
            return "interruptor activado"
        if self.pause_left > 0:
            return f"pausa tras {self.max_losing_streak} pérdidas ({self.pause_left} velas)"
        if len(pf.positions) >= self.max_positions:
            return "máximo de posiciones"
        return None

    def size(self, pf: Portfolio, equity: float, price: float, atr: float) -> float:
        stop_dist = self.stop_atr * atr
        qty = equity * self.risk_per_trade / stop_dist
        qty = min(qty, equity * self.max_exposure / price, pf.cash / (price * (1 + pf.fee)))
        return max(0.0, qty)

    def check_exit(self, pf: Portfolio, symbol: str, high: float, low: float, close: float,
                   atr: Optional[float], score: float) -> Optional[Tuple[float, str]]:
        """Revisa una posición abierta con la vela nueva y devuelve (precio, motivo)
        si hay que salir. El stop se evalúa antes que el objetivo (supuesto
        pesimista cuando ambos caben en la vela). Si no hay salida, actualiza el stop."""
        p = pf.positions.get(symbol)
        if not p:
            return None
        if low <= p.stop:
            return p.stop, ("stop" if p.stop < p.entry else "stop de protección")
        if high >= p.target:
            return p.target, "objetivo alcanzado"
        if score < self.exit_score:
            return close, f"el consejo gira bajista ({score:+.2f})"
        p.high = max(p.high, high)
        if p.high >= p.entry + p.risk_per_unit:
            p.stop = max(p.stop, p.entry * (1 + 2 * pf.fee))  # break-even cubriendo comisiones
        if atr and p.stop >= p.entry:
            p.stop = max(p.stop, p.high - self.stop_atr * atr)
        return None

    def on_closed(self, t: ClosedTrade) -> None:
        self.losing_streak = self.losing_streak + 1 if t.pnl < 0 else 0
        if self.losing_streak >= self.max_losing_streak:
            self.pause_left, self.losing_streak = self.cooldown, 0

    def manage(self, pf: Portfolio, symbol: str, time: int, high: float, low: float, close: float,
               atr: Optional[float], score: float) -> Optional[ClosedTrade]:
        """Versión papel: decide y cierra en el mismo paso."""
        ex = self.check_exit(pf, symbol, high, low, close, atr, score)
        if not ex:
            return None
        t = pf.close(symbol, ex[0], time, ex[1])
        self.on_closed(t)
        return t

    def tick(self, equity: float) -> Optional[str]:
        """Una vez por paso: pausa y control de drawdown global. Si devuelve
        "HALT", quien llama debe cerrar todas las posiciones."""
        if self.pause_left > 0:
            self.pause_left -= 1
        self.peak_equity = max(self.peak_equity, equity)
        if not self.halted and self.peak_equity and equity < self.peak_equity * (1 - self.max_drawdown):
            self.halted = True
            return "HALT"
        return None
