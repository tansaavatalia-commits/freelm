@echo off
rem Doppio clic: salva la chiave gratuita OpenRouter per il motore online di GENESIS.
rem La chiave si scrive solo nella finestra che si apre; non viene mostrata ne' salvata in file.
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0scripts\imposta-chiave-online.ps1"
