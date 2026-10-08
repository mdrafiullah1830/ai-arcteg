"""Research experiments: start/stop scenario runs, compare summaries."""
from __future__ import annotations

import datetime as dt
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_min_role
from app.models.experiment import SCENARIOS, Experiment
from app.models.user import User
from app.schemas.common import OkResponse, Paged
from app.schemas.intel import ExperimentCreate, ExperimentOut
from app.services import queries
from app.simulation.engine import engine

router = APIRouter(prefix="/experiments", tags=["experiments"])


def _to_out(row: Experiment) -> ExperimentOut:
    return ExperimentOut(
        id=row.id,
        experiment_uid=row.experiment_uid,
        name=row.name,
        scenario=row.scenario,
        data_source=row.data_source,
        config=row.config,
        summary=row.summary,
        started_at=row.started_at,
        ended_at=row.ended_at,
        status=row.status,
    )


@router.get("", response_model=Paged[ExperimentOut])
def list_experiments(
    limit: int = Query(50, ge=1, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
) -> Paged[ExperimentOut]:
    total = db.query(Experiment).count()
    rows = (
        db.query(Experiment)
        .order_by(Experiment.started_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return Paged[ExperimentOut](
        items=[_to_out(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get("/scenarios")
def scenarios() -> dict:
    return {"scenarios": [{"id": k, "label": v} for k, v in SCENARIOS.items()]}


@router.post("", response_model=ExperimentOut, status_code=status.HTTP_201_CREATED)
def create_experiment(
    payload: ExperimentCreate,
    _: User = Depends(require_min_role("ENGINEER")),
    db: Session = Depends(get_db),
) -> ExperimentOut:
    if payload.scenario not in SCENARIOS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"scenario must be one of {sorted(SCENARIOS)}")
    # Switch the digital twin to the requested scenario for this run.
    engine.set_scenario(payload.scenario)
    if not engine.running:
        engine.start()
    row = Experiment(
        experiment_uid=uuid.uuid4().hex[:16],
        name=payload.name,
        scenario=payload.scenario,
        device_id=payload.device_id,
        data_source="SIMULATED_DATA",
        config_json=json.dumps(payload.config),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.post("/{experiment_id}/stop", response_model=ExperimentOut)
def stop_experiment(
    experiment_id: int,
    _: User = Depends(require_min_role("ENGINEER")),
    db: Session = Depends(get_db),
) -> ExperimentOut:
    row = db.get(Experiment, experiment_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Experiment not found")
    if row.status != "RUNNING":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Experiment already {row.status}")

    summary = queries.energy_summary(db)
    last = queries.latest_sample(db) or {}
    row.ended_at = dt.datetime.now(dt.timezone.utc)
    row.status = "COMPLETED"
    row.summary_json = json.dumps(
        {
            "energy_wh": summary["today_energy_wh"],
            "avg_power_w": summary["avg_power_w"],
            "final_delta_t": last.get("delta_t", 0.0),
            "final_hot_c": last.get("hot_temperature", 0.0),
            "final_efficiency_pct": last.get("system_efficiency", 0.0),
            "ticks": engine.ticks,
        }
    )
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.get("/{experiment_id}", response_model=ExperimentOut)
def get_experiment(experiment_id: int, db: Session = Depends(get_db)) -> ExperimentOut:
    row = db.get(Experiment, experiment_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Experiment not found")
    return _to_out(row)


@router.delete("/{experiment_id}", response_model=OkResponse)
def delete_experiment(
    experiment_id: int,
    _: User = Depends(require_min_role("ADMIN")),
    db: Session = Depends(get_db),
) -> OkResponse:
    row = db.get(Experiment, experiment_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Experiment not found")
    db.delete(row)
    db.commit()
    return OkResponse(detail="Experiment deleted")
