#requires -version 5.1
<#
  Asistente de instalación del bot de trading (Windows 10/11)
  ------------------------------------------------------------
  Doble clic en "Instalar-Bot.bat" (en esta misma carpeta). El asistente:
    1. instala Python 3.12 si falta (winget, sin permisos de administrador);
    2. crea un entorno aislado e instala el bot y sus dependencias;
    3. guarda tus claves (opcionales) en un archivo solo legible por tu usuario;
    4. hace la primera optimización con datos reales;
    5. deja el bot funcionando en PAPEL (dinero simulado) y arrancando solo al iniciar sesión;
    6. programa la prueba diaria del momentum en papel + la tarjeta de aciertos + el panel;
    7. crea accesos directos en el escritorio (panel, informe, asistente).
  El dinero real queda BLOQUEADO hasta que el bot supere la prueba de 20 días ("gate").
#>
param([string]$Accion = "")

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

# ---------------------------------------------------------------- rutas
$AppDir   = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path        # raíz del repositorio
$BotDir   = Join-Path $AppDir "examples\trading_agents"
$Bot      = Join-Path $BotDir "bot.py"
$Venv     = Join-Path $AppDir ".venv"
$Py       = Join-Path $Venv "Scripts\python.exe"
$DataDir  = Join-Path $env:USERPROFILE "freelm-bot-datos"                   # memoria, cartera, claves, registros
$EnvFile  = Join-Path $DataDir "bot.env"
$ModeFile = Join-Path $DataDir "modo.txt"
$LogDir   = Join-Path $DataDir "registros"
$Starter  = Join-Path $PSScriptRoot "iniciar-bot.ps1"
$TaskName = "FreelmTradingBot"
$DailyTask = "FreelmMomentumDiario"
$PanelFile = Join-Path $DataDir "panel.html"
$SqlFile  = Join-Path $BotDir "deploy\supabase.sql"
$RepoZip  = "https://github.com/tansaavatalia-commits/freelm/archive/refs/heads/main.zip"

# ---------------------------------------------------------------- utilidades
function Titulo([string]$t) { Write-Host ""; Write-Host "=== $t ===" -ForegroundColor Cyan }
function Ok([string]$t)     { Write-Host "  [OK] $t" -ForegroundColor Green }
function Aviso([string]$t)  { Write-Host "  [!]  $t" -ForegroundColor Yellow }
function Fallo([string]$t)  { Write-Host "  [X]  $t" -ForegroundColor Red }
function Tiene([string]$c)  { return [bool](Get-Command $c -ErrorAction SilentlyContinue) }

function SiNo([string]$pregunta, [bool]$porDefecto = $true) {
    $sufijo = "[S/n]"
    if (-not $porDefecto) { $sufijo = "[s/N]" }
    $r = Read-Host "  $pregunta $sufijo"
    if ([string]::IsNullOrWhiteSpace($r)) { return $porDefecto }
    return ($r.Trim().ToLower() -in @("s", "si", "sí", "y", "yes"))
}

function Refrescar-Path {
    $m = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $u = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$m;$u"
}

function Buscar-Python {
    # Devuelve @(ejecutable, argumentos...) de un Python >= 3.9, o $null
    $candidatos = @(@("py", "-3.12"), @("py", "-3"), @("python"))
    foreach ($c in $candidatos) {
        if (-not (Tiene $c[0])) { continue }
        $extra = @()
        if ($c.Count -gt 1) { $extra = $c[1..($c.Count - 1)] }
        try {
            & $c[0] @extra -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { return ,$c }  # la coma evita que PowerShell «aplane» la lista
        } catch {}
    }
    return $null
}

function Cargar-Entorno {
    $env:FREELM_TRADING_DIR = $DataDir
    $env:PYTHONUTF8 = "1"
    if (Test-Path $EnvFile) {
        foreach ($linea in Get-Content $EnvFile) {
            $l = $linea.Trim()
            if ($l -eq "" -or $l.StartsWith("#") -or -not $l.Contains("=")) { continue }
            $i = $l.IndexOf("=")
            $k = $l.Substring(0, $i).Trim()
            $v = $l.Substring($i + 1).Trim()
            if ($v -ne "") { Set-Item -Path "Env:$k" -Value $v }
        }
    }
}

function Ejecutar-Bot([string[]]$argumentos, [switch]$Testnet) {
    if (-not (Test-Path $Py)) { Fallo "El bot no está instalado todavía (opción 1 del menú)."; return 1 }
    Cargar-Entorno
    if ($Testnet) { Entorno-Testnet }
    & $Py $Bot @argumentos | Out-Host   # a la pantalla, no al valor de retorno
    return $LASTEXITCODE
}

# ---------------------------------------------------------------- momentum diario, aciertos, panel, nube
function Momentum-Hoy {
    Titulo "Momentum en papel: procesar el último día cerrado"
    Ejecutar-Bot @("momentum") | Out-Null
    Ejecutar-Bot @("senales", "--record", "--no-history", "--limit", "260") | Out-Null
    Ejecutar-Bot @("panel") | Out-Null
    Ejecutar-Bot @("sync", "--soft") | Out-Null
}

function Diario-Silencioso {
    # lo que ejecuta la tarea programada cada día (sin preguntas, con registro)
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    $log = Join-Path $LogDir ("diario-" + (Get-Date -Format "yyyyMMdd") + ".log")
    Start-Transcript -Path $log -Append | Out-Null
    try { Momentum-Hoy } finally { Stop-Transcript | Out-Null }
}

function Paso-Diario {
    Titulo "Prueba diaria del momentum (papel) + tarjeta de aciertos + panel"
    Write-Host "  Cada día a las 01:30 (o al encender el PC si estaba apagado) el bot procesa el día cerrado,"
    Write-Host "  registra las señales para medir cuánto aciertan y regenera el panel. Nunca usa dinero real."
    $accion = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`" -Accion diario"
    $disparo = New-ScheduledTaskTrigger -Daily -At "01:30"
    $ajustes = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
    Register-ScheduledTask -TaskName $DailyTask -Action $accion -Trigger $disparo -Settings $ajustes `
        -Description "Momentum en papel + tarjeta de aciertos (freelm)" -Force | Out-Null
    Ok "Tarea diaria '$DailyTask' programada."
    if (SiNo "¿Procesar ya el día de hoy?") { Momentum-Hoy }
    return $true
}

function Ver-Panel {
    Ejecutar-Bot @("panel") | Out-Null
    if (Test-Path $PanelFile) { Start-Process $PanelFile; Ok "Panel abierto en el navegador: $PanelFile" }
    else { Aviso "Todavía no hay datos: usa la opción 14 (procesar hoy) o espera a la tarea diaria." }
}

function Tarjeta-Aciertos {
    Titulo "Tarjeta de aciertos de las señales (historia + en vivo)"
    Write-Host "  Descarga ~8 años de velas diarias de Binance (1-2 min) y mide cuánto acierta cada señal."
    Ejecutar-Bot @("senales", "--record") | Out-Null
}

function Configurar-Supabase {
    Titulo "Base de datos en la nube (Supabase, gratis) - opcional"
    Write-Host "  Sirve para ver los resultados desde cualquier sitio y guardarlos fuera del PC."
    Write-Host "  1. Se abrirá supabase.com: entra (con GitHub o email) y crea un proyecto GRATIS"
    Write-Host "     (nombre: freelm-trading-bot, región: Central EU / Frankfurt). Espera 1-2 minutos."
    Pausa "Pulsa Enter para abrir Supabase"
    Start-Process "https://supabase.com/dashboard/new"
    Pausa "Cuando el proyecto esté listo, pulsa Enter"
    Write-Host "  2. En el proyecto: SQL Editor > New query. He copiado el esquema al portapapeles:"
    Write-Host "     pégalo (Ctrl+V) y pulsa Run. Debe decir 'Success'."
    try { Get-Content $SqlFile -Raw | Set-Clipboard; Ok "Esquema copiado ($SqlFile)." }
    catch { Aviso "No pude copiarlo: abre $SqlFile, cópialo entero y pégalo."; Start-Process notepad.exe $SqlFile }
    Pausa "Cuando diga Success, pulsa Enter"
    Write-Host "  3. Project Settings > API (o 'Connect'): copia la Project URL y la clave SECRETA"
    Write-Host "     (secret key / service_role). La clave publishable NO sirve para escribir."
    $url = (Read-Host "  Project URL (https://xxxx.supabase.co)").Trim()
    if ($url -notmatch "^https://[a-z0-9-]+\.supabase\.co/?$") { Aviso "Esa URL no parece de Supabase; no se guarda nada."; return }
    $key = Leer-Secreto "Clave secreta de Supabase"
    if ($key -eq "") { Aviso "Sin clave no se guarda nada."; return }
    Guardar-Clave "SUPABASE_URL" $url
    Guardar-Clave "SUPABASE_KEY" $key
    Ok "Guardadas en $EnvFile (solo legible por tu usuario)."
    Ejecutar-Bot @("sync") | Out-Null
    Write-Host ""
    Write-Host "  4. (Opcional) Para que GitHub también suba los resultados cada día: en GitHub,"
    Write-Host "     Settings > Secrets and variables > Actions > New repository secret, crea"
    Write-Host "     SUPABASE_URL y SUPABASE_KEY con esos mismos valores."
    if (SiNo "¿Abrir esa página de GitHub ahora?" $false) {
        Start-Process "https://github.com/tansaavatalia-commits/freelm/settings/secrets/actions"
    }
}

function Configurar-Avisos {
    Titulo "Avisos diarios (Telegram o email vía webhook)"
    Write-Host "  Opción A, Telegram: opción 3 del menú (token + chat id)."
    Write-Host "  Opción B, email/Gmail con Zapier (gratis): en zapier.com crea un Zap con disparador"
    Write-Host "  'Webhooks by Zapier > Catch Hook' y acción 'Gmail > Send Email' (cuerpo: el campo 'text')."
    Write-Host "  Copia la URL del webhook (https://hooks.zapier.com/...) y pégala aquí."
    $u = Leer-Secreto "URL del webhook"
    if ($u -eq "") { Aviso "Sin cambios."; return }
    if (-not $u.StartsWith("https://")) { Aviso "La URL debe empezar por https://"; return }
    Guardar-Clave "FREELM_WEBHOOK_URL" $u
    Ok "Webhook guardado."
    Ejecutar-Bot @("notificar") | Out-Null
    Write-Host "  Para recibirlo también desde GitHub: crea el secret FREELM_WEBHOOK_URL en el repositorio."
}

# ---------------------------------------------------------------- testnet (cuenta demo de Binance)
$TestnetDir = Join-Path $DataDir "testnet"

function Entorno-Testnet {
    # las claves de la testnet se guardan aparte y solo se usan en este proceso: nunca pisan las reales
    $env:FREELM_EXCHANGE_KEY = $env:FREELM_TESTNET_KEY
    $env:FREELM_EXCHANGE_SECRET = $env:FREELM_TESTNET_SECRET
    $env:FREELM_TRADING_DIR = $TestnetDir   # memoria y cartera separadas de las del modo papel
    New-Item -ItemType Directory -Force -Path $TestnetDir | Out-Null
    $champ = Join-Path $DataDir "champion.json"
    if ((Test-Path $champ) -and -not (Test-Path (Join-Path $TestnetDir "champion.json"))) {
        Copy-Item $champ $TestnetDir
    }
}

function Pausa([string]$texto = "Pulsa Enter para continuar") { Read-Host "  $texto" | Out-Null }

function Guardar-Clave([string]$k, [string]$v) {
    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
    $lineas = @()
    if (Test-Path $EnvFile) { $lineas = @(Get-Content $EnvFile | Where-Object { $_ -notmatch "^\s*$k\s*=" }) }
    if ($lineas.Count -eq 0) { $lineas = @("# Claves del bot de trading. NO compartas este archivo.") }
    $lineas += "$k=$v"
    Set-Content -Path $EnvFile -Value $lineas -Encoding UTF8
    & icacls $EnvFile /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null
}

function Parar-Testnet {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*bot.py*live*--exchange*testnet*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*iniciar-bot.ps1*-Modo testnet*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

function Probar-Testnet {
    Titulo "Probar en la TESTNET de Binance (cuenta demo, dinero ficticio)"
    Write-Host "  Para qué sirve: comprobar que las claves, las órdenes, el stop en el exchange y las órdenes"
    Write-Host "  límite funcionan, sin arriesgar nada. NO sirve para medir si la estrategia gana: los precios"
    Write-Host "  y la liquidez de la testnet no son los del mercado real (eso lo mide el modo papel)."
    Write-Host "  Recomendado: 2-3 días, justo antes de pasar a dinero real."
    if (-not (Test-Path $Py)) { Fallo "Primero instala el bot (opción 1)."; return }

    Titulo "Paso 1 de 6 · Entrar en la testnet"
    Write-Host "  Se abrirá https://testnet.binance.vision en tu navegador."
    Write-Host "  Pulsa 'Log In with GitHub' y entra con tu cuenta de GitHub (es gratis; no pide datos bancarios)."
    Pausa "Pulsa Enter para abrir la página"
    Start-Process "https://testnet.binance.vision/"
    Pausa "Cuando hayas entrado, pulsa Enter"

    Titulo "Paso 2 de 6 · Crear la clave API de la testnet"
    Write-Host "  En esa página pulsa 'Generate HMAC_SHA256 Key', pon de descripción 'bot' y pulsa 'Generate'."
    Write-Host "  Verás 'API Key' y 'Secret Key'. COPIA LAS DOS AHORA: el secret solo se muestra una vez."
    Write-Host "  (Estas claves solo valen para la testnet; no tienen nada que ver con tu dinero real.)"
    Pausa "Cuando las tengas copiadas, pulsa Enter"

    Titulo "Paso 3 de 6 · Guardar las claves"
    Write-Host "  Pega cada una con clic derecho (o Ctrl+V) y Enter. No se verá al escribir: es normal."
    $k = Leer-Secreto "API Key de la testnet"
    $s = Leer-Secreto "Secret Key de la testnet"
    if ($k -ne "") { Guardar-Clave "FREELM_TESTNET_KEY" $k }
    if ($s -ne "") { Guardar-Clave "FREELM_TESTNET_SECRET" $s }
    Cargar-Entorno
    if (-not $env:FREELM_TESTNET_KEY -or -not $env:FREELM_TESTNET_SECRET) {
        Fallo "Faltan las claves de la testnet. Vuelve a esta opción cuando las tengas."; return
    }
    Ok "Claves de testnet guardadas (aparte de las reales)."

    Titulo "Paso 4 de 6 · Comprobar la conexión"
    Write-Host "  El bot se conecta, lee tu saldo de prueba y los mínimos de cada moneda, y coloca una compra"
    Write-Host "  límite a MITAD de precio (nunca se ejecuta) que cancela al momento."
    $rc = Ejecutar-Bot @("conexion", "--exchange", "testnet", "--orden-prueba") -Testnet
    if ($rc -eq 2) { Fallo "Comprobación rechazada."; return }
    if ($rc -ne 0) {
        Aviso "Hubo avisos o errores (arriba). Si dice 'Invalid API-key' o similar, repite el paso 2 y 3."
        if (-not (SiNo "¿Seguir de todos modos?" $false)) { return }
    } else { Ok "Conexión y órdenes verificadas." }

    Titulo "Paso 5 de 6 · Poner el bot a funcionar en la testnet"
    Write-Host "  a) En esta ventana: ves cada decisión en directo (Ctrl+C para parar)."
    Write-Host "  b) En segundo plano: sigue funcionando aunque cierres esto (registro aparte)."
    Write-Host "  El modo papel (el que cuenta los 20 días) sigue funcionando igual en ambos casos."
    $op = Read-Host "  Elige a o b"
    if ($op.Trim().ToLower() -eq "b") {
        Parar-Testnet
        Start-Process powershell.exe -WindowStyle Minimized -ArgumentList @(
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$Starter`"", "-Modo", "testnet")
        Ok "Bot de testnet en marcha en segundo plano (ventana minimizada)."
        Write-Host "  Registro: $LogDir\testnet-AAAAMMDD.log"
    } else {
        Ejecutar-Bot @("live", "--interval", "5m", "--exchange", "testnet", "--entry-mode", "limit", "--llm") -Testnet | Out-Null
    }

    Titulo "Paso 6 de 6 · Qué revisar en 2-3 días"
    Write-Host "  - Opción 13 del menú: informe de la testnet (operaciones, órdenes límite, errores)."
    Write-Host "  - En https://testnet.binance.vision verás las órdenes reales que colocó el bot."
    Write-Host "  - Que el stop aparezca como orden en el exchange en cada compra."
    Write-Host "  - Que no haya errores repetidos en el registro."
    Write-Host "  Si todo va bien y la puerta (opción 2) dice APTO, ya puedes plantearte el dinero real (opción 9)."
    Write-Host "  Para parar el bot de testnet: opción 12."
}

function Informe-Testnet {
    Titulo "Informe de la testnet"
    Ejecutar-Bot @("report", "--plain", "--exchange", "testnet") -Testnet | Out-Null
    $hoy = Join-Path $LogDir ("testnet-" + (Get-Date -Format "yyyyMMdd") + ".log")
    if (Test-Path $hoy) { Titulo "Últimas líneas del registro de testnet"; Get-Content $hoy -Tail 25 }
}

# ---------------------------------------------------------------- pasos
function Paso-Python {
    Titulo "1/7 Python"
    $py = Buscar-Python
    if ($py) { Ok ("Python encontrado: " + ($py -join " ")); return $true }
    Aviso "No hay Python 3.9 o superior."
    if (Tiene "winget") {
        if (SiNo "¿Instalar Python 3.12 ahora con winget (gratis, oficial, sin administrador)?") {
            winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements | Out-Host
            Refrescar-Path
            $py = Buscar-Python
            if ($py) { Ok "Python instalado."; return $true }
            Aviso "Python se instaló, pero esta ventana aún no lo ve. Cierra el asistente y ábrelo de nuevo."
            return $false
        }
    }
    Aviso "Instálalo a mano desde python.org y marca la casilla 'Add python.exe to PATH'."
    Start-Process "https://www.python.org/downloads/windows/"
    return $false
}

function Paso-Dependencias {
    Titulo "2/7 Entorno e instalación del bot"
    $py = Buscar-Python
    if (-not $py) { Fallo "Falta Python (paso 1)."; return $false }
    $extra = @()
    if ($py.Count -gt 1) { $extra = $py[1..($py.Count - 1)] }
    if (-not (Test-Path $Py)) {
        & $py[0] @extra -m venv $Venv | Out-Host
        if ($LASTEXITCODE -ne 0) { Fallo "No se pudo crear el entorno."; return $false }
    }
    & $Py -m pip install --upgrade pip --quiet | Out-Host
    & $Py -m pip install -e $AppDir ccxt --quiet | Out-Host
    if ($LASTEXITCODE -ne 0) { Fallo "Falló la instalación de dependencias (¿hay conexión a internet?)."; return $false }
    & $Py -c "import freelm, ccxt, httpx; print('ok')" | Out-Null
    if ($LASTEXITCODE -ne 0) { Fallo "La instalación no se pudo verificar."; return $false }
    New-Item -ItemType Directory -Force -Path $DataDir, $LogDir | Out-Null
    Ok "Bot instalado en $AppDir; datos en $DataDir"
    return $true
}

function Leer-Secreto([string]$texto) {
    $s = Read-Host "  $texto (Enter para dejarlo como está)" -AsSecureString
    $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) }
}

function Paso-Claves {
    Titulo "3/7 Claves (todas opcionales)"
    Write-Host "  Se guardan en $EnvFile, legible solo por tu usuario de Windows."
    Write-Host "  - IA gratuita: https://aistudio.google.com/apikey (Gemini) o https://console.groq.com/keys (Groq)"
    Write-Host "  - Telegram: habla con @BotFather, /newbot -> token; luego escribe a tu bot y mira tu chat id en"
    Write-Host "    https://api.telegram.org/bot<TOKEN>/getUpdates"
    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
    $valores = [ordered]@{}
    if (Test-Path $EnvFile) {
        foreach ($linea in Get-Content $EnvFile) {
            if ($linea -match "^\s*([A-Z_]+)\s*=\s*(.*)$") { $valores[$Matches[1]] = $Matches[2] }
        }
    }
    $campos = [ordered]@{
        "GEMINI_API_KEY"     = "Clave de Gemini (IA)"
        "GROQ_API_KEY"       = "Clave de Groq (IA)"
        "TELEGRAM_BOT_TOKEN" = "Token del bot de Telegram"
        "TELEGRAM_CHAT_ID"   = "Tu chat id de Telegram"
    }
    # SUPABASE_* y FREELM_WEBHOOK_URL tienen su propia opción del menú (17 y 18) y se conservan aquí
    foreach ($k in $campos.Keys) {
        $v = Leer-Secreto $campos[$k]
        if ($v -ne "") { $valores[$k] = $v }
    }
    if (SiNo "¿Añadir ahora las claves del exchange (solo para la fase de dinero real, después de los 20 días)?" $false) {
        Aviso "Crea la clave en Binance con permiso de TRADING y SIN permiso de RETIRADA, restringida a tu IP."
        $v = Leer-Secreto "API key del exchange";    if ($v -ne "") { $valores["FREELM_EXCHANGE_KEY"] = $v }
        $v = Leer-Secreto "API secret del exchange"; if ($v -ne "") { $valores["FREELM_EXCHANGE_SECRET"] = $v }
    }
    $lineas = @("# Claves del bot de trading. NO compartas este archivo.")
    foreach ($k in $valores.Keys) { $lineas += "$k=$($valores[$k])" }
    Set-Content -Path $EnvFile -Value $lineas -Encoding UTF8
    # permisos: solo el usuario actual
    & icacls $EnvFile /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null
    Ok "Claves guardadas ($($valores.Count))."
    return $true
}

function Paso-Optimizar {
    Titulo "4/7 Primera optimización con datos reales de Binance (10-20 min)"
    if (-not (SiNo "¿Hacerla ahora? Mejora la configuración inicial; se puede saltar.")) { return $true }
    $rc = Ejecutar-Bot @("optimize", "--source", "binance", "--limit", "5000", "--population", "12", "--generations", "5")
    if ($rc -ne 0) { Aviso "La optimización no terminó bien; el bot usará la configuración por defecto." }
    return $true
}

function Paso-Energia {
    if (SiNo "¿Evitar que el PC se suspenda mientras esté enchufado? (si se suspende, el bot se para)") {
        & powercfg /change standby-timeout-ac 0 | Out-Null
        Ok "Suspensión desactivada con el PC enchufado."
    }
}

function Paso-Arranque {
    Titulo "5/7 Arranque automático (papel, velas de 5 min)"
    if (-not (Test-Path $ModeFile)) { Set-Content -Path $ModeFile -Value "papel" -Encoding ASCII }
    $accion = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Starter`""
    $disparo = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
    $ajustes = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $TaskName -Action $accion -Trigger $disparo -Settings $ajustes `
        -Description "Bot de trading (freelm) en modo papel" -Force | Out-Null
    Start-ScheduledTask -TaskName $TaskName
    Ok "El bot arranca solo al iniciar sesión, y ya está en marcha. Registros: $LogDir"
    Paso-Energia
    return $true
}

function Paso-Accesos {
    Titulo "7/7 Accesos directos en el escritorio"
    $ws = New-Object -ComObject WScript.Shell
    $escritorio = [Environment]::GetFolderPath("Desktop")
    $bat = Join-Path $PSScriptRoot "Instalar-Bot.bat"
    $a = $ws.CreateShortcut((Join-Path $escritorio "Bot de trading - Panel.lnk"))
    $a.TargetPath = $bat; $a.WorkingDirectory = $PSScriptRoot; $a.Save()
    $b = $ws.CreateShortcut((Join-Path $escritorio "Bot de trading - Informe.lnk"))
    $b.TargetPath = "powershell.exe"
    $b.Arguments = "-NoProfile -ExecutionPolicy Bypass -NoExit -File `"$PSCommandPath`" -Accion informe"
    $b.WorkingDirectory = $PSScriptRoot; $b.Save()
    $c = $ws.CreateShortcut((Join-Path $escritorio "Bot de trading - Resultados.lnk"))
    $c.TargetPath = "powershell.exe"
    $c.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`" -Accion panel"
    $c.WorkingDirectory = $PSScriptRoot; $c.Save()
    Ok "Accesos 'Bot de trading - Panel', 'Informe' y 'Resultados' creados."
    return $true
}

function Instalacion-Completa {
    if (-not (Paso-Python)) { return }
    if (-not (Paso-Dependencias)) { return }
    Paso-Claves | Out-Null
    Paso-Optimizar | Out-Null
    Paso-Arranque | Out-Null
    Titulo "6/7 Prueba diaria del momentum y tarjeta de aciertos"
    Paso-Diario | Out-Null
    Paso-Accesos | Out-Null
    Titulo "Listo"
    Write-Host "  El bot funciona en PAPEL (dinero simulado). Revisa el informe cuando quieras (acceso 'Informe')."
    Write-Host "  Los resultados del momentum y cuánto aciertan las señales: acceso 'Resultados' (panel)."
    Write-Host "  Opcional: opción 17 (base de datos Supabase) y 18 (avisos por email)."
    Write-Host "  Dentro de 20 días, la opción 'Puerta del dinero real' te dirá si es apto. Si no lo es, no metas dinero."
}

function Ver-Informe {
    Titulo "Informe"
    Ejecutar-Bot @("report", "--plain") | Out-Null
    Titulo "Puerta del dinero real"
    Ejecutar-Bot @("gate") | Out-Null
    $hoy = Join-Path $LogDir ("bot-" + (Get-Date -Format "yyyyMMdd") + ".log")
    if (Test-Path $hoy) { Titulo "Últimas líneas del registro de hoy"; Get-Content $hoy -Tail 25 }
}

function Estado {
    Titulo "Estado"
    $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($t) { Ok ("Tarea automática: " + $t.State) } else { Aviso "Arranque automático no configurado." }
    $modo = "papel"; if (Test-Path $ModeFile) { $modo = (Get-Content $ModeFile -Raw).Trim() }
    Write-Host "  Modo: $modo"
    Write-Host "  Código: $AppDir"
    Write-Host "  Datos:  $DataDir"
}

function Parar-Procesos {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*trading_agents*bot.py*live*" -and $_.CommandLine -notlike "*--exchange testnet*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

function Detener {
    $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($t) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if (SiNo "¿Quitar también el arranque automático?" $false) {
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
            Ok "Arranque automático eliminado."
        } else { Ok "Bot detenido (volverá a arrancar al iniciar sesión)." }
    } else { Aviso "No hay tarea automática." }
    Parar-Procesos
}

function Dinero-Real {
    Titulo "Puerta del dinero real"
    $rc = Ejecutar-Bot @("gate")
    if ($rc -ne 0) { Aviso "NO APTO todavía. El bot sigue en papel."; return }
    Aviso "El bot ha superado la prueba de 20 días. Aun así, PUEDE PERDER DINERO."
    Write-Host "  Requisitos: claves del exchange guardadas (opción 3) con permiso de trading y SIN retirada."
    Write-Host "  Tope duro de capital: 100 (el bot nunca usa más aunque la cuenta tenga más)."
    $c = Read-Host "  Escribe CONFIRMO para pasar a dinero real"
    if ($c -ne "CONFIRMO") { Aviso "Cancelado."; return }
    Set-Content -Path $ModeFile -Value "real" -Encoding ASCII
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Start-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Ok "Modo REAL activado. Para volver a papel: opción 'Volver a papel'."
}

function Volver-Papel {
    Set-Content -Path $ModeFile -Value "papel" -Encoding ASCII
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Start-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Ok "Vuelto a modo papel."
}

function Actualizar {
    Titulo "Actualizar el bot"
    if ((Tiene "git") -and (Test-Path (Join-Path $AppDir ".git"))) {
        & git -C $AppDir pull --ff-only
    } else {
        Aviso "Descarga el ZIP actualizado desde GitHub y sustituye la carpeta (tus datos están en $DataDir y no se tocan)."
        Start-Process $RepoZip
        return
    }
    Paso-Dependencias | Out-Null
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Start-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
}

function Menu {
    while ($true) {
        Write-Host ""
        Write-Host "  BOT DE TRADING - Asistente para Windows" -ForegroundColor Cyan
        Write-Host "  ---------------------------------------"
        Write-Host "   1  Instalación completa (recomendado la primera vez)"
        Write-Host "   2  Ver informe y puerta del dinero real"
        Write-Host "   3  Cambiar claves (IA, Telegram, exchange)"
        Write-Host "   4  Iniciar ahora en esta ventana (ver qué hace, Ctrl+C para salir)"
        Write-Host "   5  Detener el bot"
        Write-Host "   6  Estado"
        Write-Host "   7  Optimizar ahora"
        Write-Host "   8  Actualizar el bot"
        Write-Host "   9  Pasar a dinero real (solo si la puerta dice APTO)"
        Write-Host "  10  Volver a papel"
        Write-Host "  11  Probar en la TESTNET de Binance (cuenta demo), paso a paso"
        Write-Host "  12  Parar el bot de testnet"
        Write-Host "  13  Informe de la testnet"
        Write-Host "  -- Momentum en papel y aciertos --"
        Write-Host "  14  Procesar hoy (papel + señales + panel)"
        Write-Host "  15  Ver el panel de resultados"
        Write-Host "  16  Tarjeta de aciertos (historia completa)"
        Write-Host "  17  Configurar base de datos Supabase (opcional)"
        Write-Host "  18  Configurar avisos por email (webhook) y probarlos"
        Write-Host "  19  Programar la prueba diaria (01:30)"
        Write-Host "   0  Salir"
        $op = Read-Host "  Elige"
        try {
            switch ($op) {
                "1"  { Instalacion-Completa }
                "2"  { Ver-Informe }
                "3"  { Paso-Claves | Out-Null; Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue; Start-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue }
                "4"  {
                    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
                    Parar-Procesos
                    Aviso "Arranque automático en pausa mientras miras; vuelve solo al reiniciar sesión (o opción 1)."
                    Ejecutar-Bot @("live", "--interval", "5m", "--exchange", "papel", "--llm") | Out-Null
                }
                "5"  { Detener }
                "6"  { Estado }
                "7"  { Ejecutar-Bot @("optimize", "--source", "binance", "--limit", "5000") | Out-Null }
                "8"  { Actualizar }
                "9"  { Dinero-Real }
                "10" { Volver-Papel }
                "11" { Probar-Testnet }
                "12" { Parar-Testnet; Ok "Bot de testnet parado." }
                "13" { Informe-Testnet }
                "14" { Momentum-Hoy }
                "15" { Ver-Panel }
                "16" { Tarjeta-Aciertos }
                "17" { Configurar-Supabase }
                "18" { Configurar-Avisos }
                "19" { Paso-Diario | Out-Null }
                "0"  { return }
                default { Aviso "Opción no válida." }
            }
        } catch {
            Fallo $_.Exception.Message
        }
    }
}

switch ($Accion) {
    "informe"  { Ver-Informe }
    "diario"   { Diario-Silencioso }
    "panel"    { Ver-Panel }
    "instalar" { Instalacion-Completa }
    default    { Menu }
}
