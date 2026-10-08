"""Experiment records for research mode and scenario comparison (A/B/C/D)."""
import datetime as dt
import json

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

SCENARIOS = {
    "A": "Normal solar system",
    "B": "Solar + TEG",
    "C": "Solar + TEG + river cooling",
    "D": "Solar + TEG + adaptive cooling + AI",
}


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    experiment_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    scenario: Mapped[str] = mapped_column(String(8), default="D")
    device_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_source: Mapped[str] = mapped_column(String(20), default="SIMULATED_DATA")
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc)
    )
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="RUNNING")

    @property
    def config(self) -> dict:
        try:
            return json.loads(self.config_json)
        except json.JSONDecodeError:
            return {}

    @property
    def summary(self) -> dict:
        try:
            return json.loads(self.summary_json)
        except json.JSONDecodeError:
            return {}
