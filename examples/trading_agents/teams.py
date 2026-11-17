"""Equipos: un grupo de agentes que delibera con los pesos que ha aprendido.

El veredicto de un equipo es una ``Signal`` cuyo ``score`` es el voto
ponderado de sus agentes y cuya ``confidence`` es el grado de acuerdo interno.
La confrontación entre equipos (consejo), los vetos y el filtro de ventaja
están en los nodos del grafo (engine.py).
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from agents import Agent, Signal
from features import Features
from learning import Coordinator


class Team:
    def __init__(self, name: str, agents: Sequence[Agent], state: Optional[dict] = None, eta: float = 0.3) -> None:
        self.name = name
        self.agents = list(agents)
        self.coord = Coordinator.from_dict(state, [a.name for a in self.agents], eta=eta, alpha=0.02)
        self.coord.eta = eta

    def observe(self, f: Features) -> Tuple[Tuple[float, ...], Tuple[float, ...], List[Signal]]:
        sigs = [a.analyze(f) for a in self.agents]
        return tuple(s.score for s in sigs), tuple(s.confidence for s in sigs), sigs

    def verdict(self, scores: Sequence[float], confs: Sequence[float], regime: str,
                values: Optional[Sequence[float]] = None) -> Signal:
        score, agree = self.coord.combine_arrays(scores, confs, regime, values)
        return Signal(self.name, score, agree, f"{len(scores)} agentes, acuerdo {agree:.0%}")
