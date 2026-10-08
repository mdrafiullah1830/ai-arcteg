"""ML prediction records."""
import datetime as dt

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)  # power|thermal|efficiency
    horizon_minutes: Mapped[int] = mapped_column(Integer, default=5)

    predicted_power: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_hot_temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_cold_temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_delta_t: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_efficiency: Mapped[float | None] = mapped_column(Float, nullable=True)

    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_name: Mapped[str] = mapped_column(String(64), default="unavailable")
    data_source: Mapped[str] = mapped_column(String(20), default="SIMULATED_DATA")
