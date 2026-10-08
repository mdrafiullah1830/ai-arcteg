"""Read-side query helpers: telemetry series, summaries, statistics, correlations."""
from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.anomaly import Anomaly
from app.models.energy import EnergyRecord
from app.models.telemetry import SensorTelemetry

RESOLUTION_SECONDS = {"raw": 0, "1m": 60, "5m": 300, "15m": 900, "1h": 3600}

# Columns exposed on the live/telemetry endpoints.
SAMPLE_FIELDS = [
    "irradiance", "ambient_temperature", "hot_temperature", "cold_temperature",
    "river_temperature", "heat_flux", "pv_voltage", "pv_current", "pv_power",
    "teg_voltage", "teg_current", "teg_power", "battery_voltage", "battery_soc",
    "mppt_duty", "cooling_efficiency", "system_efficiency", "delta_t", "fault_state",
]


def _aware(value: dt.datetime | None) -> dt.datetime | None:
    """SQLite returns naive datetimes; they are always UTC on this project."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.timezone.utc)
    return value


def row_to_sample(row: SensorTelemetry) -> dict[str, Any]:
    ts = _aware(row.timestamp)
    sample: dict[str, Any] = {
        "timestamp": ts.isoformat() if ts else "",
        "data_source": row.data_source,
    }
    for field in SAMPLE_FIELDS:
        sample[field] = getattr(row, field, 0.0)
    sample["total_power"] = round(row.pv_power + row.teg_power, 3)
    return sample


def latest_sample(db: Session, device_id: int | None = None) -> dict[str, Any] | None:
    q = db.query(SensorTelemetry)
    if device_id is not None:
        q = q.filter(SensorTelemetry.device_id == device_id)
    row = q.order_by(SensorTelemetry.timestamp.desc()).first()
    return row_to_sample(row) if row else None


def _window(db: Session, hours: float, device_id: int | None = None):
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
    q = db.query(SensorTelemetry).filter(SensorTelemetry.timestamp >= cutoff)
    if device_id is not None:
        q = q.filter(SensorTelemetry.device_id == device_id)
    return q


def series(
    db: Session,
    parameter: str = "total_power",
    hours: float = 24.0,
    resolution: str = "15m",
    device_id: int | None = None,
    limit: int = 2000,
) -> dict[str, Any]:
    """Down-sampled time series for charts. Buckets by fixed interval."""
    rows = (
        _window(db, hours, device_id)
        .order_by(SensorTelemetry.timestamp.desc())
        .limit(20000)
        .all()
    )
    bucket = RESOLUTION_SECONDS.get(resolution, 900)
    data_source = rows[0].data_source if rows else "DIGITAL_TWIN"

    points: list[dict[str, Any]] = []
    if bucket == 0:
        for row in reversed(rows[-limit:]):
            ts = _aware(row.timestamp)
            points.append({"timestamp": ts.isoformat() if ts else "", "value": _value(row, parameter)})
    else:
        buckets: dict[int, list[float]] = {}
        order: list[int] = []
        for row in rows:
            ts = _aware(row.timestamp)
            if ts is None:
                continue
            key = int(ts.timestamp() // bucket) * bucket
            if key not in buckets:
                buckets[key] = []
                order.append(key)
            value = _value(row, parameter)
            if value is not None:
                buckets[key].append(value)
        for key in sorted(order)[-limit:]:
            values = buckets[key]
            avg = sum(values) / len(values)
            points.append(
                {
                    "timestamp": dt.datetime.fromtimestamp(key, tz=dt.timezone.utc).isoformat(),
                    "value": round(avg, 3),
                    "n": len(values),
                }
            )
    return {
        "resolution": resolution,
        "count": len(points),
        "data_source": data_source,
        "points": list(reversed(points)),
    }


def _value(row: SensorTelemetry, parameter: str) -> float | None:
    if parameter == "total_power":
        return round(row.pv_power + row.teg_power, 3)
    if parameter == "delta_t":
        return row.delta_t
    if hasattr(row, parameter):
        value = getattr(row, parameter)
        return float(value) if isinstance(value, (int, float)) else None
    return None


def energy_summary(db: Session) -> dict[str, Any]:
    today = dt.datetime.now(dt.timezone.utc).date()
    day_start = dt.datetime.combine(today, dt.time.min, tzinfo=dt.timezone.utc)
    today_rows = (
        db.query(
            func.coalesce(func.sum(EnergyRecord.pv_energy), 0.0),
            func.coalesce(func.sum(EnergyRecord.teg_energy), 0.0),
            func.coalesce(func.sum(EnergyRecord.total_energy), 0.0),
        )
        .filter(EnergyRecord.timestamp >= day_start)
        .one()
    )
    pv_today, teg_today, total_today = (float(x) for x in today_rows)
    last = db.query(EnergyRecord).order_by(EnergyRecord.id.desc()).first()
    cumulative = float(last.cumulative_energy) if last else 0.0
    avg_power = 0.0
    if total_today > 0:
        elapsed_h = max(
            (dt.datetime.now(dt.timezone.utc) - day_start).total_seconds() / 3600.0, 1e-6
        )
        avg_power = total_today / elapsed_h
    pv_share = (pv_today / total_today * 100.0) if total_today > 0 else 0.0
    return {
        "today_energy_wh": round(total_today, 3),
        "cumulative_energy_wh": round(cumulative, 3),
        "pv_share_pct": round(pv_share, 2),
        "teg_share_pct": round(100.0 - pv_share, 2),
        "avg_power_w": round(avg_power, 3),
        "data_source": "DIGITAL_TWIN",
    }


def energy_series(db: Session, hours: float = 24.0, resolution: str = "1h") -> list[dict[str, Any]]:
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
    rows = (
        db.query(EnergyRecord)
        .filter(EnergyRecord.timestamp >= cutoff)
        .order_by(EnergyRecord.timestamp.desc())
        .limit(10000)
        .all()
    )
    bucket = RESOLUTION_SECONDS.get(resolution, 3600)
    buckets: dict[int, float] = {}
    for row in rows:
        ts = _aware(row.timestamp)
        if ts is None:
            continue
        key = int(ts.timestamp() // bucket) * bucket
        buckets[key] = buckets.get(key, 0.0) + row.total_energy
    return [
        {
            "timestamp": dt.datetime.fromtimestamp(key, tz=dt.timezone.utc).isoformat(),
            "value": round(value, 4),
        }
        for key, value in sorted(buckets.items())
    ]


def stats(db: Session, parameter: str, hours: float = 24.0) -> dict[str, Any]:
    rows = _window(db, hours).order_by(SensorTelemetry.timestamp.desc()).limit(20000).all()
    values = [v for v in (_value(r, parameter) for r in rows) if v is not None]
    values.sort()
    n = len(values)
    if n == 0:
        return {
            "parameter": parameter, "count": 0, "mean": 0.0, "std": 0.0,
            "min": 0.0, "max": 0.0, "p25": 0.0, "p50": 0.0, "p75": 0.0,
        }
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / n

    def pct(p: float) -> float:
        idx = min(n - 1, max(0, int(p * (n - 1))))
        return values[idx]

    return {
        "parameter": parameter,
        "count": n,
        "mean": round(mean, 4),
        "std": round(var**0.5, 4),
        "min": round(values[0], 4),
        "max": round(values[-1], 4),
        "p25": round(pct(0.25), 4),
        "p50": round(pct(0.50), 4),
        "p75": round(pct(0.75), 4),
    }


def correlation(db: Session, a: str, b: str, hours: float = 24.0) -> dict[str, Any]:
    rows = _window(db, hours).order_by(SensorTelemetry.timestamp.desc()).limit(20000).all()
    pairs = [(_value(r, a), _value(r, b)) for r in rows]
    pairs = [(x, y) for x, y in pairs if x is not None and y is not None]
    n = len(pairs)
    if n < 3:
        return {"pair": [a, b], "pearson_r": 0.0, "count": n}
    mean_a = sum(x for x, _ in pairs) / n
    mean_b = sum(y for _, y in pairs) / n
    cov = sum((x - mean_a) * (y - mean_b) for x, y in pairs) / n
    std_a = (sum((x - mean_a) ** 2 for x, _ in pairs) / n) ** 0.5
    std_b = (sum((y - mean_b) ** 2 for _, y in pairs) / n) ** 0.5
    r = cov / (std_a * std_b) if std_a > 0 and std_b > 0 else 0.0
    return {"pair": [a, b], "pearson_r": round(r, 4), "count": n}


def anomaly_summary(db: Session, limit: int = 10) -> dict[str, Any]:
    total = db.query(func.count(Anomaly.id)).scalar() or 0
    open_count = (
        db.query(func.count(Anomaly.id)).filter(Anomaly.status == "OPEN").scalar() or 0
    )
    warning = (
        db.query(func.count(Anomaly.id)).filter(Anomaly.severity == "WARNING").scalar() or 0
    )
    critical = (
        db.query(func.count(Anomaly.id)).filter(Anomaly.severity == "CRITICAL").scalar() or 0
    )
    recent = (
        db.query(Anomaly).order_by(Anomaly.timestamp.desc()).limit(limit).all()
    )
    return {
        "open": open_count,
        "warning": warning,
        "critical": critical,
        "total": total,
        "recent": recent,
    }
