#!/bin/bash
# Clip Radar for macOS: set up to run from source.
#   scripts/install.sh      a Python environment in .venv, the packages, the laughter detector,
#                           and FFmpeg, yt-dlp and TwitchDownloaderCLI in tools/
# Then start it with scripts/run.sh.
set -euo pipefail
cd "$(dirname "$0")/.."

echo
echo "  Clip Radar setup"
echo "  ----------------"
echo

# ---------- Python 3.10 to 3.13 (the caption library has no 3.14 build yet) ----------
PY=""
for v in 3.12 3.11 3.13 3.10; do
  for c in "python$v" "/opt/homebrew/bin/python$v" "/usr/local/bin/python$v" \
           "/Library/Frameworks/Python.framework/Versions/$v/bin/python$v"; do
    if command -v "$c" >/dev/null 2>&1; then PY="$c"; break 2; fi
  done
done
if [ -z "$PY" ] && command -v python3 >/dev/null 2>&1 && \
   python3 -c 'import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,13) else 1)'; then
  PY=python3
fi
if [ -z "$PY" ]; then
  if command -v brew >/dev/null 2>&1; then
    echo "  Python 3.12 is needed. Installing it with Homebrew..."
    brew install python@3.12
    PY="$(brew --prefix)/bin/python3.12"
  else
    echo "  Python 3.12 is needed. Get it from https://www.python.org/downloads/macos/"
    echo "  (or install Homebrew from https://brew.sh and run this again)."
    exit 1
  fi
fi
echo "  [1/5] Python $("$PY" -c 'import platform; print(platform.python_version())') found."

# ---------- virtual environment ----------
if [ -x .venv/bin/python ] && ! .venv/bin/python -c "import sys" >/dev/null 2>&1; then rm -rf .venv; fi
[ -x .venv/bin/python ] || "$PY" -m venv .venv
VPY=.venv/bin/python

echo "  [2/5] Installing packages..."
"$VPY" -m pip install --upgrade pip --disable-pip-version-check -q
"$VPY" -m pip install -U --disable-pip-version-check -q numpy "yt-dlp[default]" pywebview

echo "  [3/5] Installing captions (Whisper). First time takes a few minutes..."
"$VPY" -m pip install -U --disable-pip-version-check -q faster-whisper || \
  echo "  Captions couldn't be installed. Clip Radar will still work, just without captions."
"$VPY" src/audio_events.py --download src/models >/dev/null 2>&1 || \
  echo "  The laughter detector didn't download. You can get it later in Settings."

# ---------- FFmpeg, yt-dlp, TwitchDownloaderCLI ----------
mkdir -p tools
NEED=""
if [ ! -x tools/ffmpeg ] || [ ! -x tools/ffprobe ]; then
  if command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; then
    echo "  [4/5] FFmpeg found ($(command -v ffmpeg))."
  else
    NEED="$NEED ffmpeg"
  fi
else
  echo "  [4/5] FFmpeg found."
fi
[ -x tools/TwitchDownloaderCLI ] || NEED="$NEED twitchdownloader"
NEED="$NEED ytdlp"
echo "  [5/5] Getting:$NEED"
"$VPY" src/tools_setup.py --dest tools $NEED || \
  echo "  Some tools didn't download. Clip Radar offers to download them again when it starts."

echo
echo "  Setup finished. Start Clip Radar with:  scripts/run.sh"
echo
