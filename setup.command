#!/bin/bash
# Tone visualiser - one-time setup for macOS.
# In Terminal, from this folder:  bash setup.command
cd "$(dirname "$0")" || exit 1
echo "Tone visualiser - one-time setup (downloads about 140 MB into a .venv folder here)"

PY=""
for v in 3.12 3.13 3.11 3.14 3.10; do
  if command -v "python$v" >/dev/null 2>&1; then PY="python$v"; break; fi
done
if [ -z "$PY" ] && command -v python3 >/dev/null 2>&1; then
  if python3 -c 'import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 14) else 1)'; then
    PY=python3
  fi
fi
if [ -z "$PY" ]; then
  echo "Could not find Python 3.10 to 3.14. Install Python 3.12 from"
  echo "https://www.python.org/downloads/ and run this again."
  read -r -p "Press Return to close. " _
  exit 1
fi
echo "Using $PY"

[ -x .venv/bin/python ] || "$PY" -m venv .venv
if .venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt; then
  echo "Setup finished. Start the visualiser with:  bash run.command"
  status=0
else
  echo "Installing the packages failed - see the messages above."
  status=1
fi
read -r -p "Press Return to close. " _
exit $status
