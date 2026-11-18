"""El motor como grafo de nodos enlazados.

Cada vela, cada símbolo recorre este grafo. Las flechas son los datos que un
nodo entrega al siguiente; ``python bot.py graph`` lo dibuja en Mermaid.

    vela ─► aprender ──────────────┐
    vela ─► resolver_sombras ──┐   │
    ventana ─► observar ─► equipo:tendencia ─┐
                       ├─► equipo:reversión ─┤
                       ├─► equipo:flujo ─────┼─► consejo ─► escéptico ─► filtro_ventaja ─┐
                       ├─► equipo:volatilidad┤      │                                    ├─► candidata
                       └─► equipo:multi-marco┘      ├─► registrar_sombra                 │
                                                    ├─► gestionar_posición ──────────────┘
                                                    └─► recordar (para aprender en la vela siguiente)

Después, un grafo de cartera: guardián (drawdown, pausa) ─► asignar (revisión
IA, tamaño, orden). Los nodos se añaden, se quitan o se reconectan sin tocar
el resto: ``Graph`` calcula el orden de ejecución a partir de lo que cada
nodo necesita (``needs``) y produce (``provides``).

Todos los parámetros ajustables viven en ``Config``. Eso es lo que optimiza
``optimize.py``.
"""
from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from agents import Agent, LLMAnalystAgent, Signal, agent_swarm
from features import Features
from learning import Calibrator, Coordinator, bucket, detect_regime
from market import Candle, market_context
from risk import ClosedTrade, Portfolio, Position, RiskManager
from safety import check_window
from teams import Team

WINDOW = 320
SHADOW_GAP = 6  # como mucho una operación en la sombra por símbolo cada N velas


# --------------------------------------------------------------------------- configuración

@dataclass
class Config:
    enter: float = 0.15            # fuerza mínima del consejo para considerar comprar
    min_agreement: float = 0.6     # acuerdo mínimo entre equipos
    min_edge: float = 0.15         # ventaja conservadora mínima (en R) exigida por el calibrador
    min_samples: int = 40          # casos en la sombra antes de confiar en un tipo de señal
    # Con datos reales de Binance (2026), el único tipo de señal con ventaja neta fue
    # justo «volátil + fuerza alta + acuerdo alto». Ya no se veta el régimen volátil
    # entero: el filtro de ventaja (calibrador) decide con evidencia en cada caso.
    block_volatile: bool = False
    trend_filter: bool = True      # no comprar bajo la EMA 200
    risk_per_trade: float = 0.01
    stop_atr: float = 1.5
    target_atr: float = 3.0
    max_positions: int = 4
    max_exposure: float = 0.30
    max_drawdown: float = 0.10     # interruptor: la caída máxima acordada
    exit_score: float = -0.2
    team_eta: float = 0.3
    council_eta: float = 0.5
    shadow_horizon: int = 48
    riskoff: bool = True           # no comprar con BTC bajo su media 200 y poca amplitud
    riskoff_breadth: float = 0.35
    max_heat: float = 0.03         # riesgo total abierto (suma de distancias al stop) <= 3 % del capital
    max_daily_loss: float = 0.03   # pérdida diaria que bloquea nuevas entradas hasta el día siguiente (UTC)
    # --- modo «alta probabilidad» (petición del usuario: solo operar con >= 77 % de acierto VERIFICADO)
    min_win_prob: float = 0.77     # cota inferior de Wilson de la probabilidad de cerrar en positivo
    prob_z: float = 3.0            # z de esa cota: 3 ~ 99,9 %, corrige las muchas pruebas (tipos x perfiles)
    exit_profiles: Tuple[float, ...] = (0.75, 1.125, 1.5, 3.0)  # objetivos en ATR (stop fijo = stop_atr)
    # --- costes y tipo de orden de entrada
    entry_mode: str = "market"     # "market" (taker + deslizamiento) o "limit" (maker, puede no ejecutarse)
    maker_fee: float = 0.001       # Binance spot estándar: 0,1 % (0,075 % pagando con BNB)
    taker_fee: float = 0.001
    limit_offset_atr: float = 0.0  # la orden límite se coloca a close - offset x ATR
    limit_wait: int = 2            # velas que espera la orden límite antes de cancelarse
    # en modo límite, ¿el objetivo se cobra con venta límite (maker)? En papel sí; en el exchange
    # real el objetivo se vigila vela a vela y se vende a mercado (el stop ya está puesto en el
    # exchange y Binance no deja dos órdenes de venta sobre las mismas monedas sin OCO)
    target_maker: bool = True
    teams: Tuple[str, ...] = ()    # vacío = todos los equipos

    def to_dict(self) -> dict:
        d = asdict(self)
        d["teams"] = list(self.teams)
        d["exit_profiles"] = list(self.exit_profiles)
        return d

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "Config":
        if not d:
            return cls()
        names = {f.name for f in fields(cls)}
        kw = {k: v for k, v in d.items() if k in names}
        for k in ("teams", "exit_profiles"):
            if k in kw:
                kw[k] = tuple(kw[k])
        return cls(**kw)


# --------------------------------------------------------------------------- grafo

@dataclass
class Node:
    name: str
    needs: Tuple[str, ...]
    provides: Tuple[str, ...]
    fn: Callable[[Dict[str, Any]], None]
    doc: str = ""


class Graph:
    def __init__(self, name: str) -> None:
        self.name = name
        self.nodes: List[Node] = []
        self._order: Optional[List[Node]] = None

    def add(self, node: Node) -> "Graph":
        self.nodes.append(node)
        self._order = None
        return self

    def remove(self, name: str) -> "Graph":
        self.nodes = [n for n in self.nodes if n.name != name]
        self._order = None
        return self

    def order(self) -> List[Node]:
        """Orden topológico según needs/provides (error si hay ciclos o faltan entradas)."""
        if self._order is not None:
            return self._order
        producers = {k: n.name for n in self.nodes for k in n.provides}
        done: set = set()
        out: List[Node] = []
        pending = list(self.nodes)
        while pending:
            ready = [n for n in pending if all(k not in producers or producers[k] in done for k in n.needs)]
            if not ready:
                raise ValueError(f"ciclo en el grafo {self.name}: {[n.name for n in pending]}")
            for n in ready:
                out.append(n)
                done.add(n.name)
                pending.remove(n)
        self._order = out
        return out

    def run(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        for n in self.order():
            n.fn(ctx)
        return ctx

    def edges(self) -> List[Tuple[str, str, str]]:
        producers = {k: n.name for n in self.nodes for k in n.provides}
        return [(producers[k], n.name, k) for n in self.nodes for k in n.needs if k in producers]

    def mermaid(self) -> str:
        lines = [f"flowchart LR\n  subgraph {_mid(self.name)}[\"{self.name}\"]"]
        for n in self.nodes:
            lines.append(f'    {_mid(n.name)}["{n.name}"]')
        for a, b, k in self.edges():
            lines.append(f"    {_mid(a)} -- {k} --> {_mid(b)}")
        lines.append("  end")
        return "\n".join(lines)


def _mid(s: str) -> str:
    return "".join(ch if ch.isascii() and ch.isalnum() else "_" for ch in s)


# --------------------------------------------------------------------------- ejecución

MIN_ORDER = 6.0  # mínimo de orden habitual en exchanges (~5 USDT) con margen
SLIPPAGE = 0.0005  # 0,05 % por lado: deslizamiento conservador de una orden a mercado en monedas líquidas


class PaperExecutor:
    """Ejecuta en papel con **deslizamiento**: compra un poco más caro y vende un
    poco más barato que el precio de referencia, como pasa con órdenes reales a
    mercado. Mismo interfaz que exchange.CcxtExecutor."""
    name = "papel"
    real_money = False
    simulated = True

    def __init__(self, slippage: float = SLIPPAGE) -> None:
        self.slippage = slippage

    def buy(self, symbol: str, qty: float, price: float) -> Tuple[float, float]:
        return qty, price * (1 + self.slippage)

    def sell(self, symbol: str, qty: float, price: float, maker: bool = False) -> float:
        # una orden límite (maker) se ejecuta a su precio; una a mercado sufre deslizamiento
        return price if maker else price * (1 - self.slippage)

    def place_limit_buy(self, symbol: str, qty: float, price: float) -> Optional[str]:
        return None  # en papel la ejecución se decide con las velas siguientes

    def limit_status(self, symbol: str, oid: Optional[str]) -> Tuple[float, float, str]:
        return 0.0, 0.0, "open"

    def cancel_limit(self, symbol: str, oid: Optional[str]) -> None:
        pass

    def protect(self, symbol: str, qty: float, stop: float) -> None:
        pass


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
    exit_target: Optional[float] = None  # objetivo (en ATR) del perfil aprobado
    p_win: float = 0.0                   # probabilidad de acierto verificada (cota inferior)

    @property
    def approved(self) -> bool:
        return not self.vetoes


@dataclass
class StepReport:
    decisions: Dict[str, Decision] = field(default_factory=dict)
    opened: List[Position] = field(default_factory=list)
    closed: List[ClosedTrade] = field(default_factory=list)
    signals: int = 0
    seconds: float = 0.0
    event: Optional[str] = None
    notes: List[str] = field(default_factory=list)
    data_issues: Dict[str, List[str]] = field(default_factory=dict)  # símbolos omitidos por datos dudosos


def group_swarm(swarm: Optional[Sequence[Agent]] = None) -> Dict[str, List[Agent]]:
    groups: Dict[str, List[Agent]] = {}
    for a in (swarm if swarm is not None else agent_swarm()):
        if a.warmup <= WINDOW:
            groups.setdefault(a.team, []).append(a)
    return groups


class Engine:
    def __init__(self, cfg: Optional[Config] = None, state: Optional[dict] = None, cash: float = 10_000.0,
                 executor: Any = None, llm: Optional[LLMAnalystAgent] = None,
                 cache: Optional[Dict[tuple, dict]] = None, swarm: Optional[Sequence[Agent]] = None,
                 sentiment: Optional[Dict[str, int]] = None,
                 funding: Optional[Dict[str, List[Tuple[int, float]]]] = None) -> None:
        state = state or {}
        self.cfg = cfg or Config.from_dict(state.get("config"))
        groups = group_swarm(swarm)
        enabled = [t for t in groups if not self.cfg.teams or t in self.cfg.teams]
        if not enabled:
            raise ValueError("ningún equipo activo")
        tstate = state.get("teams", {})
        self._saved_teams = dict(tstate)
        self.teams = {n: Team(n, groups[n], tstate.get(n), eta=self.cfg.team_eta) for n in enabled}
        self.council = Coordinator.from_dict(state.get("council"), list(self.teams), eta=self.cfg.council_eta,
                                             alpha=0.03)
        self.council.eta = self.cfg.council_eta
        # las operaciones en la sombra pagan comisión + deslizamiento, igual que las reales
        taker_side, maker_side = self.cfg.taker_fee + SLIPPAGE, self.cfg.maker_fee
        limit = self.cfg.entry_mode == "limit"
        tmaker = limit and self.cfg.target_maker
        self.cal = Calibrator.from_dict(state.get("calibrator"), min_samples=self.cfg.min_samples,
                                        min_edge=self.cfg.min_edge, horizon=self.cfg.shadow_horizon,
                                        fee=taker_side, sample_gap=SHADOW_GAP,
                                        entry_cost=maker_side if limit else taker_side,
                                        target_cost=maker_side if tmaker else taker_side, stop_cost=taker_side,
                                        limit_offset=self.cfg.limit_offset_atr if limit else None,
                                        limit_wait=self.cfg.limit_wait)
        self.pf = Portfolio(cash=cash)
        self.risk = RiskManager(risk_per_trade=self.cfg.risk_per_trade, stop_atr=self.cfg.stop_atr,
                                target_atr=self.cfg.target_atr, max_positions=self.cfg.max_positions,
                                max_exposure=self.cfg.max_exposure, max_drawdown=self.cfg.max_drawdown,
                                exit_score=self.cfg.exit_score, peak_equity=cash,
                                max_daily_loss=self.cfg.max_daily_loss)
        self.executor = executor or PaperExecutor()
        self.llm = llm
        self.cache = cache
        self.sentiment = sentiment
        self.funding = funding
        self.track_stats = True  # el optimizador lo apaga: no necesita estadísticas por agente
        self.check_data = True   # comprobación de integridad de datos por vela (safety.check_window)
        self.warmup = min(WINDOW, max(a.warmup for t in self.teams.values() for a in t.agents) + 1)
        self._pending: Dict[str, tuple] = {}
        self._last_shadow: Dict[str, int] = {}
        self._step = 0
        self.total_signals = 0
        self.total_seconds = 0.0
        self.veto_counts: Dict[str, int] = {}
        self.llm_vetoes = 0
        self.symbol_graph = self._build_symbol_graph()
        self.portfolio_graph = self._build_portfolio_graph()

    # ---------------------------------------------------------------- nodos por símbolo
    def _build_symbol_graph(self) -> Graph:
        g = Graph("símbolo")
        cfg = self.cfg

        def learn(ctx: Dict[str, Any]) -> None:
            pend = self._pending.get(ctx["symbol"])
            if pend:
                obs, team_sigs, regime, prev_close, vol = pend
                ret = math.log(ctx["candle"].close / prev_close)
                for name, o in obs.items():
                    self.teams[name].coord.learn_arrays(o[0], o[1], regime, ret, vol, self.track_stats, o[2])
                self.council.learn(team_sigs, regime, ret, vol)
            ctx["learned"] = True

        def resolve_shadows(ctx: Dict[str, Any]) -> None:
            c = ctx["candle"]
            self.cal.update(ctx["symbol"], c.high, c.low, c.close)
            ctx["shadows_resolved"] = True

        def observe(ctx: Dict[str, Any]) -> None:
            sym, window = ctx["symbol"], ctx["window"]
            key = (sym, window[-1].time)
            entry = self.cache.get(key) if self.cache is not None else None
            f = None
            if entry is None or any(t not in entry["obs"] for t in self.teams):
                f = Features(window, sym)
                f.ctx = ctx["mctx"]
                entry = entry or {"regime": detect_regime(f), "atr": f.atr(14)[-1],
                                  "long_ema": f.ema(200)[-1] or f.ema(100)[-1], "vol": f.vol(), "obs": {}}
                sigs: Dict[str, List[Signal]] = {}
                for name, team in self.teams.items():
                    if name not in entry["obs"]:
                        scores, confs, s = team.observe(f)
                        entry["obs"][name] = (scores, confs, tuple(a * b for a, b in zip(scores, confs)))
                        sigs[name] = s
                ctx["agent_signals"] = sigs
                if self.cache is not None:
                    self.cache[key] = entry
            ctx["features"] = f
            ctx["market"] = entry
            ctx["report"].signals += sum(len(entry["obs"][t][0]) + 1 for t in self.teams)

        g.add(Node("aprender", ("candle",), ("learned",), learn, "Hedge: premia a quien acertó la vela anterior"))
        g.add(Node("resolver_sombras", ("candle",), ("shadows_resolved",), resolve_shadows,
                   "cierra operaciones en la sombra"))
        g.add(Node("observar", ("window",), ("market",), observe, "94 agentes analizan (con caché)"))

        for name in self.teams:
            def team_node(ctx: Dict[str, Any], name: str = name) -> None:
                m = ctx["market"]
                o = m["obs"][name]
                ctx[f"team:{name}"] = self.teams[name].verdict(o[0], o[1], m["regime"], o[2])
            g.add(Node(f"equipo:{name}", ("market", "learned"), (f"team:{name}",), team_node))

        def council(ctx: Dict[str, Any]) -> None:
            m = ctx["market"]
            team_sigs = [ctx[f"team:{n}"] for n in self.teams]
            score, agree = self.council.combine(team_sigs, m["regime"])
            # cada modo de entrada tiene su propia estadística (costes y ejecución distintos)
            mode = ("L|" if cfg.target_maker else "LT|") if cfg.entry_mode == "limit" else ""
            d = Decision(ctx["symbol"], score, agree, m["regime"], mode + bucket(m["regime"], abs(score), agree),
                         teams=team_sigs)
            if score < cfg.enter:
                d.vetoes.append("sin consenso alcista")
            ctx["decision"] = d

        def skeptic(ctx: Dict[str, Any]) -> None:
            d, m = ctx["decision"], ctx["market"]
            if d.score >= cfg.enter:
                if d.agreement < cfg.min_agreement:
                    self._veto(d, f"desacuerdo entre equipos ({d.agreement:.0%})")
                if cfg.block_volatile and d.regime == "volátil":
                    self._veto(d, "régimen volátil")
                if cfg.trend_filter and m["long_ema"] is not None and ctx["candle"].close < m["long_ema"]:
                    self._veto(d, "contra la tendencia mayor (EMA200)")
                mc = ctx["mctx"]
                gap = mc.get("btc_gap")
                if cfg.riskoff and gap is not None and gap < 0 and mc.get("breadth", 1) < cfg.riskoff_breadth:
                    self._veto(d, f"mercado en fase bajista (amplitud {mc['breadth']:.0%})")
            ctx["skeptic"] = True

        def edge_gate(ctx: Dict[str, Any]) -> None:
            d = ctx["decision"]
            if d.score >= cfg.enter:
                ok, note, target, p_lb = self.cal.choose(d.key, cfg.exit_profiles, cfg.min_win_prob, cfg.prob_z)
                d.edge_note, d.exit_target, d.p_win = note, target, p_lb
                if not ok:
                    self._veto(d, note)
            ctx["gate"] = True

        def shadow(ctx: Dict[str, Any]) -> None:
            d, m, c, sym = ctx["decision"], ctx["market"], ctx["candle"], ctx["symbol"]
            if m["atr"] and d.score >= cfg.enter and self._step - self._last_shadow.get(sym, -SHADOW_GAP) >= SHADOW_GAP:
                # la misma señal se prueba con todos los perfiles de salida a la vez
                self.cal.record(sym, d.key, c.close, c.close - cfg.stop_atr * m["atr"], atr=m["atr"],
                                profiles=cfg.exit_profiles)
                self._last_shadow[sym] = self._step
            ctx["shadow"] = True

        def position(ctx: Dict[str, Any]) -> None:
            d, m, c, sym = ctx["decision"], ctx["market"], ctx["candle"], ctx["symbol"]
            p = self.pf.positions.get(sym)
            old_stop = p.stop if p else None
            ex = self.risk.check_exit(self.pf, sym, c.high, c.low, c.close, m["atr"], d.score)
            if ex:
                maker = cfg.entry_mode == "limit" and cfg.target_maker and ex[1] == "objetivo alcanzado"
                self.close_position(sym, ex[0], c.time, ex[1], ctx["report"], maker=maker)
            elif p and p.stop != old_stop:
                self.executor.protect(sym, p.qty, p.stop)
            ctx["exit"] = True

        def candidate(ctx: Dict[str, Any]) -> None:
            d, m, sym = ctx["decision"], ctx["market"], ctx["symbol"]
            if (ctx["trading"] and d.approved and m["atr"] and sym not in self.pf.positions
                    and sym not in self.pf.pending):
                # prioridad: la probabilidad verificada más alta
                ctx["candidates"].append((d.p_win, sym, d, m["atr"], ctx))

        def remember(ctx: Dict[str, Any]) -> None:
            m = ctx["market"]
            obs = {n: m["obs"][n] for n in self.teams}
            self._pending[ctx["symbol"]] = (obs, ctx["decision"].teams, m["regime"], ctx["candle"].close, m["vol"])

        g.add(Node("consejo", tuple(f"team:{n}" for n in self.teams), ("decision",), council,
                   "confronta a los equipos con pesos aprendidos"))
        g.add(Node("escéptico", ("decision", "market"), ("skeptic",), skeptic,
                   "veto: desacuerdo, volatilidad, EMA200, mercado bajista"))
        g.add(Node("filtro_ventaja", ("skeptic", "shadows_resolved"), ("gate",), edge_gate,
                   "solo señales con ventaja demostrada"))
        g.add(Node("registrar_sombra", ("decision", "shadows_resolved"), ("shadow",), shadow,
                   "prueba cada señal sin dinero"))
        def limit_orders(ctx: Dict[str, Any]) -> None:
            """Órdenes límite de entrada colocadas en velas anteriores: ¿se ejecutaron en esta?"""
            sym, c = ctx["symbol"], ctx["candle"]
            o = self.pf.pending.get(sym)
            if o:
                simulated = getattr(self.executor, "simulated", False)
                if simulated:  # papel: ejecutada solo si el precio ATRAVESÓ la orden
                    done = c.low < o["limit"]
                    qty, fill = (o["qty"], o["limit"]) if done else (0.0, 0.0)
                else:  # exchange: se pregunta el estado real de la orden
                    qty, fill, status = self.executor.limit_status(sym, o["oid"])
                    done = status == "closed"
                    if not done and qty > 0 and o["wait"] <= 1:  # parcial al vencer: cancelar el resto
                        self.executor.cancel_limit(sym, o["oid"])
                        done = True
                if done:
                    del self.pf.pending[sym]
                    qty = min(qty, self.pf.cash / (fill * (1 + cfg.maker_fee))) if fill > 0 else 0.0
                    if qty * fill >= MIN_ORDER:
                        stop = fill - cfg.stop_atr * o["atr"]
                        pos = Position(sym, qty, fill, stop, fill + o["target"] * o["atr"], fill - stop, c.time, fill,
                                       o["reason"], risk_frac=qty * (fill - stop) / max(o["equity"], 1e-9),
                                       p_win=o["p_win"], expires=cfg.shadow_horizon, strict=True)
                        self.pf.open(pos, fee=cfg.maker_fee)
                        self.executor.protect(sym, qty, stop)
                        ctx["report"].opened.append(pos)
                        if simulated and c.low <= stop:  # en la misma vela pudo tocar el stop: pesimista
                            self.close_position(sym, stop, c.time, "stop", ctx["report"])
                else:
                    o["wait"] -= 1
                    if o["wait"] <= 0:
                        del self.pf.pending[sym]
                        if not simulated:
                            self.executor.cancel_limit(sym, o["oid"])
                        ctx["report"].notes.append(f"{sym}: orden límite no ejecutada")
            ctx["orders"] = True

        g.add(Node("órdenes_límite", ("candle",), ("orders",), limit_orders, "¿se ejecutó la orden límite?"))
        g.add(Node("gestionar_posición", ("decision", "orders"), ("exit",), position, "stop, objetivo, horizonte"))
        g.add(Node("candidata", ("gate", "exit"), ("candidate",), candidate, "propone la compra"))
        g.add(Node("recordar", ("decision", "shadow"), ("pending",), remember, "guarda para aprender luego"))
        return g

    # ---------------------------------------------------------------- nodos de cartera
    def _build_portfolio_graph(self) -> Graph:
        g = Graph("cartera")

        def guard(ctx: Dict[str, Any]) -> None:
            eq = self.pf.equity(ctx["prices"])
            ctx["equity"] = eq
            ev = self.risk.tick(eq, ctx["time"])
            if ev == "DAILY":
                ctx["report"].notes.append(f"límite de pérdida diaria alcanzado (capital {eq:,.2f})")
                ctx["report"].event = ev
            if ev == "HALT":
                for s in list(self.pf.positions):
                    self.close_position(s, ctx["prices"][s], ctx["time"], "interruptor de emergencia", ctx["report"])
                ctx["report"].event = ev

        def allocate(ctx: Dict[str, Any]) -> None:
            rep = ctx["report"]
            for _, sym, d, atr, sctx in sorted(ctx["candidates"], key=lambda x: -x[0]):
                if self.risk.can_open(self.pf):
                    break
                price = ctx["prices"][sym]
                # presupuesto de riesgo primero: si no cabe ni una orden mínima, no se consulta a la IA
                heat = sum(q.qty * max(0.0, q.entry - q.stop) for q in self.pf.positions.values())
                room = self.cfg.max_heat * ctx["equity"] - heat
                qty = min(self.risk.size(self.pf, ctx["equity"], price, atr),
                          max(0.0, room) / (self.risk.stop_atr * atr))
                if qty * price < MIN_ORDER:
                    if room < MIN_ORDER * self.risk.stop_atr * atr / price:  # el límite total ya no deja abrir nada
                        rep.notes.append("límite de riesgo total alcanzado")
                        break
                    continue
                if self.llm is not None:
                    self.llm.peer_signals = d.teams
                    s = self.llm.analyze(sctx["features"] or Features(sctx["window"], sym))
                    if s.value < 0:
                        self.llm_vetoes += 1
                        d.vetoes.append(f"IA en contra: {s.reason}")
                        continue
                if self.cfg.entry_mode == "limit":
                    lim = price - self.cfg.limit_offset_atr * atr
                    oid = self.executor.place_limit_buy(sym, qty * price / lim, lim)
                    if oid is False:  # el exchange la rechazó (mínimos, saldo...)
                        continue
                    self.pf.pending[sym] = {"limit": lim, "qty": qty * price / lim, "atr": atr, "oid": oid,
                                            "target": d.exit_target or self.cfg.target_atr, "p_win": d.p_win,
                                            "wait": self.cfg.limit_wait, "equity": ctx["equity"],
                                            "reason": f"límite {lim:.4f}; consejo {d.score:+.2f}, {d.edge_note}"}
                    rep.notes.append(f"{sym}: orden límite de compra a {lim:.4f}")
                    continue
                qty, fill = self.executor.buy(sym, qty, price)
                # el deslizamiento encarece la compra: nunca gastar más caja de la que hay
                qty = min(qty, self.pf.cash / (fill * (1 + self.pf.fee)))
                if qty <= 0 or qty * fill < MIN_ORDER:
                    continue
                # salida EXACTAMENTE igual a la medida en la sombra (stop, objetivo del perfil y
                # horizonte): si no, la probabilidad verificada no valdría para esta operación
                stop = fill - self.cfg.stop_atr * atr
                target = fill + (d.exit_target or self.cfg.target_atr) * atr
                pos = Position(sym, qty, fill, stop, target, fill - stop, ctx["time"], fill,
                               f"consejo {d.score:+.2f}, acuerdo {d.agreement:.0%}, {d.edge_note}",
                               risk_frac=qty * (fill - stop) / ctx["equity"] if ctx["equity"] > 0 else 0.0,
                               p_win=d.p_win, expires=self.cfg.shadow_horizon, strict=True)
                self.pf.open(pos, fee=self.cfg.taker_fee)
                self.executor.protect(sym, qty, stop)
                rep.opened.append(pos)

        g.add(Node("guardián", ("prices",), ("equity",), guard, "drawdown máximo y pausas"))
        g.add(Node("asignar", ("equity", "candidates"), ("opened",), allocate,
                   "revisión IA, tamaño por riesgo, orden"))
        return g

    # ---------------------------------------------------------------- utilidades
    def _veto(self, d: Decision, why: str) -> None:
        d.vetoes.append(why)
        k = why.split(" (")[0]
        self.veto_counts[k] = self.veto_counts.get(k, 0) + 1

    def close_position(self, sym: str, price: float, t: int, why: str, rep: StepReport, maker: bool = False) -> None:
        p = self.pf.positions[sym]
        fill = self.executor.sell(sym, p.qty, price, maker=maker) if maker else self.executor.sell(sym, p.qty, price)
        tr = self.pf.close(sym, fill, t, why, fee=self.cfg.maker_fee if maker else self.cfg.taker_fee)
        self.risk.on_closed(tr)
        rep.closed.append(tr)

    def step(self, windows: Dict[str, Sequence[Candle]], trading: bool = True) -> StepReport:
        rep = StepReport()
        t0 = time.perf_counter()
        candidates: List[tuple] = []
        prices: Dict[str, float] = {}
        now = 0
        t_key = ("ctx", next(iter(windows.values()))[-1].time)
        mctx = self.cache.get(t_key) if self.cache is not None else None
        if mctx is None:
            mctx = market_context(windows, self.sentiment, funding=self.funding)
            if self.cache is not None:
                self.cache[t_key] = mctx
        if hasattr(self.executor, "step_time"):  # identificadores de orden deterministas por vela
            self.executor.step_time = next(iter(windows.values()))[-1].time
        for sym, window in windows.items():
            c = window[-1]
            now, prices[sym] = c.time, c.close
            if self.check_data:
                problems = check_window(window)
                if problems:
                    # datos dudosos: ni se aprende, ni se decide, ni se gestiona con ellos en esta vela
                    # (la posición, si la hay, sigue protegida por su stop en el exchange)
                    rep.data_issues[sym] = problems
                    rep.notes.append(f"{sym}: datos dudosos, se omite esta vela ({problems[0]})")
                    self._pending.pop(sym, None)
                    continue
            ctx = {"symbol": sym, "window": window, "candle": c, "trading": trading,
                   "candidates": candidates, "report": rep, "mctx": mctx[sym]}
            self.symbol_graph.run(ctx)
            rep.decisions[sym] = ctx["decision"]
        rep.seconds = time.perf_counter() - t0
        self.total_signals += rep.signals
        self.total_seconds += rep.seconds
        self.portfolio_graph.run({"prices": prices, "time": now, "candidates": candidates, "report": rep})
        self._step += 1
        return rep

    @property
    def signals_per_second(self) -> float:
        return self.total_signals / self.total_seconds if self.total_seconds else 0.0

    def state(self) -> dict:
        teams = dict(self._saved_teams)
        teams.update({n: t.coord.to_dict() for n, t in self.teams.items()})
        return {"config": self.cfg.to_dict(), "teams": teams, "council": self.council.to_dict(),
                "calibrator": self.cal.to_dict()}


# --------------------------------------------------------------------------- backtest y métricas

def metrics(equity: Sequence[float], periods_per_year: int) -> Dict[str, float]:
    rets = [equity[i] / equity[i - 1] - 1 for i in range(1, len(equity)) if equity[i - 1] > 0]
    mean = sum(rets) / len(rets) if rets else 0.0
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / len(rets)) if rets else 0.0
    peak, mdd = equity[0], 0.0
    for e in equity:
        peak = max(peak, e)
        mdd = max(mdd, 1 - e / peak)
    total = equity[-1] / equity[0] - 1
    years = max(len(equity) - 1, 1) / periods_per_year
    weeks = years * 52
    return {"return": total, "annual": (1 + total) ** (1 / years) - 1 if total > -1 else -1.0,
            "weekly": (1 + total) ** (1 / weeks) - 1 if total > -1 and weeks > 0 else -1.0,
            "max_drawdown": mdd, "sharpe": mean / sd * math.sqrt(periods_per_year) if sd else 0.0}


def trade_stats(trades: Sequence[ClosedTrade]) -> Dict[str, float]:
    wins = [t.pnl for t in trades if t.pnl > 0]
    losses = [-t.pnl for t in trades if t.pnl <= 0]
    return {"n": len(trades), "win_rate": len(wins) / len(trades) if trades else 0.0,
            "profit_factor": sum(wins) / sum(losses) if losses else (math.inf if wins else 0.0),
            "avg_r": sum(t.r for t in trades) / len(trades) if trades else 0.0}


def run_backtest(engine: Engine, data: Dict[str, List[Candle]], start: int, stop: int, trade_from: int,
                 on_step: Optional[Callable[[int, StepReport], None]] = None) -> dict:
    """Recorre las velas [start, stop). Aprende siempre; opera solo desde ``trade_from``.
    Devuelve la curva de capital del tramo operado."""
    equity: List[float] = []
    for i in range(start, stop):
        windows = {s: cs[max(0, i - WINDOW + 1): i + 1] for s, cs in data.items()}
        trading = i >= trade_from
        rep = engine.step(windows, trading=trading)
        if trading:
            equity.append(engine.pf.equity({s: data[s][i].close for s in data}))
        if on_step:
            on_step(i, rep)
    first = {s: data[s][trade_from].close for s in data}
    last = {s: data[s][stop - 1].close for s in data}
    bh = sum(last[s] / first[s] - 1 for s in data) / len(data)
    return {"equity": [equity[0] if equity else engine.pf.cash] + equity, "buy_hold": bh}


def stress_test(r_multiples: Sequence[float], risk: float, n_paths: int = 2000, horizon: Optional[int] = None,
                seed: int = 0) -> Dict[str, float]:
    """Prueba de estrés de Monte Carlo: baraja (con reemplazo) las operaciones
    reales, en múltiplos de R, en miles de órdenes distintos y mide la caída
    máxima de cada camino. Responde: «con esta forma de operar, ¿cuánto podría
    caer en una mala racha?», no solo «cuánto cayó en este orden concreto»."""
    import random as _r
    rs = list(r_multiples)
    if len(rs) < 5:
        return {"paths": 0}
    rng = _r.Random(seed)
    h = horizon or len(rs)
    dds, finals = [], []
    for _ in range(n_paths):
        eq = peak = 1.0
        mdd = 0.0
        for _ in range(h):
            eq *= 1 + risk * rng.choice(rs)
            if eq > peak:
                peak = eq
            elif 1 - eq / peak > mdd:
                mdd = 1 - eq / peak
        dds.append(mdd)
        finals.append(eq - 1)
    dds.sort()
    finals.sort()
    return {"paths": n_paths, "trades": h, "dd_p50": dds[n_paths // 2], "dd_p95": dds[int(n_paths * 0.95)],
            "ret_p5": finals[int(n_paths * 0.05)], "ret_p50": finals[n_paths // 2],
            "p_loss": sum(1 for x in finals if x < 0) / n_paths}
