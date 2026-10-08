"""Runtime settings and system information endpoints."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine as db_engine
from app.core.deps import rate_limit, require_min_role
from app.models.user import User
from app.schemas.common import HealthStatus, OkResponse
from app.schemas.system import SettingsUpdate, SystemInfo
from app.services import settings_store
from app.simulation.engine import engine
from app.websocket.manager import manager

router = APIRouter(tags=["system"])

LOCATIONS = ["Dhaka", "Chattogram", "Khulna", "Sylhet", "Rajshahi", "Barishal"]

UNITS = {
    "irradiance": "W/m2",
    "temperature": "C",
    "power": "W",
    "voltage": "V",
    "current": "A",
    "energy": "Wh",
    "efficiency": "%",
    "delta_t": "K",
}


@router.get("/system/info", response_model=SystemInfo)
def system_info() -> SystemInfo:
    return SystemInfo(
        app=settings.app_name,
        version="1.0.0",
        environment=settings.environment,
        data_source="DIGITAL_TWIN" if engine.running else "IDLE",
        locations=LOCATIONS,
        units=UNITS,
    )


@router.get("/system/health", response_model=HealthStatus)
def health(_: None = Depends(rate_limit)) -> HealthStatus:
    api = "up"
    try:
        with db_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        database = "up"
    except Exception:
        database = "down"
        api = "degraded"

    from app.ml import service as ml

    ml_status = "trained" if ml.model_available() else "untrained"
    simulation = "running" if engine.running and not engine.paused else ("paused" if engine.paused else "stopped")
    from app.services import queries  # noqa: F401  (import cycle guard)

    data_source = "DIGITAL_TWIN" if engine.running else "IDLE"
    if settings.mqtt_broker_url:
        mqtt = "configured"
    else:
        mqtt = "disabled"

    return HealthStatus(
        status=api,
        api=api,
        database=database,
        ml=ml_status,
        simulation=simulation,
        websocket=f"{manager.count} clients",
        data_source=data_source,
        mqtt=mqtt,
        timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
    )


@router.get("/settings")
def get_settings(_: None = Depends(rate_limit)) -> dict:
    return settings_store.all_settings()


@router.put("/settings", response_model=OkResponse)
def update_settings(
    payload: SettingsUpdate,
    _: User = Depends(require_min_role("ENGINEER")),
) -> OkResponse:
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No fields to update")
    applied = []
    for key, value in data.items():
        if value is None:
            continue
        settings_store.set_setting(key, value)
        applied.append(key)
        # Push hot-applyable values into the live simulation.
        if key == "simulation_speed":
            engine.speed = value
        elif key == "sampling_interval_seconds":
            engine.tick_seconds = value
        elif key == "mppt_algorithm":
            engine.mppt.algorithm = value
            engine.mppt.reset()
        elif key == "location":
            engine.location = value
    return OkResponse(detail=f"Updated: {', '.join(applied)}")
