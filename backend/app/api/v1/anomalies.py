"""Anomaly/alert endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import rate_limit, require_min_role
from app.models.anomaly import Anomaly
from app.models.user import User
from app.schemas.common import OkResponse, Paged
from app.schemas.intel import AnomalyOut, AnomalySummary, AnomalyUpdate
from app.services import queries

router = APIRouter(prefix="/anomalies", tags=["anomalies"])

VALID_STATUSES = {"OPEN", "ACK", "RESOLVED"}


def _to_out(row: Anomaly) -> AnomalyOut:
    return AnomalyOut(
        id=row.id,
        timestamp=row.timestamp.isoformat(),
        device_id=row.device_id,
        parameter=row.parameter,
        observed_value=row.observed_value,
        expected_value=row.expected_value,
        severity=row.severity,
        anomaly_score=row.anomaly_score,
        status=row.status,
        detector=row.detector,
        message=row.message,
    )


@router.get("", response_model=Paged[AnomalyOut])
def list_anomalies(
    status_filter: str | None = Query(None, alias="status"),
    severity: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = 0,
    _: None = Depends(rate_limit),
    db: Session = Depends(get_db),
) -> Paged[AnomalyOut]:
    q = db.query(Anomaly)
    if status_filter:
        q = q.filter(Anomaly.status == status_filter)
    if severity:
        q = q.filter(Anomaly.severity == severity)
    total = q.count()
    rows = q.order_by(Anomaly.timestamp.desc()).offset(offset).limit(limit).all()
    return Paged[AnomalyOut](
        items=[_to_out(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get("/summary", response_model=AnomalySummary)
def summary(_: None = Depends(rate_limit), db: Session = Depends(get_db)) -> AnomalySummary:
    data = queries.anomaly_summary(db)
    return AnomalySummary(
        open=data["open"],
        warning=data["warning"],
        critical=data["critical"],
        total=data["total"],
        recent=[_to_out(r) for r in data["recent"]],
    )


@router.patch("/{anomaly_id}", response_model=AnomalyOut)
def update_anomaly(
    anomaly_id: int,
    payload: AnomalyUpdate,
    _: User = Depends(require_min_role("ENGINEER")),
    db: Session = Depends(get_db),
) -> AnomalyOut:
    if payload.status not in VALID_STATUSES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"status must be one of {sorted(VALID_STATUSES)}")
    row = db.get(Anomaly, anomaly_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Anomaly not found")
    row.status = payload.status
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.delete("", response_model=OkResponse)
def clear_resolved(
    _: User = Depends(require_min_role("ADMIN")),
    db: Session = Depends(get_db),
) -> OkResponse:
    deleted = db.query(Anomaly).filter(Anomaly.status == "RESOLVED").delete()
    db.commit()
    return OkResponse(detail=f"Deleted {deleted} resolved anomalies")
