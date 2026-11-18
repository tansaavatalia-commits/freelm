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
    6. crea accesos directos en el escritorio.
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

function Ejecutar-Bot([string[]]$argumentos) {
    if (-not (Test-Path $Py)) { Fallo "El bot no está instalado todavía (opción 1 del menú)."; return 1 }
    Cargar-Entorno
    & $Py $Bot @argumentos | Out-Host   # a la pantalla, no al valor de retorno
    return $LASTEXITCODE
}

# ---------------------------------------------------------------- pasos
function Paso-Python {
    Titulo "1/6 Python"
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
    Titulo "2/6 Entorno e instalación del bot"
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
    Titulo "3/6 Claves (todas opcionales)"
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
    Titulo "4/6 Primera optimización con datos reales de Binance (10-20 min)"
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
    Titulo "5/6 Arranque automático (papel, velas de 5 min)"
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
    Titulo "6/6 Accesos directos en el escritorio"
    $ws = New-Object -ComObject WScript.Shell
    $escritorio = [Environment]::GetFolderPath("Desktop")
    $bat = Join-Path $PSScriptRoot "Instalar-Bot.bat"
    $a = $ws.CreateShortcut((Join-Path $escritorio "Bot de trading - Panel.lnk"))
    $a.TargetPath = $bat; $a.WorkingDirectory = $PSScriptRoot; $a.Save()
    $b = $ws.CreateShortcut((Join-Path $escritorio "Bot de trading - Informe.lnk"))
    $b.TargetPath = "powershell.exe"
    $b.Arguments = "-NoProfile -ExecutionPolicy Bypass -NoExit -File `"$PSCommandPath`" -Accion informe"
    $b.WorkingDirectory = $PSScriptRoot; $b.Save()
    Ok "Accesos 'Bot de trading - Panel' e 'Informe' creados."
    return $true
}

function Instalacion-Completa {
    if (-not (Paso-Python)) { return }
    if (-not (Paso-Dependencias)) { return }
    Paso-Claves | Out-Null
    Paso-Optimizar | Out-Null
    Paso-Arranque | Out-Null
    Paso-Accesos | Out-Null
    Titulo "Listo"
    Write-Host "  El bot funciona en PAPEL (dinero simulado). Revisa el informe cuando quieras (acceso 'Informe')."
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
        Where-Object { $_.CommandLine -like "*trading_agents*bot.py*live*" } |
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
    "instalar" { Instalacion-Completa }
    default    { Menu }
}
