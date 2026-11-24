@echo off
rem Avvia LocalChords. Con --console resta nella finestra del terminale e mostra i log.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo LocalChords non e' installato. Esegui prima:
    echo     powershell -ExecutionPolicy Bypass -File setup.ps1
    pause
    exit /b 1
)

if /i "%~1"=="--console" goto console
start "" ".venv\Scripts\pythonw.exe" -m app %*
exit /b 0

:console
shift
".venv\Scripts\python.exe" -m app %1 %2 %3 %4
exit /b %errorlevel%
