"""AI/ML endpoints: insights, training, model metrics, stored predictions."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import rate_limit, require_min_role
from app.ml import service as ml
from app.models.prediction import Prediction
from app.models.user import User
from app.schemas.common import OkResponse, Paged
from app.schemas.intel import AiInsights, ModelMetrics, PredictionOut, TrainResponse
from app.services import queries

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/insights", response_model=AiInsights)
def insights(_: None = Depends(rate_limit), db: Session = Depends(get_db)) -> AiInsights:
    sample = queries.latest_sample(db)
    pred = ml.predict_latest()
    return AiInsights(**ml.ai_insights(sample, pred))


@router.post("/train", response_model=TrainResponse)
def train(
    _: User = Depends(require_min_role("ENGINEER")),
    db: Session = Depends(get_db),
) -> TrainResponse:
    # Ensure at least a little history exists before fitting.
    if queries.latest_sample(db) is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "No telemetry to train on — start the simulation or ingest hardware data first",
        )
    result = ml.train()
    return TrainResponse(**result)


@router.get("/model", response_model=ModelMetrics)
def model_metrics() -> ModelMetrics:
    return ModelMetrics(**ml.model_status())


@router.post("/predict", response_model=PredictionOut)
def predict_now(
    horizon_minutes: int = Query(5, ge=1, le=1440),
    _: None = Depends(rate_limit),
) -> PredictionOut:
    result = ml.predict_latest(horizon_minutes=horizon_minutes)
    if result is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Model unavailable — train it first via POST /api/v1/ai/train",
        )
    ml.store_prediction(result)
    return PredictionOut(**result)


@router.get("/predictions", response_model=Paged[PredictionOut])
def list_predictions(
    limit: int = Query(50, ge=1, le=500),
    offset: int = 0,
    _: None = Depends(rate_limit),
    db: Session = Depends(get_db),
) -> Paged[PredictionOut]:
    total = db.query(Prediction).count()
    rows = (
        db.query(Prediction)
        .order_by(Prediction.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    items = [
        PredictionOut(
            timestamp=r.timestamp.isoformat(),
            kind=r.kind,
            horizon_minutes=r.horizon_minutes,
            predicted_power=r.predicted_power,
            predicted_hot_temperature=r.predicted_hot_temperature,
            predicted_cold_temperature=r.predicted_cold_temperature,
            predicted_delta_t=r.predicted_delta_t,
            predicted_efficiency=r.predicted_efficiency,
            confidence=r.confidence,
            model_name=r.model_name,
            data_source=r.data_source,
        )
        for r in rows
    ]
    return Paged[PredictionOut](
        items=items, total=total, limit=limit, offset=offset
    )


@router.post("/purge", response_model=OkResponse)
def purge_predictions(_: User = Depends(require_min_role("ADMIN")), db: Session = Depends(get_db)) -> OkResponse:
    deleted = db.query(Prediction).delete()
    db.commit()
    return OkResponse(detail=f"Deleted {deleted} predictions")
