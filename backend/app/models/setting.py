"""Runtime system settings stored as key/value JSON (overridable via API)."""
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, default="null")
    description: Mapped[str] = mapped_column(String(255), default="")
