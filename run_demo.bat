@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo  Please double-click setup.bat first - it installs what the visualiser needs.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" demo\run_demo.py %*
if errorlevel 1 pause
