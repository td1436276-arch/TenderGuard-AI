@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo TenderGuard has not been installed yet.
    echo Run install_tenderguard.bat first.
    pause
    exit /b 1
)

echo Starting TenderGuard AI...
echo Keep this window open while using the application.
".venv\Scripts\python.exe" -m streamlit run app.py

if errorlevel 1 (
    echo.
    echo TenderGuard stopped with an error. Copy the error message and ask for help.
    pause
)
