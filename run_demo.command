#!/bin/bash
# The demo comparison for macOS. In Terminal, from this folder:  bash run_demo.command
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "Please run setup.command first:  bash setup.command"
  exit 1
fi
exec .venv/bin/python demo/run_demo.py "$@"
