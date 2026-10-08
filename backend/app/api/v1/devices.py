"""Device registry: CRUD + health."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_min_role
from app.models.device import Device
from app.models.user import User
from app.schemas.common import OkResponse, Paged
from app.schemas.core import DeviceCreate, DeviceOut, DeviceUpdate

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=Paged[DeviceOut])
def list_devices(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> Paged[DeviceOut]:
    total = db.query(Device).count()
    items = db.query(Device).order_by(Device.id).offset(offset).limit(limit).all()
    # Mark devices offline if they have not reported within the threshold.
    threshold = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=60)
    for device in items:
        if device.is_simulated:
            continue  # simulated devices are driven by the engine
        last_seen = device.last_seen
        if last_seen is not None and last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=dt.timezone.utc)
        if last_seen is None or last_seen < threshold:
            device.status = "OFFLINE"
    return Paged[DeviceOut].model_validate(
        {"items": items, "total": total, "limit": limit, "offset": offset}
    )


@router.get("/{device_id}", response_model=DeviceOut)
def get_device(device_id: int, db: Session = Depends(get_db)) -> Device:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    return device


@router.post("", response_model=DeviceOut, status_code=status.HTTP_201_CREATED)
def create_device(
    payload: DeviceCreate,
    _: User = Depends(require_min_role("ENGINEER")),
    db: Session = Depends(get_db),
) -> Device:
    if db.query(Device).filter(Device.device_uid == payload.device_uid).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "device_uid already registered")
    device = Device(
        device_uid=payload.device_uid,
        device_name=payload.device_name,
        location=payload.location,
        firmware_version=payload.firmware_version,
        is_simulated=payload.is_simulated,
        mode="DIGITAL_TWIN" if payload.is_simulated else "LIVE_HARDWARE",
        status="OFFLINE",
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


@router.patch("/{device_id}", response_model=DeviceOut)
def update_device(
    device_id: int,
    payload: DeviceUpdate,
    _: User = Depends(require_min_role("ENGINEER")),
    db: Session = Depends(get_db),
) -> Device:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(device, field, value)
    db.commit()
    db.refresh(device)
    return device


@router.delete("/{device_id}", response_model=OkResponse)
def delete_device(
    device_id: int,
    _: User = Depends(require_min_role("ADMIN")),
    db: Session = Depends(get_db),
) -> OkResponse:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    db.delete(device)
    db.commit()
    return OkResponse(detail="Device deleted")
