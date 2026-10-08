"""Unit tests for physics, MPPT and anomaly rule layers (no HTTP/DB needed)."""
from __future__ import annotations

import math

from app.services import physics
from app.services.anomaly import detect, rule_detections
from app.services.mppt import MpptTracker, PvCurve


# ---- physics ---------------------------------------------------------------
def test_irradiance_zero_at_night() -> None:
    # 00:00 of the sim day -> night.
    assert physics.solar_irradiance(0.0) == 0.0


def test_irradiance_positive_at_noon() -> None:
    # Noon = 6 h into the solar window (sim_seconds = 12h -> hour 12 -> solar_hour 6).
    g = physics.solar_irradiance(12 * 3600)
    assert g > 300


def test_irradiance_cloudiness_reduces_output() -> None:
    clear = physics.solar_irradiance(12 * 3600, cloudiness=0.0)
    cloudy = physics.solar_irradiance(12 * 3600, cloudiness=1.0)
    assert cloudy < clear


def test_pv_power_scales_with_irradiance() -> None:
    low, _ = physics.pv_power(200, 30)
    high, _ = physics.pv_power(1000, 30)
    assert high > low > 0


def test_pv_power_temperature_penalty() -> None:
    cool, _ = physics.pv_power(1000, 20)
    hot, _ = physics.pv_power(1000, 60)
    assert cool > hot


def test_thermal_delta_t_positive_with_sun() -> None:
    t_hot, t_cold, delta_t, flux = physics.thermal_states(1000, 30, 25, 0.8)
    assert t_hot > t_cold
    assert delta_t > 0
    assert flux > 0


def test_river_cooling_lowers_cold_side() -> None:
    _, cold_no_cool, _, _ = physics.thermal_states(1000, 40, 22, 0.0)
    _, cold_cooled, _, _ = physics.thermal_states(1000, 40, 22, 1.0)
    assert cold_cooled < cold_no_cool


def test_teg_power_grows_with_delta_t() -> None:
    _, _, p_small = physics.teg_output(10)
    _, _, p_large = physics.teg_output(50)
    assert p_large > p_small > 0


def test_ambient_diurnal_bounds() -> None:
    temps = [physics.ambient_temperature(s) for s in range(0, 86400, 600)]
    assert min(temps) >= 20 and max(temps) <= 36


# ---- MPPT ------------------------------------------------------------------
def test_pv_curve_mpp_within_range() -> None:
    curve = PvCurve.from_conditions(1000, 25)
    assert 0 < curve.v_mpp < curve.voc
    assert curve.power(curve.v_mpp) >= curve.power(curve.voc * 0.3)


def test_po_converges_toward_mpp() -> None:
    curve = PvCurve.from_conditions(1000, 25)
    tracker = MpptTracker(algorithm="P&O", voltage=5.0)
    for _ in range(60):
        tracker.track(curve)
    assert tracker.snapshot(curve)["tracking_efficiency"] > 85


def test_inc_converges_toward_mpp() -> None:
    curve = PvCurve.from_conditions(1000, 25)
    tracker = MpptTracker(algorithm="INC", voltage=5.0)
    for _ in range(60):
        tracker.track(curve)
    assert tracker.snapshot(curve)["tracking_efficiency"] > 85


def test_voltage_stays_within_curve_bounds() -> None:
    curve = PvCurve.from_conditions(800, 35)
    tracker = MpptTracker(algorithm="P&O", voltage=1.0)
    for _ in range(50):
        v = tracker.track(curve)
        assert 0 < v <= curve.voc * 0.98 + 1e-6


# ---- anomaly rules ---------------------------------------------------------
def test_healthy_sample_has_no_findings() -> None:
    sample = {
        "hot_temperature": 65,
        "cold_temperature": 30,
        "delta_t": 35,
        "irradiance": 900,
        "pv_voltage": 18,
        "teg_power": 3,
        "battery_soc": 80,
        "battery_voltage": 12.6,
        "system_efficiency": 15,
        "cooling_efficiency": 55,
    }
    assert rule_detections(sample) == []


def test_overtemperature_flagged_critical() -> None:
    sample = {"hot_temperature": 140}
    findings = rule_detections(sample)
    assert len(findings) == 1
    assert findings[0].parameter == "hot_temperature"
    assert findings[0].severity == "CRITICAL"


def test_low_battery_warning() -> None:
    sample = {"battery_soc": 10}
    findings = rule_detections(sample)
    assert findings and findings[0].severity == "WARNING"


def test_fault_bitmask_reported() -> None:
    findings = detect({"irradiance": 900}, fault_state=0b10)
    fault_findings = [f for f in findings if f.detector == "fault_bitmask"]
    assert fault_findings
    assert "overheating" in fault_findings[0].message


def test_scores_bounded() -> None:
    findings = rule_detections({"hot_temperature": 250, "battery_soc": 0})
    for f in findings:
        assert 0 <= f.anomaly_score <= 1
