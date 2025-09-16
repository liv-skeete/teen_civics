#!/usr/bin/env bash
# TeenCivics unified dev runner (fixed)
# Usage:
#   ./scripts/dev.sh
#   PORT=5050 TEENCIVICS_VENV="$HOME/.venvs/teencivics" ./scripts/dev.sh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." >/dev/null 2>&1 && pwd)"
cd "$PROJECT_DIR"

# Use an external venv path by default to avoid iCloud/Dropbox sync issues with local folders
DEFAULT_VENV="${HOME}/.venvs/teencivics"
VENV_DIR="${TEENCIVICS_VENV:-$DEFAULT_VENV}"

PY="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"
PORT="${PORT:-5050}"

log() { echo "[dev] $*"; }

trap 'echo "[dev] ERROR on line $LINENO"; exit 1' ERR

log "Ensuring virtualenv at $VENV_DIR ..."
# Create parent dir for external venvs
mkdir -p "$(dirname "$VENV_DIR")"
if [[ ! -x "$PY" ]]; then
  python3 -m venv "$VENV_DIR"
fi

# Helpful symlink for tools that expect .venv under the project
if [[ ! -e ".venv" ]]; then
  ln -s "$VENV_DIR" .venv 2>/dev/null || true
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
export PYTHONUNBUFFERED=1

log "Upgrading pip (one-time or quick) ..."
"$PY" -m pip install --upgrade pip >/dev/null

log "Installing dependencies from requirements.txt ..."
"$PIP" install -r requirements.txt

log "Freeing port $PORT if occupied ..."
if command -v lsof >/dev/null; then
  lsof -ti :"$PORT" | xargs kill -9 2>/dev/null || true
fi
# Also stop any lingering python app.py processes
pkill -f "python app.py" 2>/dev/null || true

log "Starting TeenCivics on http://localhost:$PORT ..."
export PORT
exec "$PY" app.py