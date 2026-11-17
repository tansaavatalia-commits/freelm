# Bot multiagente de señales cripto que aprende

> ⚠️ **Solo paper trading.** El bot no envía órdenes reales a ningún exchange.
> Es material educativo y no es asesoramiento financiero. **Ningún sistema
> puede garantizar beneficios ni evitar todas las pérdidas.** El objetivo del
> 18 % es una meta que el bot *mide*, no una promesa.

## Arquitectura

```
        8 símbolos (BTC, ETH, SOL, BNB, XRP, ADA, AVAX, LINK; configurable)
                                 │  velas OHLCV
   ┌────────────┬────────────┬───┴────────┬─────────────┬──────────────┐
   │ TENDENCIA  │ REVERSIÓN  │   FLUJO    │ VOLATILIDAD │ MULTI-MARCO  │   94 agentes por símbolo
   │ 12 EMA     │ 9 RSI      │ 4 OBV      │ 6 squeeze   │ 10 tendencia │   ≈ 800 señales por vela
   │ 6 MACD     │ 9 Bollinger│ 6 Donchian │ 9 Keltner   │    en 2x-24x │   > 30.000 señales/segundo
   │ 9 pendiente│ 5 estocást.│ 6 ROC      │             │              │
   │            │ 4 VWAP     │            │             │              │
   └─────┬──────┴─────┬──────┴─────┬──────┴──────┬──────┴──────┬───────┘
         │ nivel 1: cada equipo vota con pesos aprendidos (por régimen)
         └────────────┴────────────┼─────────────┴─────────────┘
                     CONSEJO: nivel 2, los equipos se confrontan
                                   │
                EQUIPO ESCÉPTICO (veto). Rechaza la operación si:
                  · los equipos no están de acuerdo (< 60 %)
                  · el mercado está en régimen volátil
                  · implica comprar contra la tendencia mayor (EMA 200)
                  · el calibrador no ha demostrado ventaja neta en ese tipo de señal
                  · la IA (opcional, freelm) opina en contra
                                   │
                GESTOR DE RIESGO
                  · 1 % de riesgo por operación, beneficio/riesgo 2:1
                  · stop a break-even tras +1R, después stop dinámico
                  · máximo 4 posiciones y 30 % del capital en cada una
                  · pausa tras 3 pérdidas seguidas; interruptor con drawdown del 12 %
                                   │
                        CARTERA DE PAPEL (comisión 0,1 %)
```

## Cómo aprende (tres niveles)

1. **Agentes dentro de cada equipo.** Se usa el algoritmo *Hedge* de pesos
   multiplicativos con *fixed share*. Tras cada vela, el agente que acertó
   con convicción gana peso y el que falló lo pierde. Los pesos son
   distintos para cada régimen (tendencia, lateral, volátil).
2. **Equipos dentro del consejo.** Mismo algoritmo, un nivel más arriba.
3. **Calibrador: el filtro de señales sin sentido.** Cada señal candidata se
   opera *en la sombra* con el mismo stop, el mismo objetivo y las mismas
   comisiones que una real. Su resultado se apunta en múltiplos de riesgo (R)
   por tipo de señal (régimen × fuerza × acuerdo). Ese tipo solo se opera de
   verdad cuando su esperanza *conservadora* (media menos un error estándar)
   supera +0,15 R con al menos 40 casos.

La memoria (los tres niveles) se guarda en `~/.cache/freelm-trading/` y se
acumula de una ejecución a otra.

## Validación honesta (walk-forward)

`backtest` divide los datos en dos fases:

- **Fase 1, aprendizaje (60 %).** El bot aprende sin operar.
- **Fase 2, validación (40 %).** El bot opera en papel con datos que nunca ha
  visto.

Solo se informa del resultado de la fase 2: rendimiento, rendimiento
anualizado, drawdown, Sharpe, acierto, factor de beneficio y si se alcanza el
objetivo del 18 %. Puedes cambiar la meta con `--target` y `--target-basis anual|periodo`.

## Uso

```bash
pip install -e .                                          # desde la raíz del repo

python examples/trading_agents/bot.py bench               # señales por segundo (mínimo 500)
python examples/trading_agents/bot.py backtest -v         # sintético, sin red
python examples/trading_agents/bot.py backtest --source binance --limit 5000   # datos reales
python examples/trading_agents/bot.py backtest --source binance --llm          # con revisión IA

freelm doctor                                             # qué claves gratis funcionan
python examples/trading_agents/bot.py live --llm          # tiempo real, en papel
python examples/trading_agents/bot.py live --once         # una vela y salir (para cron)
python examples/trading_agents/bot.py status --source binance
```

Opciones útiles: `--symbols BTCUSDT,ETHUSDT`, `--interval 4h`, `--risk 0.005`,
`--max-positions 2`, `--min-agreement 0.7`, `--min-edge 0.25`. Los valores más
estrictos dan menos operaciones y más selectivas.

## Resultados de referencia (datos sintéticos, no reales)

| Datos | Validación | Cesta comprar y mantener | Drawdown máx. | Operaciones | Acierto |
|---|---|---|---|---|---|
| Sintéticos con inercia (`--structure 1`) | +32,2 % | +32,6 % | 5,6 % | 139 | 63 % |
| Sintéticos, azar + derivas (`--structure 0`) | +12,8 % | +29,0 % | 8,9 % | 200 | 51 % |

En ambos casos el riesgo es mucho menor que mantener la cesta. **No se ha
probado aún con datos reales.** El mercado real es más difícil y cambia, así
que valida con `--source binance` antes de sacar conclusiones.

## Añadir tu propio agente

```python
from agents import Agent, Signal

class MiAgente(Agent):
    team = "flujo"
    def __init__(self):
        self.name, self.warmup = "mi_agente", 30
    def analyze(self, f):                       # f: Features (indicadores con caché)
        sube = f.price > f.closes[-10]
        return Signal(self.name, 1 if sube else -1, 0.5, "momentum 10 velas")
```

Añádelo en `agent_swarm()` dentro de `agents.py`. El equipo decide con datos
si merece confianza.
