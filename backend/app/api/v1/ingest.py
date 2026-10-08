"""Hardware ingestion endpoint: ESP32/HTTP POST guarded by an API key.

Firmware POSTs JSON here (see firmware/README and firmware/esp32_sketch).
MQTT ingestion (if configured) funnels into the same store_telemetry path.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.schemas.common import OkResponse
from app.schemas.core import TelemetryIngest
from app.services.ingest import store_telemetry

router = APIRouter(prefix="/ingest", tags=["ingest"])


def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if not x_api_key or x_api_key != settings.device_ingest_api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid ingestion API key")


@router.post("/telemetry", response_model=OkResponse)
async def ingest_telemetry(
    payload: TelemetryIngest,
    _: None = Depends(verify_api_key),
    db: Session = Depends(get_db),
) -> OkResponse:
    """Receive one hardware telemetry frame and persist it."""
    sample = payload.model_dump(mode="json")
    try:
        result = store_telemetry(db, sample, payload.device_uid, data_source="LIVE_HARDWARE")
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    try:
        from app.websocket.manager import manager

        await manager.broadcast(
            {"type": "telemetry", "data": {"source": "LIVE_HARDWARE", **sample}}
        )
    except Exception:
        pass  # WebSocket fan-out is best effort.
    return OkResponse(detail=f"stored telemetry #{result['telemetry_id']}")


@router.get("/config", response_model=OkResponse)
async def ingest_config(_: None = Depends(verify_api_key)) -> OkResponse:
    """Firmware bootstrap: lets a device confirm its key and learn intervals."""
    return OkResponse(
        detail=f"tick={settings.simulation_tick_seconds}s prefix={settings.mqtt_topic_prefix}"
    )


@router.post("/batch", response_model=OkResponse)
async def ingest_batch(
    payloads: list[TelemetryIngest],
    _: None = Depends(verify_api_key),
    db: Session = Depends(get_db),
) -> OkResponse:
    """Store a batch of frames (offline buffer flush from the gateway)."""
    stored = 0
    for payload in payloads:
        try:
            store_telemetry(db, payload.model_dump(mode="json"), payload.device_uid)
            stored += 1
        except ValueError:
            continue
    # Let other tasks (WS broadcast) run between requests.
    await asyncio.sleep(0)
    return OkResponse(detail=f"stored {stored}/{len(payloads)} frames")
