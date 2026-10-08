#!/usr/bin/env bash
# Start the ARCTEG backend in dev mode (auto-reload, SQLite, sim autostart).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
VENV="$BACKEND/.venv"

if [[ ! -d "$VENV" ]]; then
  echo "Creating virtualenv..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade pip
  "$VENV/bin/pip" install -r "$BACKEND/requirements.txt"
fi

if [[ ! -f "$ROOT/.env" ]]; then
  echo "Creating .env from .env.example"
  cp "$ROOT/.env.example" "$ROOT/.env"
fi

cd "$BACKEND"
exec "$VENV/bin/uvicorn" app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --reload
