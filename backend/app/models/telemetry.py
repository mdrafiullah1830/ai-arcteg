"""Sensor telemetry time-series row (high frequency, aggregated at query time)."""
import datetime as dt

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SensorTelemetry(Base):
    __tablename__ = "sensor_telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)
    data_source: Mapped[str] = mapped_column(String(20), default="DIGITAL_TWIN")

    irradiance: Mapped[float] = mapped_column(Float, default=0.0)
    ambient_temperature: Mapped[float] = mapped_column(Float, default=0.0)
    hot_temperature: Mapped[float] = mapped_column(Float, default=0.0)
    cold_temperature: Mapped[float] = mapped_column(Float, default=0.0)
    river_temperature: Mapped[float] = mapped_column(Float, default=0.0)
    heat_flux: Mapped[float] = mapped_column(Float, default=0.0)

    pv_voltage: Mapped[float] = mapped_column(Float, default=0.0)
    pv_current: Mapped[float] = mapped_column(Float, default=0.0)
    pv_power: Mapped[float] = mapped_column(Float, default=0.0)

    teg_voltage: Mapped[float] = mapped_column(Float, default=0.0)
    teg_current: Mapped[float] = mapped_column(Float, default=0.0)
    teg_power: Mapped[float] = mapped_column(Float, default=0.0)

    battery_voltage: Mapped[float] = mapped_column(Float, default=12.6)
    battery_soc: Mapped[float] = mapped_column(Float, default=100.0)

    mppt_duty: Mapped[float] = mapped_column(Float, default=0.5)
    cooling_efficiency: Mapped[float] = mapped_column(Float, default=0.0)
    system_efficiency: Mapped[float] = mapped_column(Float, default=0.0)

    delta_t: Mapped[float] = mapped_column(Float, default=0.0)
    fault_state: Mapped[int] = mapped_column(Integer, default=0)


Index("ix_telemetry_device_ts", SensorTelemetry.device_id, SensorTelemetry.timestamp)
