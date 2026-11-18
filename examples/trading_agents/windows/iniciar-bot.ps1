#requires -version 5.1
<#
  Arranca el bot en segundo plano (lo usa la tarea programada "FreelmTradingBot").
  Lee el modo (papel/real) de %USERPROFILE%\freelm-bot-datos\modo.txt y las claves de bot.env.
  Si el bot se cae (sin red, error), espera 30 s y vuelve a arrancar. Registro diario en ...\registros.
#>
param([string]$Modo = "")   # "" = leer modo.txt (papel/real); "testnet" = cuenta demo de Binance
$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$AppDir   = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$Bot      = Join-Path $AppDir "examples\trading_agents\bot.py"
$Py       = Join-Path $AppDir ".venv\Scripts\python.exe"
$DataDir  = Join-Path $env:USERPROFILE "freelm-bot-datos"
$EnvFile  = Join-Path $DataDir "bot.env"
$ModeFile = Join-Path $DataDir "modo.txt"
$LogDir   = Join-Path $DataDir "registros"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$env:FREELM_TRADING_DIR = $DataDir
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"   # que el registro se escriba al momento
if (Test-Path $EnvFile) {
    foreach ($linea in Get-Content $EnvFile) {
        $l = $linea.Trim()
        if ($l -eq "" -or $l.StartsWith("#") -or -not $l.Contains("=")) { continue }
        $i = $l.IndexOf("=")
        $v = $l.Substring($i + 1).Trim()
        if ($v -ne "") { Set-Item -Path ("Env:" + $l.Substring(0, $i).Trim()) -Value $v }
    }
}

$prefijo = "bot-"
if ($Modo -eq "testnet") {
    # claves de testnet en lugar de las reales, y memoria/cartera separadas de las del modo papel
    $env:FREELM_EXCHANGE_KEY = $env:FREELM_TESTNET_KEY
    $env:FREELM_EXCHANGE_SECRET = $env:FREELM_TESTNET_SECRET
    $TestnetDir = Join-Path $DataDir "testnet"
    New-Item -ItemType Directory -Force -Path $TestnetDir | Out-Null
    $env:FREELM_TRADING_DIR = $TestnetDir
    $prefijo = "testnet-"
}

while ($true) {
    $modo = "papel"
    if ($Modo -eq "testnet") { $modo = "testnet" }
    elseif (Test-Path $ModeFile) { $modo = (Get-Content $ModeFile -Raw).Trim() }
    $argumentos = @($Bot, "live", "--interval", "5m", "--exchange", $modo, "--auto-optimize",
                    "--optimize-limit", "8000", "--llm")
    if ($modo -eq "testnet") { $argumentos += @("--entry-mode", "limit") }   # probar también las órdenes límite
    if ($modo -eq "real") { $argumentos += @("--confirm-real-money", "--max-capital", "100") }
    $log = Join-Path $LogDir ($prefijo + (Get-Date -Format "yyyyMMdd") + ".log")
    # todo el registro en UTF-8 (en PowerShell 5.1, «>>» escribiría UTF-16 y mezclaría codificaciones)
    Add-Content -Path $log -Encoding UTF8 -Value ("==== " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + " arranque en modo " + $modo)
    & $Py @argumentos 2>&1 | ForEach-Object { "$_" } | Out-File -FilePath $log -Append -Encoding utf8
    $codigo = $LASTEXITCODE
    Add-Content -Path $log -Encoding UTF8 -Value ("==== salida con código " + $codigo + "; reinicio en 30 s")
    if ($codigo -eq 2 -and $Modo -ne "testnet") {
        # 2 = dinero real bloqueado por la puerta o falta de confirmación: volver a papel
        Set-Content -Path $ModeFile -Value "papel" -Encoding ASCII
    }
    Start-Sleep -Seconds 30
}
