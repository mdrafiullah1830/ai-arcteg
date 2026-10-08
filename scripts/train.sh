#!/usr/bin/env bash
# Train ML models (seeds 600 simulated ticks first if the DB is empty).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/backend/.venv"

if [[ ! -d "$VENV" ]]; then
  echo "virtualenv missing — run scripts/dev.sh once first" >&2
  exit 1
fi

cd "$ROOT/backend"
exec "$VENV/bin/python" "$ROOT/ml/training/train.py" "$@"
