"""Anomaly detection: deterministic rules + optional IsolationForest model."""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings

# parameter -> (warning_low, warning_high, critical_low, critical_high, unit)
RULE_LIMITS: dict[str, tuple[float, float, float, float, str]] = {
    "hot_temperature": (0.0, 90.0, 0.0, 130.0, "C"),
    "cold_temperature": (0.0, 55.0, 0.0, 80.0, "C"),
    "delta_t": (0.0, 70.0, 0.0, 110.0, "K"),
    "irradiance": (0.0, 1150.0, 0.0, 1400.0, "W/m2"),
    "pv_voltage": (0.0, 24.0, 0.0, 30.0, "V"),
    "teg_power": (0.0, 8.0, 0.0, 12.0, "W"),
    "battery_soc": (15.0, 100.0, 5.0, 100.0, "%"),
    "battery_voltage": (10.5, 14.5, 9.5, 16.0, "V"),
    "system_efficiency": (3.0, 45.0, 1.0, 60.0, "%"),
    "cooling_efficiency": (5.0, 100.0, 0.0, 100.0, "%"),
}


@dataclass
class Finding:
    parameter: str
    observed_value: float
    expected_value: float
    severity: str
    anomaly_score: float
    detector: str
    message: str


def _score(value: float, warn: float, crit: float, hard_limit: float) -> float:
    """0..1 severity score: distance past the warning band normalized by limit."""
    span = max(abs(hard_limit - warn), 1e-6)
    return min(1.0, abs(value - warn) / span)


def rule_detections(sample: dict) -> list[Finding]:
    """Evaluate static operating envelopes against one telemetry sample."""
    findings: list[Finding] = []
    for param, (w_lo, w_hi, c_lo, c_hi, unit) in RULE_LIMITS.items():
        if param not in sample:
            continue
        value = float(sample[param])
        if c_lo <= value <= c_hi and w_lo <= value <= w_hi:
            continue  # healthy
        if value < c_lo or value > c_hi:
            severity = "CRITICAL"
            score = _score(value, w_lo if value < w_lo else w_hi,
                           c_lo if value < c_lo else c_hi,
                           c_lo if value < c_lo else c_hi)
            score = max(score, 0.85)
        else:
            severity = "WARNING"
            score = 0.5 + 0.3 * _score(value, w_lo if value < w_lo else w_hi,
                                       c_lo if value < c_lo else c_hi,
                                       w_lo if value < w_lo else w_hi)
        edge = w_lo if value < w_lo else w_hi
        findings.append(
            Finding(
                parameter=param,
                observed_value=round(value, 3),
                expected_value=edge,
                severity=severity,
                anomaly_score=round(min(1.0, score), 3),
                detector="rule",
                message=f"{param} = {value:.2f}{unit} outside {edge:.1f}{unit} operating band",
            )
        )
    return findings


def ml_detections(sample: dict, model=None) -> list[Finding]:
    """Score a sample with the trained IsolationForest (if loaded)."""
    if model is None:
        return []
    features = [
        "irradiance", "ambient_temperature", "hot_temperature", "cold_temperature",
        "pv_voltage", "pv_power", "teg_voltage", "teg_power",
        "battery_voltage", "battery_soc", "system_efficiency",
    ]
    try:
        vector = [[float(sample.get(f, 0.0)) for f in features]]
        pred = model.predict(vector)[0]
        score = float(model.decision_function(vector)[0])
    except Exception:
        return []
    if pred != -1:
        return []
    severity = "CRITICAL" if score < -0.15 else "WARNING"
    # Highest-deviation feature for a human-readable message.
    worst, worst_delta = features[0], 0.0
    for name in features:
        try:
            delta = abs(float(sample.get(name, 0.0)))
        except (TypeError, ValueError):
            delta = 0.0
        if delta > worst_delta:
            worst, worst_delta = name, delta
    return [
        Finding(
            parameter=worst,
            observed_value=round(float(sample.get(worst, 0.0)), 3),
            expected_value=0.0,
            severity=severity,
            anomaly_score=round(min(1.0, abs(score) * 3.0), 3),
            detector="iforest",
            message=f"IsolationForest flagged unsupervised outlier (score={score:.3f})",
        )
    ]


def fault_flags(fault_state: int) -> list[str]:
    """Decode the simulator fault bitmask into names (mirrors firmware flags)."""
    names = ["sensor_failure", "overheating", "low_irradiance",
             "cooling_degradation", "voltage_spike", "comm_failure"]
    return [n for i, n in enumerate(names) if fault_state & (1 << i)]


def detect(sample: dict, model=None, fault_state: int = 0) -> list[Finding]:
    """Run all detectors on a telemetry sample."""
    findings = rule_detections(sample)
    findings.extend(ml_detections(sample, model))
    if fault_state:
        findings.append(
            Finding(
                parameter="fault_state",
                observed_value=float(fault_state),
                expected_value=0.0,
                severity="CRITICAL",
                anomaly_score=0.95,
                detector="fault_bitmask",
                message="Active faults: " + ", ".join(fault_flags(fault_state)),
            )
        )
    return findings


def health_for(sample: dict) -> str:
    """Aggregate sensor health label for the device row."""
    findings = rule_detections(sample)
    if any(f.severity == "CRITICAL" for f in findings):
        return "FAULT"
    if findings:
        return "DEGRADED"
    return "HEALTHY"


DEFAULT_THRESHOLDS = {
    "hot_temperature_limit": 120.0,
    "cold_temperature_limit": 60.0,
    "anomaly_threshold": 0.6,
    "max_power_w": 500.0,
}


def active_thresholds() -> dict:
    """Thresholds overridden at runtime via the settings API, else defaults."""
    from app.services.settings_store import get_setting

    merged = dict(DEFAULT_THRESHOLDS)
    for key in merged:
        value = get_setting(key)
        if value is not None:
            merged[key] = value
    return merged
