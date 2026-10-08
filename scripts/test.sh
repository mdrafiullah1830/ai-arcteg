#!/usr/bin/env bash
# Run the backend test suite.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/backend/.venv"

if [[ ! -d "$VENV" ]]; then
  echo "virtualenv missing — run scripts/dev.sh once first" >&2
  exit 1
fi

cd "$ROOT/backend"
exec "$VENV/bin/python" -m pytest tests/ -q "$@"
