#!/bin/bash
# Tone visualiser for macOS. In Terminal, from this folder:  bash run.command
# (add options after it, e.g.  bash run.command --file demo/wavs/sample_zira.wav)
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "Please run setup.command first:  bash setup.command"
  exit 1
fi
exec .venv/bin/python -m tonevis "$@"
