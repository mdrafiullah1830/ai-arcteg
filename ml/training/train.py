"""Offline ML training entrypoint.

Trains power/thermal/efficiency models against whatever telemetry currently
exists in the database and writes joblib artifacts to ml/models/.

Usage (from the backend directory so `app` imports resolve):
    cd backend
    python ../ml/training/train.py            # train from DB
    python ../ml/training/train.py --seed 500 # simulate N ticks first (dev)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from anywhere: put backend/ on sys.path.
BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _seed_rows(count: int) -> None:
    """Run simulation ticks to populate telemetry so training has data."""
    from app.core.database import init_db
    from app.simulation.engine import engine

    init_db()
    engine.running = True
    for i in range(count):
        engine.tick()
        if i % 100 == 0:
            print(f"  seeded {i + 1}/{count}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Train ARCTEG ML models")
    parser.add_argument(
        "--seed", type=int, default=0,
        help="Backfill N simulation ticks first (dev convenience)",
    )
    args = parser.parse_args()

    if args.seed:
        print(f"Seeding {args.seed} telemetry rows...", file=sys.stderr)
        _seed_rows(args.seed)

    from app.core.database import init_db
    from app.ml import service as ml

    init_db()
    result = ml.train()
    print(json.dumps(result, indent=2))

    if result.get("status") == "insufficient_data":
        print(
            f"\nNeed at least 50 rows, have {result.get('data_rows', 0)}. "
            "Run with --seed 500 or start the API + simulation first.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
