"""Anomaly / alert records produced by rule + ML detectors."""
import datetime as dt

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Anomaly(Base):
    __tablename__ = "anomalies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    device_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    parameter: Mapped[str] = mapped_column(String(48), index=True)
    observed_value: Mapped[float] = mapped_column(Float)
    expected_value: Mapped[float] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(String(16), default="INFO")  # INFO|WARNING|CRITICAL
    anomaly_score: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default="OPEN", index=True)  # OPEN|ACK|RESOLVED
    detector: Mapped[str] = mapped_column(String(32), default="rule")
    message: Mapped[str] = mapped_column(String(255), default="")
