"""Gestor de riesgo + bróker de papel (dinero simulado, NUNCA órdenes reales).

Reglas (las que repiten todos los bots serios de GitHub):
- Solo largo (spot): comprar o quedarse en liquidez.
- Tamaño por riesgo: se arriesga como mucho ``risk_per_trade`` del capital
  hasta el stop (2 x ATR), con exposición máxima ``max_exposure``.
- Stop dinámico (*trailing*) a 2 x ATR bajo el máximo desde la entrada.
- Interruptor de emergencia: si la caída desde el máximo del capital supera
  ``max_drawdown``, el bot deja de operar.
- Comisión ``fee`` por operación (0,1% como en la mayoría de exchanges).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Trade:
    time: int
    side: str
    price: float
    qty: float
    reason: str


@dataclass
class PaperBroker:
    cash: float = 10_000.0
    fee: float = 0.001
    qty: float = 0.0
    trades: List[Trade] = field(default_factory=list)

    def equity(self, price: float) -> float:
        return self.cash + self.qty * price

    def buy(self, time: int, price: float, notional: float, reason: str) -> None:
        notional = min(notional, self.cash)
        if notional <= 1e-9:
            return
        q = notional * (1 - self.fee) / price
        self.cash -= notional
        self.qty += q
        self.trades.append(Trade(time, "BUY", price, q, reason))

    def sell_all(self, time: int, price: float, reason: str) -> None:
        if self.qty <= 0:
            return
        self.cash += self.qty * price * (1 - self.fee)
        self.trades.append(Trade(time, "SELL", price, self.qty, reason))
        self.qty = 0.0


@dataclass
class RiskManager:
    enter: float = 0.15
    exit: float = -0.05
    risk_per_trade: float = 0.02
    max_exposure: float = 1.0
    atr_mult: float = 2.0
    max_drawdown: float = 0.25
    peak_equity: float = 0.0
    stop: Optional[float] = None
    high_since_entry: float = 0.0
    halted: bool = False

    def act(self, broker: PaperBroker, time: int, price: float, low: float, atr: Optional[float],
            decision: float) -> Optional[str]:
        eq = broker.equity(price)
        self.peak_equity = max(self.peak_equity, eq)
        if self.peak_equity and eq < self.peak_equity * (1 - self.max_drawdown):
            if not self.halted:
                self.halted = True
                broker.sell_all(time, price, "interruptor de emergencia: drawdown máximo")
                return "HALT"
            return None
        if self.halted:
            return None

        if broker.qty > 0:
            self.high_since_entry = max(self.high_since_entry, price)
            if atr:
                self.stop = max(self.stop or 0.0, self.high_since_entry - self.atr_mult * atr)
            if self.stop is not None and low <= self.stop:
                broker.sell_all(time, min(price, self.stop), f"stop {self.stop:.2f}")
                self.stop = None
                return "STOP"
            if decision < self.exit:
                broker.sell_all(time, price, f"consenso bajista {decision:+.2f}")
                self.stop = None
                return "SELL"
            return None

        if decision > self.enter and atr:
            stop_dist = self.atr_mult * atr / price
            frac = min(self.max_exposure, self.risk_per_trade / max(stop_dist, 1e-6)) * min(1.0, decision / 0.5)
            broker.buy(time, price, eq * frac, f"consenso alcista {decision:+.2f}")
            self.high_since_entry = price
            self.stop = price - self.atr_mult * atr
            return "BUY"
        return None
