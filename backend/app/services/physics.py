"""Documented simplified physics for the hybrid PV + TEG energy harvester.

Model (research prototype level, not a high-fidelity simulator):

* Solar irradiance follows a clipped sine day curve modulated by cloudiness.
* PV output:      P_pv = G * A_pv * eta_pv * (1 - 0.004 * (T_cell - 25))
* Cell temp:      T_cell = T_ambient + G / 800 * 25
* Concentrator raises hot-side temperature:
      T_hot = T_ambient + (G * A_conc / A_pv) * K_gain * cloud_efficiency
* Cold side is clamped to the river temperature when cooling is enabled,
  otherwise it drifts toward ambient.
* TEG electrical: V = S * dT ; I = V / (R_int + R_load) with R_load = R_int
  (matched load, maximum power point for a linear source).
* Total DC bus power is P_pv + P_teg, minus a small converter loss.
"""
from __future__ import annotations

import math

from app.core.config import settings


def solar_irradiance(sim_seconds: float, cloudiness: float = 0.0, intensity: float = 1.0) -> float:
    """Clear-sky-like irradiance for a 24 h cycle starting at 06:00.

    sim_seconds  Elapsed simulated seconds (wraps every 86400).
    cloudiness   0..1 fraction of sky covered (1 = fully overcast).
    intensity    0.2..1.5 multiplier (scenario knob).
    """
    day_frac = (sim_seconds % 86400) / 86400.0
    # Map 06:00 -> 0.0, 18:00 -> 0.5 of the day for the solar window.
    hour = day_frac * 24.0
    solar_hour = hour - 6.0
    if solar_hour < 0 or solar_hour > 12:
        base = 0.0
    else:
        base = math.sin(math.pi * solar_hour / 12.0) ** 1.3
    g = base * 1000.0 * intensity
    g *= 1.0 - 0.85 * cloudiness
    # Small deterministic ripple so charts are not perfectly smooth.
    g += 12.0 * math.sin(sim_seconds / 37.0)
    return max(0.0, min(1200.0, g))


def pv_power(irradiance: float, ambient_temperature: float) -> tuple[float, float]:
    """Return (P_pv watts, T_cell celsius)."""
    t_cell = ambient_temperature + (irradiance / 800.0) * 25.0
    temp_coef = 1.0 - 0.004 * (t_cell - 25.0)
    power = irradiance * settings.pv_area_m2 * settings.pv_efficiency * max(0.0, temp_coef)
    return power, t_cell


def thermal_states(
    irradiance: float,
    ambient_temperature: float,
    river_temperature: float,
    cooling_effectiveness: float,
) -> tuple[float, float, float, float]:
    """Return (T_hot, T_cold, delta_t, heat_flux).

    cooling_effectiveness 0..1: 0 = cold side floats to ambient,
    1 = cold side pinned to the river temperature.
    """
    cloud_eff = 1.0 if irradiance > 0 else 0.4
    concentration = (irradiance * settings.concentrator_area_m2) / max(settings.pv_area_m2, 0.01)
    t_hot = ambient_temperature + concentration * (settings.concentrator_gain_k / 100.0) * cloud_eff
    t_hot = max(ambient_temperature, min(250.0, t_hot))

    t_cold_free = ambient_temperature + (irradiance / 1000.0) * 8.0
    t_cold_cooled = river_temperature
    t_cold = (
        t_cold_free * (1.0 - cooling_effectiveness)
        + t_cold_cooled * cooling_effectiveness
    )
    t_cold = min(t_cold, t_hot - 1.0)

    delta_t = max(0.0, t_hot - t_cold)
    heat_flux = irradiance * settings.concentrator_area_m2 * 0.55  # W absorbed
    return t_hot, t_cold, delta_t, heat_flux


def teg_output(delta_t: float) -> tuple[float, float, float]:
    """Return (V, I, P) at matched load for the given temperature difference."""
    voltage = settings.teg_seebeck_v_per_k * delta_t
    r_int = max(settings.teg_internal_resistance_ohm, 0.01)
    current = voltage / (2.0 * r_int)
    power = voltage * current
    return voltage, current, power


def system_efficiency(pv_power_w: float, teg_power_w: float, irradiance: float) -> float:
    """Electrical efficiency of the whole aperture at the given irradiance."""
    incident = irradiance * settings.pv_area_m2
    if incident <= 1.0:
        return 0.0
    return (pv_power_w + teg_power_w) / incident * 100.0


def cooling_efficiency(cooling_effectiveness: float, delta_t: float) -> float:
    """How well the cold side is being kept down (0..100 %)."""
    if delta_t <= 1.0:
        return 0.0
    return round(cooling_effectiveness * 100.0 * min(1.0, delta_t / 40.0), 2)


def ambient_temperature(sim_seconds: float, base: float = 28.0, amplitude: float = 6.0) -> float:
    """Diurnal ambient temperature (celsius)."""
    day_frac = (sim_seconds % 86400) / 86400.0
    # Peak ~15:00, trough ~03:00.
    return base + amplitude * math.sin(2.0 * math.pi * (day_frac - 0.25))


def river_temperature(sim_seconds: float, base: float = 24.0, amplitude: float = 2.0) -> float:
    """Slow-moving river temperature (celsius)."""
    day_frac = (sim_seconds % 86400) / 86400.0
    return base + amplitude * math.sin(2.0 * math.pi * (day_frac - 0.35))
