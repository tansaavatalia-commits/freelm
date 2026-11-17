# Bot multiagente de señales cripto que aprende

> ⚠️ **Solo paper trading.** El bot no envía órdenes reales a ningún exchange.
> Es material educativo y no es asesoramiento financiero. Que un backtest
> salga positivo no garantiza nada en el mercado real.

Varios **equipos de agentes** analizan el mercado en paralelo. Cada equipo usa
una familia de estrategias de las que aparecen en los proyectos de trading
open source más conocidos de GitHub (freqtrade, jesse, backtrader,
hummingbot). Un **coordinador** aprende con la experiencia en qué agente
fiarse en cada tipo de mercado.

```
              velas OHLCV (Binance público / CSV / sintético)
                               │
   ┌───────────────┬───────────┼────────────┬──────────────────┐
   │  TENDENCIA    │ REVERSIÓN │   FLUJO    │        IA        │
   │  ema_cross    │ rsi       │ obv_flow   │ llm_analyst      │
   │  macd         │ bollinger │ breakout   │ (freelm, gratis, │
   │               │           │            │  oye a los demás)│
   └───────┬───────┴─────┬─────┴──────┬─────┴────────┬─────────┘
           └─────────────┴─────┬──────┴──────────────┘
                     COORDINADOR (aprende)
          pesos Hedge por régimen: tendencia / lateral / volátil
                               │ decisión ∈ [-1, 1]
                       GESTOR DE RIESGO
     tamaño por riesgo · stop 2×ATR dinámico · interruptor por drawdown
                               │
                     BRÓKER DE PAPEL (comisión 0,1%)
```

## Cómo aprende

En cada vela, cuando ya se conoce el retorno real de la vela anterior, cada
agente recibe una recompensa: acertar la dirección con convicción suma y
fallar con convicción resta. Su peso se multiplica por `exp(eta·recompensa)`.
Esto es el algoritmo *Hedge* de pesos multiplicativos. Además se aplica
*fixed share*: una pequeña mezcla uniforme deja que un agente castigado
vuelva a ganar peso cuando el mercado cambia.

Los pesos se llevan por separado para cada régimen de mercado (detectado con
el *efficiency ratio* de Kaufman). Así el bot descubre por sí mismo, por
ejemplo, que en mercado lateral funciona la reversión y en tendencia, los
cruces de medias. La memoria se guarda en `~/.cache/freelm-trading/SYMBOL.json`
y se acumula entre ejecuciones.

## Uso

```bash
pip install -e .            # desde la raíz del repo (necesita freelm + httpx)

# 1) Sin red ni claves: datos sintéticos
python examples/trading_agents/bot.py backtest -v

# 2) Datos reales de Binance (API pública, sin clave)
python examples/trading_agents/bot.py backtest --source binance --symbol ETHUSDT --interval 4h

# 3) Con el analista IA: usa tus claves gratuitas (GEMINI_API_KEY, GROQ_API_KEY, ...)
freelm doctor               # comprueba qué claves funcionan
python examples/trading_agents/bot.py backtest --source binance --llm --llm-every 24

# 4) En vivo, en papel; sigue aprendiendo vela a vela
python examples/trading_agents/bot.py live --symbol BTCUSDT --interval 1h --llm
python examples/trading_agents/bot.py live --once     # una vela y salir (para cron)

# 5) Ver lo aprendido
python examples/trading_agents/bot.py status --symbol BTCUSDT
```

## Añadir tu propio agente

```python
from agents import Agent, Signal

class MiAgente(Agent):
    name, team, warmup = "mi_agente", "custom", 30
    def analyze(self, candles):
        sube = candles[-1].close > candles[-10].close
        return Signal(self.name, 1 if sube else -1, 0.5, "momentum 10 velas")
```

Añádelo a `default_agents()` en `agents.py`. Empieza con el mismo peso que los
demás y el coordinador decidirá con datos si merece confianza.

## Límites

- Es solo largo (spot). No hace cortos ni usa apalancamiento.
- Con datos sintéticos, que son un paseo aleatorio, no hay ventaja que
  aprender. Sirven para comprobar la mecánica, no para medir rentabilidad.
- El analista IA consume cuota de los proveedores gratuitos. En backtest,
  `--llm-every` limita cuántas consultas hace.
