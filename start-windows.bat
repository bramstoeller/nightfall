@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Create a virtual environment and install requirements.txt first. See README.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m nightfall %*
if errorlevel 1 pause
