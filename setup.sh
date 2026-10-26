#!/usr/bin/env bash
# Karaoke Style Studio — one-time environment setup.
set -euo pipefail
cd "$(dirname "$0")"
say() { printf '\n==> %s\n' "$1"; }

OS="$(uname -s)"
PKG=""
if [ "$OS" = "Darwin" ]; then
  if command -v brew >/dev/null 2>&1; then PKG="brew"; else
    say "Installing Homebrew (required for ffmpeg)..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    PKG="brew"
  fi
elif [ "$OS" = "Linux" ]; then
  if command -v apt-get >/dev/null 2>&1; then PKG="apt"
  elif command -v dnf >/dev/null 2>&1; then PKG="dnf"
  elif command -v yum >/dev/null 2>&1; then PKG="yum"
  else say "No supported package manager found. Install python3 and ffmpeg manually, then re-run."; PKG="none"
  fi
else
  say "Unsupported OS '$OS'. Install python3 (3.10+) and ffmpeg manually, then re-run."; PKG="none"
fi
say "Detected OS: $OS (package manager: $PKG)"

say "Checking Python 3..."
if command -v python3 >/dev/null 2>&1; then
  PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  PY_MAJOR="${PY_VER%%.*}"; PY_MINOR="${PY_VER##*.}"
  if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    say "Python $PY_VER found but 3.10+ is required."; NEED_PYTHON=1
  else say "Python $PY_VER OK."; NEED_PYTHON=0
  fi
else say "python3 not found."; NEED_PYTHON=1
fi

if [ "${NEED_PYTHON:-0}" = "1" ]; then
  case "$PKG" in
    brew) brew install python@3.12 ;;
    apt)  sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip ;;
    dnf)  sudo dnf install -y python3 python3-pip ;;
    yum)  sudo yum install -y python3 python3-pip ;;
    *)    say "Install Python 3.10+ from https://www.python.org/downloads/ then re-run."; exit 1 ;;
  esac
fi

say "Checking ffmpeg..."
if command -v ffmpeg >/dev/null 2>&1; then
  say "ffmpeg found: $(command -v ffmpeg)"
else
  say "Installing ffmpeg..."
  case "$PKG" in
    brew) brew install ffmpeg ;;
    apt)  sudo apt-get update && sudo apt-get install -y ffmpeg ;;
    dnf)  sudo dnf install -y ffmpeg ;;
    yum)  sudo yum install -y ffmpeg ;;
    *)    say "Install ffmpeg from https://ffmpeg.org/download.html then re-run."; exit 1 ;;
  esac
fi

say "Creating virtualenv (.venv)..."
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip --quiet

say "Installing Python dependencies (downloads torch — can take a few minutes)..."
.venv/bin/python -m pip install -r requirements.txt

chmod +x run.sh

say "Setup complete."
echo
echo "Start the app with:"
echo "    ./run.sh"
echo
echo "Then open http://127.0.0.1:8989 in your browser."
