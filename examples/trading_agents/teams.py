"""Equipos y consejo: donde las señales se confrontan.

Nivel 1, el **equipo**. Sus agentes votan con los pesos que el equipo ha
aprendido para el régimen actual. El veredicto incluye la dirección y el
grado de acuerdo interno.

Nivel 2, el **consejo**. Combina los veredictos de los equipos con pesos
también aprendidos. Además, un **equipo escéptico** puede vetar la operación.
Su lista de comprobaciones es fija:

  - los equipos no están de acuerdo (acuerdo ponderado < ``min_agreement``);
  - el mercado está en régimen volátil;
  - comprar contra la tendencia mayor (precio bajo la EMA 200);
  - el calibrador no ha visto ventaja neta demostrada en ese tipo de señal;
  - (si está activo) el analista IA opina en contra.

Una operación solo se abre si pasa todos los filtros. La mayoría de las
señales se descartan, y está bien: el objetivo es operar poco y con sentido.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from agents import Agent, Signal
from features import Features
from learning import Calibrator, Coordinator, bucket


class Team:
    def __init__(self, name: str, agents: Sequence[Agent], state: Optional[dict] = None) -> None:
        self.name = name
        self.agents = list(agents)
        self.coord = Coordinator.from_dict(state, [a.name for a in self.agents], eta=0.3, alpha=0.02)

    def verdict(self, f: Features, regime: str) -> tuple:
        signals = [a.analyze(f) for a in self.agents]
        score, agree = self.coord.combine(signals, regime)
        return Signal(self.name, score, agree, f"{len(signals)} agentes, acuerdo {agree:.0%}"), signals


@dataclass
class Decision:
    symbol: str
    score: float
    agreement: float
    regime: str
    key: str
    vetoes: List[str] = field(default_factory=list)
    teams: List[Signal] = field(default_factory=list)
    edge_note: str = ""

    @property
    def approved(self) -> bool:
        return not self.vetoes


class Council:
    def __init__(self, team_names: List[str], calibrator: Calibrator, state: Optional[dict] = None,
                 enter: float = 0.15, min_agreement: float = 0.6, block_volatile: bool = True,
                 trend_filter: bool = True) -> None:
        self.coord = Coordinator.from_dict(state, team_names, eta=0.5, alpha=0.03)
        self.cal = calibrator
        self.enter, self.min_agreement = enter, min_agreement
        self.block_volatile, self.trend_filter = block_volatile, trend_filter
        self.veto_counts: Dict[str, int] = {}

    def decide(self, symbol: str, f: Features, regime: str, team_signals: List[Signal]) -> Decision:
        score, agree = self.coord.combine(team_signals, regime)
        d = Decision(symbol, score, agree, regime, bucket(regime, abs(score), agree), teams=team_signals)
        if score < self.enter:
            d.vetoes.append("sin consenso alcista")
            return d  # ni siquiera es candidata: no se cuenta como veto
        if agree < self.min_agreement:
            d.vetoes.append(f"desacuerdo entre equipos ({agree:.0%})")
        if self.block_volatile and regime == "volátil":
            d.vetoes.append("régimen volátil")
        if self.trend_filter:
            long_ema = f.ema(200)[-1] or f.ema(100)[-1]
            if long_ema is not None and f.price < long_ema:
                d.vetoes.append("contra la tendencia mayor (EMA200)")
        ok, note = self.cal.approved(d.key)
        d.edge_note = note
        if not ok:
            d.vetoes.append(note)
        for v in d.vetoes:
            k = v.split(" (")[0]
            self.veto_counts[k] = self.veto_counts.get(k, 0) + 1
        return d
