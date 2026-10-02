@echo off
setlocal
if "%~1"=="" (
  echo  To use this, drag a .wav file onto play_file.bat.
  echo  For example, drag demo\wavs\sample_zira.wav onto it.
  pause
  exit /b 1
)
set "WAV=%~f1"
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo  Please double-click setup.bat first - it installs what the visualiser needs.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m tonevis --file "%WAV%"
if errorlevel 1 pause
