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
   - crea dos accesos en el escritorio: **Panel** (este menú) e **Informe**.

## Uso diario

- **Informe**: capital, rendimiento, operaciones, la verificación del 77 % y el
  estado de la **puerta del dinero real**.
- **Panel**, opción 4: ver en directo lo que decide el bot, vela a vela (Ctrl+C para salir).
- Registros: `%USERPROFILE%\freelm-bot-datos\registros\bot-AAAAMMDD.log`.
- Toda la memoria del bot (aprendizaje, configuración campeona, cartera simulada)
  está en `%USERPROFILE%\freelm-bot-datos`. Actualizar o reinstalar el bot no la borra.

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
| El PC se apaga o suspende | El bot se para y vuelve a arrancar solo al iniciar sesión. Para que funcione 24/7 sin tu PC, usa el servidor gratuito de Oracle (ver el README principal). |
