@echo off
rem Asset Forge launcher: starts the app and opens it in your browser.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run: setting up...
  uv venv --python 3.12 .venv || goto :fail
  uv pip install --python .venv\Scripts\python.exe -e . || goto :fail
)
start "" /b cmd /c "timeout /t 3 >nul & start http://127.0.0.1:7860"
".venv\Scripts\python.exe" -m asset_forge
goto :eof
:fail
echo Setup failed. Make sure "uv" is installed, then double-click this file again.
pause
