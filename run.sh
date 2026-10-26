#!/usr/bin/env bash
# Karaoke Style Studio — start the app.
# Run ./setup.sh once first.
set -e
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo "No virtualenv found. Run ./setup.sh first (one-time setup)."
  exit 1
fi

if ! .venv/bin/python -c "import demucs" 2>/dev/null; then
  echo "Note: Demucs not installed — the Studio engine will be unavailable."
  echo "Re-run ./setup.sh, or the Fast (ffmpeg) engine works without it."
fi

exec .venv/bin/python server.py
