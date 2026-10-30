#!/bin/bash
# Clip Radar for macOS, from source: in its own window (WebKit), or in your browser with --browser.
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  echo
  echo "  Clip Radar isn't set up yet. Run scripts/install.sh first."
  echo
  exit 1
fi
export PYTHONUTF8=1
exec .venv/bin/python src/app.py "$@"
