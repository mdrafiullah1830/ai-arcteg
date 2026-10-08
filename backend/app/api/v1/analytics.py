"""Analytics: descriptive statistics, correlations, scenario comparison."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import rate_limit
from app.schemas.intel import CompareResponse, CorrelationResponse, StatsResponse
from app.services import queries
from app.simulation.engine import SCENARIOS

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/stats", response_model=StatsResponse)
def stats(
    parameter: str = Query("total_power"),
    hours: float = Query(24.0, gt=0, le=24 * 30),
    _: None = Depends(rate_limit),
    db: Session = Depends(get_db),
) -> StatsResponse:
    return StatsResponse(**queries.stats(db, parameter=parameter, hours=hours))


@router.get("/correlation", response_model=CorrelationResponse)
def correlation(
    a: str = Query("irradiance"),
    b: str = Query("pv_power"),
    hours: float = Query(24.0, gt=0, le=24 * 30),
    _: None = Depends(rate_limit),
    db: Session = Depends(get_db),
) -> CorrelationResponse:
    data = queries.correlation(db, a, b, hours=hours)
    return CorrelationResponse(**data)


@router.get("/compare", response_model=CompareResponse)
def compare_scenarios(
    hours: float = Query(24.0, gt=0, le=24 * 30),
    _: None = Depends(rate_limit),
    db: Session = Depends(get_db),
) -> CompareResponse:
    """Aggregate energy/thermal metrics per scenario label stored on samples.

    Scenario is not a telemetry column, so we reconstruct the comparison from
    the research runs recorded in experiments (or fall back to a physics-based
    estimate of what each scenario would deliver under current conditions).
    """
    from app.models.experiment import Experiment

    rows = db.query(Experiment).order_by(Experiment.started_at.desc()).limit(50).all()
    by_scenario: dict[str, dict] = {}
    for row in rows:
        summary = row.summary or {}
        if not summary:
            continue
        slot = by_scenario.setdefault(
            row.scenario,
            {"scenario": row.scenario, "label": SCENARIOS.get(row.scenario, {}).get("label", row.scenario), "runs": 0, "energy_wh": 0.0, "avg_power_w": 0.0},
        )
        slot["runs"] += 1
        slot["energy_wh"] += float(summary.get("energy_wh", 0.0))
        slot["avg_power_w"] += float(summary.get("avg_power_w", 0.0))

    scenarios = []
    for code, meta in SCENARIOS.items():
        stats_row = by_scenario.get(code)
        if stats_row and stats_row["runs"]:
            stats_row["energy_wh"] = round(stats_row["energy_wh"] / stats_row["runs"], 3)
            stats_row["avg_power_w"] = round(stats_row["avg_power_w"] / stats_row["runs"], 3)
            scenarios.append(stats_row)
        else:
            scenarios.append(
                {
                    "scenario": code,
                    "label": meta["label"],
                    "runs": 0,
                    "energy_wh": None,
                    "avg_power_w": None,
                    "note": "No completed run yet — create an experiment to compare.",
                }
            )
    return CompareResponse(
        scenarios=scenarios,
        generated_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        data_label="EXPERIMENT_SUMMARY",
    )
