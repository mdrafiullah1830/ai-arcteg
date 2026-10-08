"""Runtime key/value settings with defaults (backed by the system_settings table)."""
from __future__ import annotations

import json
import threading

from app.core.database import SessionLocal
from app.models.setting import SystemSetting

_lock = threading.Lock()

DEFAULTS: dict[str, object] = {
    "simulation_speed": 1.0,
    "sampling_interval_seconds": 5.0,
    "hot_temperature_limit": 120.0,
    "cold_temperature_limit": 60.0,
    "max_power_w": 500.0,
    "anomaly_threshold": 0.6,
    "mppt_algorithm": "P&O",
    "power_model": "linear",
    "data_retention_days": 30,
    "location": "Dhaka",
    "device_config": {},
}

DESCRIPTIONS = {
    "simulation_speed": "Digital twin time multiplier (1 = real time)",
    "sampling_interval_seconds": "Telemetry sample period in seconds",
    "hot_temperature_limit": "Critical hot-side threshold (C)",
    "cold_temperature_limit": "Critical cold-side threshold (C)",
    "max_power_w": "Expected maximum system power (W)",
    "anomaly_threshold": "ML anomaly score threshold (0..1)",
    "mppt_algorithm": "Active MPPT algorithm (P&O or INC)",
    "power_model": "Power curve model name",
    "data_retention_days": "Telemetry retention window",
    "location": "Site label shown on dashboards",
    "device_config": "Free-form per-device overrides",
}


def get_setting(key: str, default: object = None) -> object:
    with _lock:
        try:
            db = SessionLocal()
            try:
                row = db.get(SystemSetting, key)
                if row is None:
                    return DEFAULTS.get(key, default)
                return json.loads(row.value_json)
            finally:
                db.close()
        except Exception:
            return DEFAULTS.get(key, default)


def set_setting(key: str, value: object, description: str = "") -> None:
    with _lock:
        db = SessionLocal()
        try:
            row = db.get(SystemSetting, key)
            payload = json.dumps(value)
            if row is None:
                db.add(
                    SystemSetting(
                        key=key,
                        value_json=payload,
                        description=description or DESCRIPTIONS.get(key, ""),
                    )
                )
            else:
                row.value_json = payload
                if description:
                    row.description = description
            db.commit()
        finally:
            db.close()


def all_settings() -> dict[str, dict]:
    """Merged view of defaults + persisted overrides."""
    result: dict[str, dict] = {}
    for key, value in DEFAULTS.items():
        result[key] = {
            "value": value,
            "description": DESCRIPTIONS.get(key, ""),
            "source": "default",
        }
    try:
        db = SessionLocal()
        try:
            for row in db.query(SystemSetting).all():
                try:
                    value = json.loads(row.value_json)
                except json.JSONDecodeError:
                    value = row.value_json
                result[row.key] = {
                    "value": value,
                    "description": row.description or DESCRIPTIONS.get(row.key, ""),
                    "source": "override",
                }
        finally:
            db.close()
    except Exception:
        pass
    return result


def ensure_defaults() -> None:
    """Persist defaults on first boot so they show up as editable rows."""
    for key, value in DEFAULTS.items():
        try:
            db = SessionLocal()
            try:
                if db.get(SystemSetting, key) is None:
                    db.add(
                        SystemSetting(
                            key=key,
                            value_json=json.dumps(value),
                            description=DESCRIPTIONS.get(key, ""),
                        )
                    )
                    db.commit()
            finally:
                db.close()
        except Exception:
            pass
