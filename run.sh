#!/bin/bash
# WhisperFlow launcher — creates a virtualenv on first run, then starts the app.
set -euo pipefail
cd "$(dirname "$0")"

# Prefer 3.12 (best wheel coverage for mlx/numba), fall back gracefully.
PYTHON=""
for candidate in python3.12 python3.11 python3.13 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PYTHON="$candidate"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "No python3 found. Install it with:  brew install python@3.12" >&2
  exit 1
fi

# A half-created or wrong-arch .venv (interrupted first run) is unusable and
# would otherwise fail forever with a confusing error. Detect and rebuild it.
if [ -d .venv ] && ! ./.venv/bin/python -c "import sys" >/dev/null 2>&1; then
  echo "Existing environment looks broken — rebuilding it…"
  rm -rf .venv
fi

if [ ! -d .venv ]; then
  echo "First run: setting up Python environment (one time, ~1 min)…"
  "$PYTHON" -m venv .venv || { echo "Failed to create venv" >&2; exit 1; }
  ./.venv/bin/pip install --quiet --upgrade pip
fi

# Install/refresh dependencies if needed.
if ! ./.venv/bin/python -c "import mlx_whisper, sounddevice, AppKit, Quartz, AVFoundation" >/dev/null 2>&1; then
  echo "Installing dependencies (one time)…"
  ./.venv/bin/pip install --quiet -r requirements.txt
  # torch is skipped on purpose: only needed for converting OpenAI
  # checkpoints, which WhisperFlow never does. Saves ~600 MB.
  ./.venv/bin/pip install --quiet --no-deps mlx-whisper
fi

exec ./.venv/bin/python -m whisperflow "$@"
