"""MPPT algorithms: Perturb & Observe (P&O) and Incremental Conductance (INC).

Both operate on a synthetic but monotonic P(V) curve around the true MPP so
tracking efficiency can be demonstrated honestly in the dashboard.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PvCurve:
    """Simplified PV I-V curve for the current irradiance/temperature.

    Current model: I(V) = Isc * (1 - (V/Voc)^1.8) for 0 <= V <= Voc.
    The MPP is derived analytically from THIS curve so reported tracking
    efficiency is measured against the real peak, not a separate estimate.
    """

    voc: float = 22.0
    isc: float = 4.5
    v_mpp: float = 11.0
    p_mpp: float = 60.0

    @classmethod
    def from_conditions(cls, irradiance: float, t_cell: float) -> "PvCurve":
        scale = max(0.05, irradiance / 1000.0)
        isc = 4.5 * scale * (1.0 + 0.0025 * (t_cell - 25.0))
        voc = 22.0 * (1.0 - 0.0028 * (t_cell - 25.0))
        curve = cls(voc=voc, isc=isc)
        # d/dx [ x * (1 - x^1.8) ] = 0  ->  x = (1/2.8)^(1/1.8)
        curve.v_mpp = voc * (1.0 / 2.8) ** (1.0 / 1.8)
        curve.p_mpp = max(0.0, curve.power(curve.v_mpp))
        return curve

    def current(self, voltage: float) -> float:
        if voltage <= 0:
            return self.isc
        if voltage >= self.voc:
            return 0.0
        x = voltage / self.voc
        return self.isc * max(0.0, 1.0 - x**1.8)

    def power(self, voltage: float) -> float:
        return voltage * self.current(voltage)


@dataclass
class MpptTracker:
    """Stateful MPPT controller instance."""

    algorithm: str = "P&O"
    voltage: float = 12.0
    step: float = 0.4
    step_count: int = 0
    direction: int = 1
    _last_power: float = field(default=0.0, repr=False)

    def reset(self, voltage: float = 12.0) -> None:
        self.voltage = voltage
        self.step_count = 0
        self.direction = 1
        self._last_power = 0.0

    def track(self, curve: PvCurve) -> float:
        """Advance one control cycle, return the new operating voltage."""
        self.step_count += 1
        if self.algorithm == "INC":
            self._inc_step(curve)
        else:
            self._po_step(curve)
        self.voltage = max(0.5, min(curve.voc * 0.98, self.voltage))
        return self.voltage

    def _po_step(self, curve: PvCurve) -> None:
        p = curve.power(self.voltage)
        candidate = self.voltage + self.direction * self.step
        p_new = curve.power(candidate)
        if p_new < p:
            # Power fell: reverse direction (classic P&O).
            if self.step_count > 1:
                self.direction *= -1
        else:
            self.voltage = candidate
        self._last_power = p_new

    def _inc_step(self, curve: PvCurve) -> None:
        v = self.voltage
        i = curve.current(v)
        dv = self.step
        i2 = curve.current(v + dv)
        di = i2 - i
        if abs(di) < 1e-6:
            return
        # dP/dV = I + V * dI/dV
        slope = i + v * (di / dv)
        if slope > 0.05:
            self.voltage = v + self.step
        elif slope < -0.05:
            self.voltage = v - self.step
        # else: at MPP, hold.

    def snapshot(self, curve: PvCurve) -> dict:
        op_power = curve.power(self.voltage)
        tracking = (op_power / curve.p_mpp * 100.0) if curve.p_mpp > 0 else 0.0
        return {
            "algorithm": self.algorithm,
            "operating_voltage": round(self.voltage, 3),
            "operating_current": round(curve.current(self.voltage), 3),
            "operating_power": round(op_power, 3),
            "duty_cycle": round(self.voltage / max(curve.voc, 0.01), 3),
            "mpp_voltage": round(curve.v_mpp, 3),
            "mpp_current": round(curve.current(curve.v_mpp), 3),
            "mpp_power": round(curve.p_mpp, 3),
            "tracking_efficiency": round(min(100.0, tracking), 2),
            "step_count": self.step_count,
        }


def pv_curve_points(curve: PvCurve, samples: int = 40) -> dict:
    voltage = [round(curve.voc * i / (samples - 1), 3) for i in range(samples)]
    power = [round(curve.power(v), 3) for v in voltage]
    current = [round(curve.current(v), 3) for v in voltage]
    return {"voltage": voltage, "power": power, "current": current}
