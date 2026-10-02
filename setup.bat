@echo off
setlocal
cd /d "%~dp0"
echo.
echo  Tone visualiser - one-time setup
echo  ================================
echo  This downloads about 140 MB of Python packages into a ".venv" folder here.
echo  It needs internet and takes a few minutes. Nothing is installed anywhere else.
echo.

set "PY="
for %%V in (3.12 3.13 3.11 3.14 3.10) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>nul && set "PY=py -%%V"
  )
)
if not defined PY (
  python -c "import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 14) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo  Could not find Python 3.10 to 3.14 on this computer.
  echo  Install Python 3.12 from https://www.python.org/downloads/ and tick
  echo  "Add python.exe to PATH" on the first screen of the installer.
  echo  Then double-click setup.bat again.
  echo.
  pause
  exit /b 1
)
echo  Using Python: %PY%

if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv
if not exist ".venv\Scripts\python.exe" (
  echo  Could not create the .venv folder. See the messages above.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo.
  echo  Installing the packages failed. Check the internet connection, read the
  echo  messages above, and double-click setup.bat to try again.
  pause
  exit /b 1
)

echo.
echo  Setup finished. Double-click run.bat to start the visualiser.
echo.
pause
