@echo off
rem Una lettura dell'inverter salvata su SQLite. Pensato per l'Utilità di
rem pianificazione di Windows (ogni minuto). I messaggi vanno in logs\raccolta.log.
cd /d "%~dp0"
".venv\Scripts\python.exe" -X utf8 raccolta.py --una-volta >nul 2>&1
