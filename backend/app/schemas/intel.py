"""Schemas for ML predictions, anomalies, analytics and research."""
import datetime as dt
from typing import Any

from pydantic import BaseModel


class PredictionOut(BaseModel):
    timestamp: str
    kind: str
    horizon_minutes: int
    predicted_power: float | None
    predicted_hot_temperature: float | None
    predicted_cold_temperature: float | None
    predicted_delta_t: float | None
    predicted_efficiency: float | None
    confidence: float | None
    model_name: str
    data_source: str


class AiInsights(BaseModel):
    """Aggregated AI page payload: predictions + recommendations."""

    available: bool
    reason: str = ""
    predicted_power_w: float | None = None
    power_confidence: float | None = None
    predicted_hot_c: float | None = None
    predicted_cold_c: float | None = None
    predicted_delta_t: float | None = None
    predicted_efficiency_pct: float | None = None
    recommendations: list[dict[str, Any]] = []
    model_metrics: dict[str, Any] = {}
    generated_at: str


class TrainResponse(BaseModel):
    status: str
    metrics: dict[str, Any]
    data_rows: int
    data_label: str


class ModelMetrics(BaseModel):
    trained: bool
    trained_at: str | None = None
    data_label: str | None = None
    rows: int | None = None
    metrics: dict[str, Any] = {}


class AnomalyOut(BaseModel):
    id: int
    timestamp: str
    device_id: int | None
    parameter: str
    observed_value: float
    expected_value: float
    severity: str
    anomaly_score: float
    status: str
    detector: str
    message: str


class AnomalyUpdate(BaseModel):
    status: str


class AnomalySummary(BaseModel):
    open: int
    warning: int
    critical: int
    total: int
    recent: list[AnomalyOut]


class StatsResponse(BaseModel):
    parameter: str
    count: int
    mean: float
    std: float
    min: float
    max: float
    p25: float
    p50: float
    p75: float


class CorrelationResponse(BaseModel):
    pair: list[str]
    pearson_r: float
    count: int


class CompareResponse(BaseModel):
    scenarios: list[dict[str, Any]]
    generated_at: str
    data_label: str


class ExperimentCreate(BaseModel):
    name: str
    scenario: str = "D"
    device_id: int | None = None
    config: dict[str, Any] = {}


class ExperimentOut(BaseModel):
    id: int
    experiment_uid: str
    name: str
    scenario: str
    data_source: str
    config: dict[str, Any]
    summary: dict[str, Any]
    started_at: dt.datetime
    ended_at: dt.datetime | None
    status: str
