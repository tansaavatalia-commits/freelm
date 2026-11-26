# Saves the owner's free OpenRouter key for GENESIS, typed by the owner in this window.
# The key is read hidden, never printed, never written to any file: it is stored only as the Windows user
# environment variable OPENROUTER_API_KEY (the same as `setx`), where freelm reads it.
$ErrorActionPreference = 'Stop'
Write-Host ''
Write-Host '  GENESIS - chiave gratuita del motore online (OpenRouter)' -ForegroundColor Cyan
Write-Host ''
Write-Host '  1. Apri https://openrouter.ai/keys, entra e premi "Create Key" (gratis: NON comprare crediti).'
Write-Host '  2. Copia la chiave (inizia con sk-or-) e incollala qui sotto con il tasto destro del mouse o Ctrl+V.'
Write-Host '     Mentre incolli non vedrai nulla: e'' normale, la chiave resta nascosta.'
Write-Host ''
$secure = Read-Host '  Chiave' -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $key = ([Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)).Trim()
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
}
if (-not $key) {
    Write-Host '  Nessuna chiave inserita: non ho cambiato nulla.' -ForegroundColor Yellow
} elseif (-not $key.StartsWith('sk-or-') -or $key.Length -lt 20 -or $key -match '\s') {
    Write-Host '  Non sembra una chiave OpenRouter (deve iniziare con sk-or-): non ho cambiato nulla.' -ForegroundColor Yellow
} else {
    [Environment]::SetEnvironmentVariable('OPENROUTER_API_KEY', $key, 'User')
    $masked = $key.Substring(0, 6) + '...' + $key.Substring($key.Length - 4)
    Write-Host ''
    Write-Host "  Chiave salvata ($masked)." -ForegroundColor Green
    Write-Host '  Ora chiudi la finestra nera di GENESIS (se e'' aperta) e riaprilo con Avvia-GENESIS.bat.'
}
$key = $null
Write-Host ''
Read-Host '  Premi Invio per chiudere' | Out-Null
