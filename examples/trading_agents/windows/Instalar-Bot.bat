@echo off
rem Asistente de instalacion del bot de trading (doble clic)
chcp 65001 >nul
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0asistente.ps1" %*
echo.
pause
