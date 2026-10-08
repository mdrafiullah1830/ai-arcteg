"""Energy accounting records (integrated over time from telemetry)."""
import datetime as dt

from sqlalchemy import Date, DateTime, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EnergyRecord(Base):
    __tablename__ = "energy_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    device_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    pv_energy: Mapped[float] = mapped_column(Float, default=0.0)  # Wh over interval
    teg_energy: Mapped[float] = mapped_column(Float, default=0.0)
    total_energy: Mapped[float] = mapped_column(Float, default=0.0)
    daily_energy: Mapped[float] = mapped_column(Float, default=0.0)  # Wh accumulated today
    cumulative_energy: Mapped[float] = mapped_column(Float, default=0.0)  # Wh all time
    day: Mapped[dt.date | None] = mapped_column(Date, nullable=True, index=True)
