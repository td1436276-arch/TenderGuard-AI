@echo off
setlocal
cd /d "%~dp0"

echo Creating the TenderGuard Python environment...
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto :error
)

echo Installing required packages...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo.
echo TenderGuard installation completed successfully.
echo You can now double-click run_tenderguard.bat.
pause
exit /b 0

:error
echo.
echo Installation failed. Copy the complete error message and ask for help.
pause
exit /b 1
