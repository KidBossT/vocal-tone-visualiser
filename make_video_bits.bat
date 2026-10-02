@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo  Please double-click setup.bat first - it installs what the visualiser needs.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -c "import imageio_ffmpeg" 2>nul || ".venv\Scripts\python.exe" -m pip install imageio-ffmpeg
set TAKES=
if exist "demo\takes\baseline.wav" set TAKES=--takes demo\takes
echo  Making the video clips in video\clips (about 8 minutes; nothing pops up or plays aloud)...
".venv\Scripts\python.exe" tools\record_clips.py %TAKES% %*
if errorlevel 1 ( pause & exit /b 1 )
".venv\Scripts\python.exe" tools\make_cards.py
echo.
echo  Done. The clips are in video\clips and the cards in video\cards.
pause
