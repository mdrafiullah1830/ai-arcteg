"""Registered IoT device model."""
import datetime as dt

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

MODE_LIVE = "LIVE_HARDWARE"
MODE_SIMULATION = "DIGITAL_TWIN"


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    device_name: Mapped[str] = mapped_column(String(120), nullable=False)
    location: Mapped[str] = mapped_column(String(120), default="Dhaka")
    mode: Mapped[str] = mapped_column(String(32), default=MODE_SIMULATION)
    firmware_version: Mapped[str] = mapped_column(String(32), default="0.0.0")
    status: Mapped[str] = mapped_column(String(20), default="OFFLINE")  # ONLINE/OFFLINE/FAULT
    sensor_health: Mapped[str] = mapped_column(String(20), default="UNKNOWN")
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc)
    )
