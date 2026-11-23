# Instalar el bot en Windows (10 y 11)

1. **Descarga el bot**: en GitHub, botón verde **Code → Download ZIP**.
2. **Descomprímelo** en una carpeta tuya, por ejemplo `Documentos\freelm`.
   No uses una carpeta sincronizada con OneDrive.
3. Entra en `examples\trading_agents\windows` y haz **doble clic en `Instalar-Bot.bat`**.
   Si Windows avisa de que el archivo viene de internet: **Más información → Ejecutar de todas formas**.
4. Elige **1 · Instalación completa**. El asistente:
   - instala Python 3.12 si falta (con `winget`, sin permisos de administrador);
   - instala el bot en un entorno aislado (`.venv`, dentro de la carpeta del bot);
   - te pide las claves **opcionales** (IA gratuita, Telegram) y las guarda en
     `%USERPROFILE%\freelm-bot-datos\bot.env`, que solo puede leer tu usuario;
   - hace la primera optimización con datos reales (10–20 min; se puede saltar);
   - deja el bot funcionando en **papel** (dinero simulado), con velas de 5 minutos,
     y hace que **arranque solo** cada vez que inicias sesión;
   - te ofrece evitar que el PC se suspenda mientras está enchufado (si se suspende, el bot se para);
   - programa la **prueba diaria del momentum en papel** (01:30, o al encender el PC si estaba
     apagado): procesa el día, registra las señales para medir cuánto aciertan y regenera el panel;
   - crea tres accesos en el escritorio: **Panel** (este menú), **Informe** y **Resultados**
     (el panel HTML con el momentum y la tarjeta de aciertos).

## Uso diario

- **Informe**: capital, rendimiento, operaciones, la verificación del 77 % y el
  estado de la **puerta del dinero real**.
- **Panel**, opción 4: ver en directo lo que decide el bot, vela a vela (Ctrl+C para salir).
- Registros: `%USERPROFILE%\freelm-bot-datos\registros\bot-AAAAMMDD.log`.
- **Diario de decisiones**, una línea por cada decisión, con su motivo:
  `%USERPROFILE%\freelm-bot-datos\diario\decisiones-AAAAMMDD.jsonl` (se abre con
  el Bloc de notas).
- Toda la memoria del bot (aprendizaje, configuración campeona, cartera simulada)
  está en `%USERPROFILE%\freelm-bot-datos`. Actualizar o reinstalar el bot no la borra.

## Momentum en papel, tarjeta de aciertos y panel — opciones 14 a 19

| Opción | Qué hace |
|---|---|
| **14** Procesar hoy | Procesa el último día cerrado en papel, registra las señales y regenera el panel (lo mismo que la tarea diaria). |
| **15** Ver el panel | Abre `freelm-bot-datos\panel.html` en el navegador: capital frente a la cesta, posiciones, **cuánto acierta cada señal en vivo**, señales de los últimos días y avisos. |
| **16** Tarjeta de aciertos | Mide cada señal con ~8 años de historia: acierto frente a la tasa base y ventaja, con su intervalo del 95 %. |
| **17** Supabase (opcional) | Guía paso a paso: crear un proyecto gratis, pegar el esquema (se copia solo al portapapeles), guardar la URL y la clave secreta y subir los datos. Así los resultados están también en la nube. |
| **18** Avisos por email (opcional) | Guarda la URL de un webhook (p. ej. Zapier «Catch Hook» → Gmail) y envía un aviso de prueba. |
| **19** Programar la prueba diaria | Vuelve a crear la tarea `FreelmMomentumDiario` (01:30). |

La misma prueba corre a la vez en GitHub (`momentum-paper.yml`). En GitHub, el panel
se guarda en la rama `momentum-state` y como archivo descargable de cada ejecución
(Actions → «momentum (papel, 20 días)» → Artifacts → `panel`). Las claves de Supabase
o del webhook se añaden allí como *secrets* (`SUPABASE_URL`, `SUPABASE_KEY`,
`FREELM_WEBHOOK_URL`). El asistente de la opción 17 abre esa página.

## Probar en la testnet de Binance (cuenta demo) — opción 11

La testnet es una cuenta de Binance con **dinero ficticio** que acepta órdenes de
verdad. Sirve para comprobar que **todo funciona técnicamente** (claves, órdenes,
stop en el exchange, órdenes límite) sin arriesgar nada. **No** sirve para medir
si la estrategia gana: sus precios y su liquidez no son los del mercado real. Eso
lo mide el modo papel, que es el que cuenta para los 20 días. Hazlo **2–3 días
antes** de pasar a dinero real.

El asistente te guía en 6 pasos:

1. **Entrar en la testnet.** Se abre https://testnet.binance.vision; pulsa
   **Log In with GitHub** (gratis, sin datos bancarios).
2. **Crear la clave.** Pulsa **Generate HMAC_SHA256 Key**, descripción `bot`,
   **Generate**, y copia **API Key** y **Secret Key**. El secret solo se muestra
   una vez.
3. **Pegarlas en el asistente** (clic derecho o Ctrl+V; no se ve al escribir). Se
   guardan aparte de las reales (`FREELM_TESTNET_KEY` / `FREELM_TESTNET_SECRET`).
4. **Comprobación automática.** El bot se conecta, lee tu saldo de prueba y los
   mínimos de cada moneda, y coloca una compra límite a **mitad de precio**
   (nunca se ejecuta) que cancela al momento.
5. **Ponerlo en marcha** en la ventana (para verlo en directo) o en segundo plano.
   Usa órdenes límite, velas de 5 minutos y su propia memoria
   (`freelm-bot-datos\testnet`). El bot en papel sigue funcionando a la vez.
6. **Qué revisar en 2–3 días:** opción **13** (informe de la testnet), las órdenes
   en la web de la testnet, que cada compra tenga su stop en el exchange y que no
   haya errores repetidos en `registros\testnet-AAAAMMDD.log`. Para pararlo:
   opción **12**.

Desde la línea de órdenes, lo mismo es: `python bot.py conexion --exchange
testnet --orden-prueba` y `python bot.py live --exchange testnet --entry-mode limit`.

## Dinero real

La opción **9** solo funciona si `gate` dice **APTO**: 20 días en papel, rendimiento
positivo, caída máxima ≤ 10 % y al menos 5 operaciones. Además pide escribir
`CONFIRMO`. El bot nunca usa más de 100 aunque la cuenta tenga más saldo.
Crea las claves del exchange **solo con permiso de trading, nunca de retirada**,
y si puedes, restringidas a tu IP.

## Problemas frecuentes

| Problema | Solución |
|---|---|
| «La ejecución de scripts está deshabilitada» | Abre el asistente con `Instalar-Bot.bat`, no con el `.ps1`: el `.bat` ya lo permite para esta ejecución. |
| Python se instaló pero «no se encuentra» | Cierra el asistente y ábrelo otra vez (Windows actualiza el PATH al abrir una ventana nueva). |
| No hay `winget` | Instala Python desde python.org marcando **Add python.exe to PATH** y vuelve a la opción 1. |
| El bot no opera nunca | Es lo esperado mientras ninguna señal tenga un 77 % de acierto **verificado**: lo verás en el informe («probabilidad no verificada»). |
| La tarea diaria no se ejecutó | Si el PC estaba apagado a las 01:30, se ejecuta al encenderlo. Registro: `freelm-bot-datos\registros\diario-AAAAMMDD.log`. |
| Supabase da error 401 | Has pegado la clave *publishable*: hace falta la **secret key** (o *service_role*). Opción 17 otra vez. |
| El PC se apaga o suspende | El bot se para y vuelve a arrancar solo al iniciar sesión. Para que funcione 24/7 sin tu PC, usa el servidor gratuito de Oracle (ver el README principal). |
