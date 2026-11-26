@echo off
rem Avvia GENESIS con un doppio clic: apre l'interfaccia nel browser (http://127.0.0.1:8765).
rem Per spegnerlo chiudi questa finestra (oppure premi Ctrl+C).
chcp 65001 >nul
cd /d "%~dp0"
set "PYEXE=%LOCALAPPDATA%\Python\pythoncore-3.15-64\python.exe"
if exist "%PYEXE%" (
  "%PYEXE%" -m genesis serve
) else (
  py -3 -m genesis serve
)
if errorlevel 1 pause
