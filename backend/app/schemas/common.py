"""Shared response schemas."""
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class OkResponse(BaseModel):
    ok: bool = True
    detail: str = ""


class Paged(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class ErrorDetail(BaseModel):
    detail: str


class HealthStatus(BaseModel):
    status: str
    api: str
    database: str
    ml: str
    simulation: str
    websocket: str
    data_source: str
    mqtt: str
    timestamp: str


class DataSummary(BaseModel):
    data_source: str
    label: str
    simulated: bool
    note: str


def data_summary(source: str) -> DataSummary:
    simulated = source != "LIVE_HARDWARE"
    return DataSummary(
        data_source=source,
        label="LIVE HARDWARE" if not simulated else "DIGITAL TWIN / SIMULATION",
        simulated=simulated,
        note=(
            "Real sensor readings from connected hardware."
            if not simulated
            else "Physics-informed simulated telemetry — not real sensor data."
        ),
    )


class SeriesPoint(BaseModel):
    timestamp: str
    values: dict[str, Any]
