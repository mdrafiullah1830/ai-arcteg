"""Shared ingestion path for HTTP / MQTT / simulation telemetry writes.

Every source lands here so derived values, anomaly persistence and device
health stay consistent regardless of how the sample arrived.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.anomaly import Anomaly
from app.models.device import Device
from app.models.energy import EnergyRecord
from app.models.telemetry import SensorTelemetry
from app.services.anomaly import detect, health_for

log = get_logger("ingest")

ANOMALY_COOLDOWN = dt.timedelta(minutes=10)


def _anomaly_recent(db: Session, parameter: str, since: dt.datetime) -> bool:
    return (
        db.query(Anomaly)
        .filter(Anomaly.parameter == parameter, Anomaly.status == "OPEN", Anomaly.timestamp >= since)
        .first()
        is not None
    )


def persist_anomalies(db: Session, sample: dict, device_id: int | None, model=None) -> int:
    """Store new findings, suppressing repeats within the cooldown window."""
    findings = detect(sample, model=model, fault_state=int(sample.get("fault_state", 0)))
    now = dt.datetime.now(dt.timezone.utc)
    created = 0
    for f in findings:
        if f.severity != "CRITICAL" and _anomaly_recent(db, f.parameter, now - ANOMALY_COOLDOWN):
            continue
        db.add(
            Anomaly(
                timestamp=now,
                device_id=device_id,
                parameter=f.parameter,
                observed_value=f.observed_value,
                expected_value=f.expected_value,
                severity=f.severity,
                anomaly_score=f.anomaly_score,
                detector=f.detector,
                message=f.message,
            )
        )
        created += 1
    return created


def upsert_device(
    db: Session,
    device_uid: str,
    defaults: dict | None = None,
    source: str = "LIVE_HARDWARE",
) -> Device:
    device = db.query(Device).filter(Device.device_uid == device_uid).first()
    if device is None:
        device = Device(
            device_uid=device_uid,
            device_name=(defaults or {}).get("device_name", f"Device {device_uid}"),
            location=(defaults or {}).get("location", "Dhaka"),
            mode=source,
            is_simulated=source != "LIVE_HARDWARE",
        )
        db.add(device)
        db.flush()
    return device


def store_telemetry(
    db: Session,
    sample: dict,
    device_uid: str,
    data_source: str = "LIVE_HARDWARE",
    auto_register: bool = True,
) -> dict:
    """Persist one telemetry sample + derived energy + anomalies.

    Returns a small acknowledgement dict.
    """
    device = db.query(Device).filter(Device.device_uid == device_uid).first()
    if device is None:
        if not auto_register:
            raise ValueError(f"Unknown device: {device_uid}")
        device = upsert_device(db, device_uid, source=data_source)

    timestamp = sample.get("timestamp")
    if isinstance(timestamp, str):
        try:
            timestamp = dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            timestamp = None
    if timestamp is None:
        timestamp = dt.datetime.now(dt.timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=dt.timezone.utc)

    pv_power = float(sample.get("pv_power") or 0.0)
    teg_power = float(sample.get("teg_power") or 0.0)
    if "pv_power" not in sample and "pv_voltage" in sample:
        pv_power = float(sample.get("pv_voltage", 0.0)) * float(sample.get("pv_current", 0.0))
    if "teg_power" not in sample and "teg_voltage" in sample:
        teg_power = float(sample.get("teg_voltage", 0.0)) * float(sample.get("teg_current", 0.0))
    total_power = pv_power + teg_power

    row = SensorTelemetry(
        timestamp=timestamp,
        device_id=device.id,
        data_source=data_source,
        irradiance=float(sample.get("irradiance") or 0.0),
        ambient_temperature=float(sample.get("ambient_temperature") or 0.0),
        hot_temperature=float(sample.get("hot_temperature") or 0.0),
        cold_temperature=float(sample.get("cold_temperature") or 0.0),
        river_temperature=float(sample.get("river_temperature") or 0.0),
        heat_flux=float(sample.get("heat_flux") or 0.0),
        pv_voltage=float(sample.get("pv_voltage") or 0.0),
        pv_current=float(sample.get("pv_current") or 0.0),
        pv_power=pv_power,
        teg_voltage=float(sample.get("teg_voltage") or 0.0),
        teg_current=float(sample.get("teg_current") or 0.0),
        teg_power=teg_power,
        battery_voltage=float(sample.get("battery_voltage") or 12.6),
        battery_soc=float(sample.get("battery_soc") or 100.0),
        mppt_duty=float(sample.get("mppt_duty") or 0.5),
        cooling_efficiency=float(sample.get("cooling_efficiency") or 0.0),
        system_efficiency=float(sample.get("system_efficiency") or 0.0),
        delta_t=float(sample.get("delta_t") or 0.0),
        fault_state=int(sample.get("fault_state") or 0),
    )
    db.add(row)

    # Device liveness + health.
    device.last_seen = timestamp
    device.status = "ONLINE"
    device.mode = data_source
    device.sensor_health = health_for(
        {
            **{f: getattr(row, f) for f in (
                "hot_temperature", "cold_temperature", "irradiance", "pv_voltage",
                "battery_soc", "system_efficiency", "cooling_efficiency",
            )},
        }
    )

    # Energy integration against the previous sample for this device.
    prev = (
        db.query(SensorTelemetry)
        .filter(SensorTelemetry.device_id == device.id, SensorTelemetry.timestamp < timestamp)
        .order_by(SensorTelemetry.timestamp.desc())
        .first()
    )
    if prev is not None:
        prev_ts = prev.timestamp
        if prev_ts.tzinfo is None:
            prev_ts = prev_ts.replace(tzinfo=dt.timezone.utc)
        dt_hours = max(0.0, (timestamp - prev_ts).total_seconds()) / 3600.0
        dt_hours = min(dt_hours, 1.0)  # clamp long gaps (e.g. device offline)
        pv_wh = (prev.pv_power + pv_power) / 2.0 * dt_hours
        teg_wh = (prev.teg_power + teg_power) / 2.0 * dt_hours
        last_energy = db.query(EnergyRecord).order_by(EnergyRecord.id.desc()).first()
        cumulative = (last_energy.cumulative_energy if last_energy else 0.0) + pv_wh + teg_wh
        today = timestamp.date()
        day_rows = (
            db.query(EnergyRecord)
            .filter(EnergyRecord.day == today)
            .all()
        )
        daily = sum(r.total_energy for r in day_rows) + pv_wh + teg_wh
        db.add(
            EnergyRecord(
                timestamp=timestamp,
                device_id=device.id,
                pv_energy=pv_wh,
                teg_energy=teg_wh,
                total_energy=pv_wh + teg_wh,
                daily_energy=daily,
                cumulative_energy=cumulative,
                day=today,
            )
        )

    created = persist_anomalies(db, row.__dict__ | {"pv_power": pv_power, "teg_power": teg_power}, device.id)
    db.commit()
    return {
        "ok": True,
        "device_id": device.id,
        "telemetry_id": row.id,
        "anomalies_created": created,
    }
