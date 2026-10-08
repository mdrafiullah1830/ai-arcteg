"""Telemetry, energy, thermal and MPPT read models."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import rate_limit
from app.schemas.common import data_summary
from app.schemas.core import (
    EnergySummary,
    MpptSelect,
    MpptState,
    PvCurveResponse,
    SeriesResponse,
    TelemetryPoint,
    ThermalCurrent,
)
from app.services import queries
from app.services.mppt import PvCurve, pv_curve_points
from app.simulation.engine import engine

router = APIRouter(tags=["telemetry"])


@router.get("/telemetry/current", response_model=TelemetryPoint)
def current_telemetry(
    _: None = Depends(rate_limit),
    db: Session = Depends(get_db),
) -> TelemetryPoint:
    sample = queries.latest_sample(db)
    if sample is None:
        # Fall back to the live engine state before the first row is persisted.
        sample = engine.last_sample
    if sample is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No telemetry yet")
    return TelemetryPoint(**sample)


@router.get("/telemetry/series", response_model=SeriesResponse)
def telemetry_series(
    parameter: str = Query("total_power"),
    hours: float = Query(24.0, gt=0, le=24 * 30),
    resolution: str = Query("15m"),
    device_id: int | None = Query(None),
    _: None = Depends(rate_limit),
    db: Session = Depends(get_db),
) -> SeriesResponse:
    data = queries.series(db, parameter=parameter, hours=hours, resolution=resolution, device_id=device_id)
    return SeriesResponse(**data)


@router.get("/telemetry/data-source")
def data_source(_: None = Depends(rate_limit), db: Session = Depends(get_db)) -> dict:
    sample = queries.latest_sample(db)
    source = sample["data_source"] if sample else "DIGITAL_TWIN"
    return data_summary(source).model_dump()


@router.get("/energy/summary", response_model=EnergySummary)
def energy(_: None = Depends(rate_limit), db: Session = Depends(get_db)) -> EnergySummary:
    return EnergySummary(**queries.energy_summary(db))


@router.get("/energy/series")
def energy_series(
    hours: float = Query(24.0, gt=0, le=24 * 30),
    resolution: str = Query("1h"),
    _: None = Depends(rate_limit),
    db: Session = Depends(get_db),
) -> dict:
    points = queries.energy_series(db, hours=hours, resolution=resolution)
    return {"resolution": resolution, "count": len(points), "points": points}


@router.get("/thermal/current", response_model=ThermalCurrent)
def thermal(_: None = Depends(rate_limit), db: Session = Depends(get_db)) -> ThermalCurrent:
    sample = queries.latest_sample(db) or engine.last_sample
    if sample is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No telemetry yet")
    return ThermalCurrent(
        hot_temperature=sample["hot_temperature"],
        cold_temperature=sample["cold_temperature"],
        river_temperature=sample["river_temperature"],
        ambient_temperature=sample["ambient_temperature"],
        delta_t=sample["delta_t"],
        cooling_efficiency=sample["cooling_efficiency"],
        heat_flux=sample["heat_flux"],
        data_source=sample["data_source"],
    )


@router.get("/mppt/state", response_model=MpptState)
def mppt_state(_: None = Depends(rate_limit), db: Session = Depends(get_db)) -> MpptState:
    sample = queries.latest_sample(db) or engine.last_sample or {}
    curve = PvCurve.from_conditions(
        sample.get("irradiance", 800.0),
        sample.get("ambient_temperature", 30.0),
    )
    snap = engine.mppt.snapshot(curve)
    snap["data_source"] = sample.get("data_source", "DIGITAL_TWIN")
    return MpptState(**snap)


@router.post("/mppt/select", response_model=MpptState)
def mppt_select(payload: MpptSelect, db: Session = Depends(get_db)) -> MpptState:
    engine.mppt.algorithm = payload.algorithm
    engine.mppt.reset()
    return mppt_state(db=db)


@router.get("/mppt/pv-curve", response_model=PvCurveResponse)
def pv_curve(_: None = Depends(rate_limit), db: Session = Depends(get_db)) -> PvCurveResponse:
    sample = queries.latest_sample(db) or engine.last_sample or {}
    curve = PvCurve.from_conditions(
        sample.get("irradiance", 800.0),
        sample.get("ambient_temperature", 30.0),
    )
    points = pv_curve_points(curve)
    return PvCurveResponse(
        voltage=points["voltage"],
        power=points["power"],
        current=points["current"],
        mpp_voltage=round(curve.v_mpp, 3),
        mpp_power=round(curve.p_mpp, 3),
        operating_voltage=round(engine.mppt.voltage, 3),
        operating_power=round(curve.power(engine.mppt.voltage), 3),
    )
