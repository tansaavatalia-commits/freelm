# Investigación de sistemas de trading automatizado y diseño del bot propio

**Fecha de consulta de todas las fuentes:** 18 de noviembre de 2026.
**Alcance:** 10 plataformas comerciales, 6 frameworks open source, plataformas de
verificación (Myfxbook, Darwinex), literatura académica y regulación de la UE, más
los datos reales propios de este proyecto (workflow `trading-research`, Binance,
8 monedas).
**Archivos de datos:** [`bots_investigados.csv`](bots_investigados.csv) ·
[`estrategias.csv`](estrategias.csv).

> **Conclusión principal, en una frase.** No he encontrado **ningún** sistema,
> plataforma ni estrategia con un historial **real, verificado de forma
> independiente y de al menos 180 días** (categoría A) que demuestre 3.000 € netos
> al mes. Los datos públicos más sólidos describen rentabilidades del orden del
> **1 % mensual bruto** en el mejor caso estructural. Eso exige **unos 300.000 € de
> capital** para llegar a 3.000 € netos al mes, no 100 €.

---

## 0. Cómo se clasifica la evidencia

| Categoría | Qué es | ¿Demuestra rentabilidad real? |
|---|---|---|
| **A** | Operaciones reales con evidencia independiente sólida | Sí |
| **B** | Historial conectado a un tercero, sin prueba suficiente del capital real | Parcialmente |
| **C** | Backtesting histórico (incluidos los papers académicos) | **No** |
| **D** | Simulación o paper trading | **No** |
| **E** | Declaraciones comerciales o testimonios | **No** |

Límites de esta investigación:
- Varias cifras proceden de resúmenes y abstracts, no del texto completo; se indica en cada caso.
- No he podido acceder a datos de cuentas privadas de los proveedores.
- Ausencia de evidencia no es evidencia de pérdidas: solo significa que no se puede afirmar rentabilidad.

---

## 1. Informe de investigación (resumen ejecutivo)

1. **Plataformas comerciales (10): ninguna publica rentabilidad real auditada.**
   Todo lo encontrado es categoría **E** (marketing, afiliados, reseñas). Los
   «track records verificados» de marketplaces como Cryptohopper los audita la
   propia plataforma, no un tercero
   ([Gainium](https://gainium.io/review/cryptohopper)).
2. **Seguridad: el riesgo más documentado de las plataformas no es perder en el
   mercado, sino la custodia de tus claves.** En diciembre de 2022 se filtraron
   unas **100.000 claves API de 3Commas**. Las pérdidas de usuarios se estiman entre
   **14,8 y 23,5 M$**; la empresa negó la filtración y luego la admitió, y el FBI
   investigó
   ([Cointelegraph](https://cointelegraph.com/news/3commas-ceo-confirms-api-key-leak-following-warning-from-cz),
   [Decrypt](https://decrypt.co/118094/after-repeated-denials-3commas-admits-it-was-source-for-earlier-hacks/),
   [Halborn](https://www.halborn.com/blog/post/explained-the-3commas-breach-december-2022),
   [ForkLog/HAPI](https://forklog.com/en/news/api-key-leaks-and-exchange-inaction-a-hapi-analysis-of-the-3commas-incident)).
   **Un bot autoalojado, como este, elimina ese riesgo de terceros.**
3. **Frameworks open source (6): son herramientas, no estrategias.** Freqtrade,
   Hummingbot, Jesse, LEAN, Backtrader y CCXT no publican rentabilidades: el
   resultado depende de lo que programes con ellos. Su valor es la transparencia y
   el control.
4. **Plataformas de verificación.**
   - **Myfxbook** solo verifica que el historial coincide con el del bróker. No
     verifica el riesgo, y hay casos de cuentas demo presentadas como reales
     ([Myfxbook](https://www.myfxbook.com/help/verification),
     [BabyPips](https://forums.babypips.com/t/a-guide-to-using-and-recognising-myfxbook-accounts/52656)).
   - **Darwinex** compara cada estrategia con 10.000 estrategias aleatorias del
     mismo riesgo ([Darwinex](https://help.darwinex.com/what-are-investable-attributes)).
     Es lo más cercano a la categoría A que existe, pero es de forex/CFD, no de
     cripto spot. No encontré estadísticas públicas de cuántas estrategias sobreviven.
5. **La base estadística del trading minorista es desfavorable.**
   - Entre el **74 % y el 89 %** de las cuentas minoristas de CFD pierden dinero
     (datos de las autoridades nacionales recogidos por
     [ESMA](https://www.esma.europa.eu/sites/default/files/library/esma35-43-1135_notice_of_pi_decisions_on_cfds_and_binary_options.pdf)).
   - **Más del 80 % de los *day traders*** pierden dinero en un semestre típico, y
     menos del 1 % gana de forma persistente (Barber, Lee, Liu y Odean, Taiwán,
     [working paper](https://faculty.haas.berkeley.edu/odean/papers/day%20traders/Day%20Trading%20Skill%20110523.pdf)).
6. **El riesgo número uno de un bot propio es el sobreajuste.** Cuantas más
   configuraciones se prueban, mayor es la probabilidad de que el backtest esté
   sobreajustado, y fuera de muestra puede dar **rentabilidad negativa**, no cero
   (Bailey, Borwein, López de Prado y Zhu,
   [Notices of the AMS 2014](https://scholarworks.wmich.edu/math_pubs/40/),
   [J. Computational Finance](https://papers.ssrn.com/abstract=2326253)).
7. **Datos reales propios** (Binance, 8 monedas, ~200 días en 1 h, ~52 días en 5 min, con comisiones y deslizamiento):
   - con la regla del 77 % verificado, **ninguna señal la cumplió** y el bot no operó;
   - el mercado cayó entre un 17 % y un 27 % en el mismo periodo;
   - sin esa regla, el resultado fue entre −1,7 % y +2,4 %;
   - categoría **C/D**: no demuestra nada todavía.

---

## 2. Base de datos de los bots investigados

Completa en [`bots_investigados.csv`](bots_investigados.csv). Resumen:

| Plataforma | Tipo | Código | Evidencia real | Categoría | Hecho relevante |
|---|---|---|---|---|---|
| 3Commas | SaaS | Cerrado | NO VERIFICADO | E | Filtración de ~100.000 claves API (2022) |
| Cryptohopper | SaaS + marketplace | Cerrado | NO VERIFICADO | E | «Verificación» interna, no de un tercero |
| Pionex | Exchange con bots | Cerrado | NO VERIFICADO | E | Solo material propio; custodia el exchange |
| Bitsgap | SaaS | Cerrado | NO VERIFICADO | E | — |
| HaasOnline | Scriptable | Cerrado | NO VERIFICADO | E | — |
| Coinrule | SaaS sin código | Cerrado | NO VERIFICADO | E | — |
| TradeSanta | SaaS plantillas | Cerrado | NO VERIFICADO | E | — |
| Gunbot | Licencia, autoalojado | Cerrado | NO VERIFICADO | E | Reportes de fallos de ejecución |
| WunderTrading | Copy trading | Cerrado | NO VERIFICADO | E | Reseñas mixtas |
| Altrady | SaaS | Cerrado | NO VERIFICADO | E | — |
| Hummingbot | Framework | Apache-2.0 | No aplica | — | Selección adversa documentada |
| Freqtrade | Framework | GPL-3.0 | No aplica | — | ~57.000 ⭐ |
| Jesse | Framework | MIT | No aplica | — | ~8.800 ⭐ |
| QuantConnect LEAN | Motor | Apache-2.0 | No aplica | — | Institucional |
| Backtrader | Librería | GPL-3.0 | No aplica | — | Poco mantenimiento |
| CCXT | Conectores | MIT | No aplica | — | ~44.900 ⭐, la usa este bot |

Las estrellas de GitHub se consultaron con la API de búsqueda de GitHub el 18/11/2026.

---

## 3. Tabla comparativa de estrategias

Completa en [`estrategias.csv`](estrategias.csv) (principio, mercados, capital, evidencia,
riesgos, automatización y veredicto). Métricas cuando hay fuente:

| Estrategia | Rentabilidad documentada | Caída / riesgo | Sharpe · Sortino · PF · acierto | Categoría | Veredicto |
|---|---|---|---|---|---|
| **Cash-and-carry / funding** | Carry medio **>10 %/año**, variable (hasta 40–60 %) ([BIS WP 1087](https://www.bis.org/publ/work1087.htm)); funding base de Binance 0,01 %/8 h ≈ **10,95 %/año bruto** ([Binance](https://www.binance.com/en/support/faq/introduction-to-binance-futures-funding-rates-360033525031)) | Un carry alto **predice caídas** de precio; riesgo de exchange y de liquidación | NO VERIFICADO | C | **Mejor evidencia estructural** |
| **Seguimiento de tendencia** | TSMOM fuerte en cripto, sobre todo en mercados alcistas ([Han, Kang y Ryu](https://acfr.aut.ac.nz/__data/assets/pdf_file/0009/918729/Time_Series_and_Cross_Sectional_Momentum_in_the_Cryptocurrency_Market_with_IA.pdf)); 18 % CAGR neto long-only, 2015–2025, con 0,10 % de costes (resumen secundario de [CXO](https://www.cxoadvisory.com/?p=46798), paper no verificado) | Lateral prolongado | NO VERIFICADO | C | **Candidata direccional principal** |
| **Momentum transversal** | Factor momentum en el modelo de 3 factores ([Liu, Tsyvinski y Wu, J. Finance 2022](https://econpapers.repec.org/RePEc:bla:jfinan:v:77:y:2022:i:2:p:1133-1177)) | *Data snooping* advertido por los propios autores | NO VERIFICADO | C | Complemento (ya implementado) |
| Reversión intradía | Datos propios: predice algo, pero **pierde tras costes** | Costes ≈ movimiento | NO VERIFICADO | C | Solo con costes muy bajos |
| Grid trading | **Valor esperado ≈ 0** sin comisiones ([Chen et al. 2025](https://arxiv.org/abs/2506.11921v1), preprint); ruina casi segura a largo plazo ([Taranto y Khan](https://businessperspectives.org/journals/investment-management-and-financial-innovations/issue-360/gambler-s-ruin-problem-and-bi-directional-grid-constrained-trading-and-investment-strategies)) | Tendencias fuera de rango | — | C | **No recomendada** |
| Market making minorista | Sin P&L neto público; selección adversa e inventario ([Hummingbot](https://docs.hummingbot.org/liquidity-mining.pdf)) | Inventario | — | E | **No para este perfil** |
| Arbitraje entre exchanges | Grande en 2017–2018 entre países (Makarov y Schoar, JFE 2020; [DOI](https://doi.org/10.1016/j.jfineco.2019.07.001), conocimiento previo, no consultado hoy) | Competencia y latencia | — | C | No recomendada hoy |
| Machine learning | Ingenuo: **falla con 10 pb de costes**; con filtro de costes, positivo en algunas configuraciones ([preprint 2026](https://ideas.repec.org/p/arx/papers/2606.00060.html)) | Sobreajuste | Sharpe >1 en la mejor configuración, sin dominancia estadística | C | Solo con validación estricta |
| RL, microestructura, volume profile, pares | NO VERIFICADO | — | — | — | No prioritarias |

---

## 4. Historiales verificables encontrados

**Ninguno de categoría A relacionado con los bots y estrategias investigados.**

- Las 10 plataformas comerciales: **E**.
- Myfxbook y Darwinex ofrecen verificación **B**, pero no encontré, para cripto
  spot automatizado, un historial público de ≥180 días con capital real
  identificado y beneficio neto ≥3.000 €/mes.
- Si aparece alguno, debe cumplir: cuenta real (no demo), capital inicial
  publicado, todas las operaciones (no una selección), ≥180 días, resultados
  netos de costes y verificación del bróker.

---

## 5. Informe de rentabilidad y riesgo

- **Mejor evidencia estructural:** el carry (funding y base). Unos ~11 %/año brutos
  en el funding base, más en épocas de euforia. Es decir, **≈0,9 % al mes bruto**,
  antes de comisiones, del riesgo de exchange y de los periodos de funding negativo.
- **Direccional (tendencia):** puede batir a comprar y mantener en grandes ciclos,
  con caídas largas y meses planos. Categoría C.
- **Lo que no tiene evidencia:** grid, martingala, market making minorista y ML ingenuo.
- **Benchmark obligatorio:** comprar y mantener BTC y una cesta equiponderada. En
  el periodo de nuestros datos, la cesta cayó entre un 17 % y un 27 %.

---

## 6. Capital necesario para 3.000 € netos al mes (escenarios matemáticos)

**Supuestos:**
- costes de trading del 0,2 % del capital al mes (rotación moderada; comisión 0,1 % + deslizamiento);
- infraestructura de 20 €/mes (0 € con el servidor gratuito de Oracle);
- caída potencial creciente con la rentabilidad exigida;
- «capital mínimo de seguridad» = capital necesario para seguir teniendo el capital base después de esa caída;
- **sin apalancamiento**.

| Rentabilidad NETA mensual | Capital necesario | Beneficio bruto/mes | Costes de trading/mes | Infraestructura/mes | Beneficio neto/mes | Caída potencial (supuesto) | Pérdida en esa caída | Capital mínimo de seguridad |
|---|---|---|---|---|---|---|---|---|
| 1 % | 302.000 € | 3.624 € | 604 € | 20 € | 3.000 € | 15 % | 45.300 € | 355.294 € |
| 2 % | 151.000 € | 3.322 € | 302 € | 20 € | 3.000 € | 20 % | 30.200 € | 188.750 € |
| 3 % | 100.667 € | 3.221 € | 201 € | 20 € | 3.000 € | 25 % | 25.167 € | 134.222 € |
| 5 % | 60.400 € | 3.141 € | 121 € | 20 € | 3.000 € | 40 % | 24.160 € | 100.667 € |
| 10 % | 30.200 € | 3.080 € | 60 € | 20 € | 3.000 € | 60 % | 18.120 € | 75.500 € |

**Qué es demostrable y qué no:**
- Solo el escenario del **1 % mensual** está cerca de lo que respalda la evidencia
  estructural (carry ≈0,9 % bruto), y aun así es categoría C.
- Del 2 % mensual en adelante **no hay evidencia verificada** de que sea sostenible.
- Con **100 €**, 3.000 €/mes equivaldría a un **3.000 % mensual**: no es alcanzable.

---

## 7. Ranking cuantitativo (100 puntos)

Reglas: lo que no está demostrado puntúa **0** y se marca NO VERIFICADO. Los
frameworks no tienen rentabilidad propia, así que «Evidencia real» y «Rendimiento
ajustado al riesgo» no les aplican (0).

| # | Candidato | Evidencia real (30) | Riesgo ajustado (25) | Consistencia (15) | Costes (10) | Seguridad (10) | Transparencia (5) | Implementación (5) | **Total** |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **CCXT + bot propio autoalojado** (este proyecto) | 0 NV | 0 NV | 0 NV | 8 | 9 | 5 | 4 | **26** |
| 2 | Freqtrade | 0 NV | 0 NV | 0 NV | 8 | 8 | 5 | 4 | **25** |
| 3 | Jesse | 0 NV | 0 NV | 0 NV | 8 | 8 | 5 | 3 | **24** |
| 4 | Hummingbot | 0 NV | 0 NV | 0 NV | 7 | 8 | 5 | 3 | **23** |
| 5 | QuantConnect LEAN | 0 NV | 0 NV | 0 NV | 7 | 8 | 5 | 2 | **22** |
| 6 | Backtrader | 0 NV | 0 NV | 0 NV | 8 | 8 | 4 | 2 | **22** |
| 7 | Gunbot (autoalojado) | 0 NV | 0 NV | 0 NV | 6 | 6 | 1 | 4 | **17** |
| 8 | Pionex | 0 NV | 0 NV | 0 NV | 7 | 4 | 1 | 5 | **17** |
| 9 | Plataformas SaaS con claves en servidores de terceros (Cryptohopper, Bitsgap, Coinrule, TradeSanta, WunderTrading, Altrady, HaasOnline) | 0 NV | 0 NV | 0 NV | 5 | 4 | 1 | 5 | **15** |
| 10 | 3Commas | 0 NV | 0 NV | 0 NV | 5 | 1 | 1 | 5 | **12** |

Las puntuaciones de costes, seguridad, transparencia e implementación son
valoraciones cualitativas basadas en hechos comprobables: código abierto o
cerrado, quién guarda las claves e incidentes documentados.

**Lectura correcta:** **ningún candidato supera 26/100**, porque **nadie aporta
evidencia real de rentabilidad**. No hay un top 10 «demostrado». Este ranking
mide solo cuál es la mejor **base técnica y segura** para construir y validar.

---

## 8. Arquitectura propuesta y estado actual del proyecto

**Inspección del proyecto existente:**
- Lenguaje: Python ≥3.9.
- Dependencias: `httpx` (librería) y `ccxt` (bot).
- Unas 3.700 líneas de Python en `examples/trading_agents/` y 63 tests sin red.
- CI en 6 versiones de Python, más el workflow con datos reales.
- Corre en Linux, Windows (asistente), Docker/Oracle y GitHub Actions.

| Motor pedido | Estado en el bot | Qué falta |
|---|---|---|
| **A. Market data** | Velas OHLCV con reintentos y respaldo (OKX/Bybit/Kraken), flujo *taker*, funding, Fear & Greed, contexto entre monedas | Libro de órdenes, interés abierto, **chequeo de integridad de datos** (huecos, velas viejas, saltos absurdos) |
| **B. Intelligence** | 105 agentes en 7 equipos, régimen de mercado, aprendizaje Hedge, IC por agente, analista LLM opcional | Detección de anomalías; **retirar los agentes sin IC** (84 de 105 en 1 h) |
| **C. Strategy** | Consejo con veto, calibrador de probabilidad verificada (Wilson, z=3), selección del perfil de salida | **Estrategia de carry** delta-neutral; control de **correlación** entre posiciones |
| **D. Risk** | 1 % por operación, límite de riesgo total del 3 %, stop/objetivo/horizonte, pausa tras 3 pérdidas, interruptor al 10 % de caída, tope de capital, puerta de 20 días | **Límite de pérdida diaria**; parada ante volatilidad extrema (hoy solo hay veto) |
| **E. Execution** | ccxt mercado y límite, stop en el exchange, parciales, cancelación | **Idempotencia** (`clientOrderId`) contra órdenes duplicadas; **conciliación** con el exchange al arrancar |
| **F. Monitoring** | Informe diario y mensual estilo quantstats, Telegram, GitHub, registros | **Diario de decisiones** auditable (JSONL); alerta de conexión caída |

---

## 9. Diseño técnico de los módulos nuevos

1. **`integrity` (nodo del grafo):**
   - rechaza la vela si su marca de tiempo no es la esperada;
   - rechaza la vela si falta más de una vela;
   - rechaza la vela si el precio salta más de N veces el ATR sin volumen;
   - rechaza la vela si un símbolo se queda atrás.

   Ante datos dudosos, **no opera** y avisa.
2. **`daily_loss_guard`:** si la pérdida realizada más la no realizada del día UTC
   supera el X % (por defecto 3 %), no abre nada más hasta el día siguiente.
3. **`decision_log`:** un JSONL por día con cada decisión: entradas, veredicto de
   cada equipo, vetos con su motivo, probabilidad verificada, orden enviada y
   respuesta del exchange.
4. **`execution` idempotente:**
   - cada orden lleva un `clientOrderId` determinista (símbolo + vela + tipo);
   - si al reintentar ya existe, se recupera en lugar de duplicarse;
   - al arrancar, se concilian las posiciones del libro con los saldos reales del exchange.
5. **`carry` (estrategia independiente, solo papel primero):**
   - largo spot y corto perpetuo del mismo importe;
   - entra solo si el funding medio esperado menos los costes es mayor que 0 con margen;
   - sale si el funding se vuelve negativo de forma sostenida;
   - control del margen de la pata corta;
   - **requiere verificar** que tu país de la UE permite derivados cripto a minoristas en el exchange elegido.
6. **`universe`:** universo histórico sin sesgo de supervivencia. Elige las N
   mayores monedas **de cada fecha** del backtest, no las de hoy.
7. **`validation`:**
   - sensibilidad de parámetros (rejilla alrededor de la campeona);
   - PBO/CSCV de López de Prado;
   - *Deflated Sharpe*;
   - comparación con BTC comprar y mantener y con la cesta equiponderada.

---

## 10. Plan de desarrollo por fases

| Fase | Contenido | Criterio de salida |
|---|---|---|
| **0 (hecha)** | Investigación y este informe | Revisado por ti |
| **1. Seguridad operativa ✔ (hecha)** | Integridad de datos, límite de pérdida diaria, diario de decisiones, idempotencia, conciliación, datos atrasados, alertas de conexión | Tests ✔ · pendiente: 7 días en testnet sin errores |
| **2. Limpieza de señales** | Retirar los agentes sin IC significativo y validar fuera de muestra que no empeora | Validación en 3 tramos + examen final |
| **3. Universo sin sesgo** | Top-N histórico | Re-backtest con datos reales |
| **4. Estrategia de carry** | Módulo en papel | 90 días en papel con funding real |
| **5. Validación científica completa ◐ (herramienta hecha: `bot.py validate`)** | Sensibilidad, PBO, Deflated Sharpe, Monte Carlo, regímenes, benchmarks | PBO ≤ 0,25 y Deflated Sharpe ≥ 0,95 · resultado 2026-11: **ninguna estrategia validada** |
| **6. Papel en vivo** | ≥ 20 días (recomendado 90) | `gate` = APTO |
| **7. Testnet** | 2–3 días | Sin errores técnicos |
| **8. Real mínimo** | Solo con tu **autorización expresa** | 180 días para hablar de consistencia |

---

## 11. Plan de validación y pruebas

| Prueba pedida | Estado |
|---|---|
| Backtest con costes reales | ✔ comisión, deslizamiento, maker/taker, mínimos de orden |
| Entrenamiento y validación separados | ✔ aprender 40 % / validar 40 % / examen 20 % |
| Walk-forward | ✔ 3 tramos + examen final; aprendizaje online punto-en-el-tiempo |
| Out-of-sample | ✔ examen final con datos nunca vistos |
| Look-ahead bias | ✔ funding con `bisect` punto-en-el-tiempo, sombras resueltas solo con velas posteriores, órdenes límite en la vela siguiente |
| Survivorship bias | ✘ **pendiente**: el universo es el top 8 de hoy (fase 3) |
| Monte Carlo | ✔ prueba de estrés con el riesgo realmente tomado |
| Regímenes de mercado | ✔ estadística separada por régimen |
| Sensibilidad de parámetros | ✔ `validate`: los parámetros vecinos también deben ganar |
| PBO / Deflated Sharpe | ✔ `validate`: PBO por CSCV (16 bloques) y Deflated Sharpe con todas las pruebas descontadas |
| Buy & Hold y benchmarks | ✔ cesta equiponderada; falta BTC solo (fase 5) |
| Paper trading obligatorio | ✔ puerta de 20 días en el código |

---

## 12. Recomendación final basada en evidencia

1. **El objetivo de 3.000 €/mes no es alcanzable con el capital actual**, y no he
   encontrado evidencia de categoría A de ningún sistema que lo consiga de forma
   consistente. Cualquier oferta que lo prometa con poco capital debe tratarse como
   **sospechosa**.
2. **La combinación con mejor evidencia**, todas de categoría C, ninguna demostrada aún con dinero real:
   - **carry delta-neutral** (funding o base), como motor principal de baja volatilidad;
   - **seguimiento de tendencia** en BTC/ETH con control de volatilidad, como motor direccional;
   - **momentum transversal** entre grandes monedas, como filtro;
   - todo ello con la gestión de riesgo actual del bot más las mejoras de la fase 1.
3. **Lo que conviene descartar:** grid, martingala, market making minorista,
   arbitraje entre exchanges, RL y ML sin validación estricta, y las plataformas
   SaaS que guardan tus claves.
4. **Prioridad, como pides:** supervivencia del capital → consistencia →
   rentabilidad → escalabilidad. El bot ya aplica esa prioridad: con los datos
   actuales **no opera**, porque nada cumple el 77 % verificado.
5. **Siguiente paso recomendado:** la **fase 1** (seguridad operativa), y en
   paralelo dejar el bot 90 días en papel. Con el escenario más favorable
   documentado (≈1 % mensual), 3.000 €/mes exigiría ~300.000 €. La decisión de
   escalar capital solo debería tomarse **después de 180 días de resultados reales
   positivos**, empezando con importes que puedas permitirte perder.

**No se ha realizado ninguna operación real ni se ha conectado ninguna cuenta financiada.**

---

### Fuentes (consultadas el 18/11/2026)

- 3Commas:
  [Cointelegraph](https://cointelegraph.com/news/3commas-ceo-confirms-api-key-leak-following-warning-from-cz) ·
  [Decrypt](https://decrypt.co/118094/after-repeated-denials-3commas-admits-it-was-source-for-earlier-hacks/) ·
  [Halborn](https://www.halborn.com/blog/post/explained-the-3commas-breach-december-2022) ·
  [ForkLog/HAPI](https://forklog.com/en/news/api-key-leaks-and-exchange-inaction-a-hapi-analysis-of-the-3commas-incident) ·
  [Finance Magnates (FBI)](https://www.financemagnates.com/cryptocurrency/fbi-is-reportedly-investigating-3commas-api-leak/)
- Plataformas:
  [Gainium sobre Cryptohopper](https://gainium.io/review/cryptohopper) ·
  [Pionex FAQ de grid](https://intercom.help/pionex/en/articles/15500905-grid-trading-bot-faq) ·
  [Coin Bureau](https://www.coinbureau.com/analysis/best-crypto-ai-trading-bots) ·
  [Zignaly (comparativa)](https://zignaly.com/crypto-trading/bots/cryptocurrency-trading-bots-comparison) ·
  [BeInCrypto](https://beincrypto.com/?p=387986) ·
  [SoftwareSuggest](https://www.softwaresuggest.com/wundertrading/alternatives) ·
  [SourceForge](https://www.sourceforge.net/software/product/Altrady/alternatives) ·
  [Coinspot (HaasOnline)](https://coinspot.io/en/reviews/haasonline/)
- Verificación:
  [Myfxbook](https://www.myfxbook.com/help/verification) ·
  [BabyPips](https://forums.babypips.com/t/a-guide-to-using-and-recognising-myfxbook-accounts/52656) ·
  [Darwinex](https://help.darwinex.com/what-are-investable-attributes)
- Académicas:
  [BIS WP 1087 «Crypto carry»](https://www.bis.org/publ/work1087.htm) ·
  [Liu, Tsyvinski y Wu (J. Finance 2022)](https://econpapers.repec.org/RePEc:bla:jfinan:v:77:y:2022:i:2:p:1133-1177) ·
  [Han, Kang y Ryu (momentum)](https://acfr.aut.ac.nz/__data/assets/pdf_file/0009/918729/Time_Series_and_Cross_Sectional_Momentum_in_the_Cryptocurrency_Market_with_IA.pdf) ·
  [CXO Advisory](https://www.cxoadvisory.com/?p=46798) ·
  [Bailey et al. (AMS)](https://scholarworks.wmich.edu/math_pubs/40/) ·
  [PBO (SSRN)](https://papers.ssrn.com/abstract=2326253) ·
  [Barber et al. (day trading)](https://faculty.haas.berkeley.edu/odean/papers/day%20traders/Day%20Trading%20Skill%20110523.pdf) ·
  [Grid: Chen et al.](https://arxiv.org/abs/2506.11921v1) ·
  [Grid: Taranto y Khan](https://businessperspectives.org/journals/investment-management-and-financial-innovations/issue-360/gambler-s-ruin-problem-and-bi-directional-grid-constrained-trading-and-investment-strategies) ·
  [ML en BTC (preprint 2026)](https://ideas.repec.org/p/arx/papers/2606.00060.html) ·
  [Makarov y Schoar (DOI)](https://doi.org/10.1016/j.jfineco.2019.07.001)
- Mercado y regulación:
  [Binance funding](https://www.binance.com/en/support/faq/introduction-to-binance-futures-funding-rates-360033525031) ·
  [BitMEX Q3 2025](https://blog.bitmex.com/2025q3-derivatives-report) ·
  [ESMA (CFD)](https://www.esma.europa.eu/sites/default/files/library/esma35-43-1135_notice_of_pi_decisions_on_cfds_and_binary_options.pdf) ·
  [ESMA/AMF fin del periodo transitorio de MiCA](https://www.amf-france.org/en/news-publications/news/end-mica-transitional-period-esma-sets-out-its-expectations-professionals-and-warns-retail-investors) ·
  [Advertencia de las ESAs](https://esma.europa.eu/press-news/esma-news/eu-supervisory-authorities-warn-consumers-risks-and-limited-protection-certain) ·
  [Hummingbot (liquidity mining)](https://docs.hummingbot.org/liquidity-mining.pdf)
