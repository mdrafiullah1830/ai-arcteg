"""Digital twin engine: ticks the physics model, writes telemetry, applies faults.

Runs as an asyncio task inside the FastAPI process. Each tick:
  1. Advances simulated clock (speed-adjusted).
  2. Evaluates the physics model for the active scenario (A/B/C/D).
  3. Applies injected faults (sensor failure, overheating, etc.).
  4. Persists a telemetry row, integrates energy, scores anomalies.
  5. Broadcasts the sample to WebSocket subscribers.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import random

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.models.device import MODE_SIMULATION, Device
from app.models.energy import EnergyRecord
from app.models.telemetry import SensorTelemetry
from app.services import physics
from app.services.anomaly import detect, health_for
from app.services.mppt import MpptTracker, PvCurve
from app.services.settings_store import get_setting

log = get_logger("simulation")

# Scenario definitions (research modes A/B/C/D).
SCENARIOS: dict[str, dict] = {
    "A": {"label": "Normal solar system", "teg": False, "river_cooling": False, "ai": False},
    "B": {"label": "Solar + TEG", "teg": True, "river_cooling": False, "ai": False},
    "C": {"label": "Solar + TEG + river cooling", "teg": True, "river_cooling": True, "ai": False},
    "D": {"label": "Solar + TEG + adaptive cooling + AI", "teg": True, "river_cooling": True, "ai": True},
}

FAULT_BITS = {
    "sensor_failure": 1 << 0,
    "overheating": 1 << 1,
    "low_irradiance": 1 << 2,
    "cooling_degradation": 1 << 3,
    "voltage_spike": 1 << 4,
    "comm_failure": 1 << 5,
}


class SimulationEngine:
    """Singleton asyncio-driven digital twin."""

    def __init__(self) -> None:
        self.running = False
        self.paused = False
        self.speed: float = settings.simulation_speed
        self.tick_seconds: float = settings.simulation_tick_seconds
        self.ticks = 0
        self.elapsed_sim_seconds = 0.0
        self.scenario = "D"
        self.location = settings.simulation_default_location
        self.faults: set[str] = set()
        self.demo_mode = False
        self.cloudiness = 0.25
        self.solar_intensity = 1.0
        self.river_temperature_override: float | None = None
        self.ambient_override: float | None = None
        self.cooling_effectiveness = 0.7
        self.mppt = MpptTracker(algorithm=str(get_setting("mppt_algorithm", "P&O")))
        self.last_sample: dict | None = None
        self._task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._battery_soc = 82.0
        self._battery_voltage = 12.6
        self._cumulative_energy = 0.0
        self._daily_energy = 0.0
        self._daily_day: dt.date | None = None
        self._fault_inject_until: dict[str, float] = {}
        self._weather_note = "simulated clear-sky model"
        self._seed_defaults()

    # ---- lifecycle -------------------------------------------------------
    def _seed_defaults(self) -> None:
        if not self.demo_mode:
            return

    def start(self) -> None:
        if self._task is None or self._task.done():
            self.running = True
            self.paused = False
            # Sync endpoints run in a threadpool with no running loop, so we
            # reuse the main event loop captured during lifespan startup.
            loop = self._loop
            if loop is None:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError as exc:
                    raise RuntimeError(
                        "Simulation loop not initialized — was the app lifespan started?"
                    ) from exc
                self._loop = loop
            self._task = loop.create_task(self._run_loop())
            log.info("Simulation started (scenario=%s, speed=%sx)", self.scenario, self.speed)

    def stop(self) -> None:
        self.running = False
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
        log.info("Simulation stopped")

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False

    async def _run_loop(self) -> None:
        # Backfill a short history so charts are not empty on first load.
        if self.ticks == 0:
            await self._backfill()
        while self.running:
            try:
                if not self.paused:
                    self.tick()
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("Simulation tick failed")
            await asyncio.sleep(max(0.2, self.tick_seconds / max(self.speed, 0.1)))

    async def _backfill(self, minutes: int = 180) -> None:
        """Generate historical samples at 1-minute spacing for charts/training."""
        step = 60
        total = minutes * 60
        db = SessionLocal()
        try:
            device = db.query(Device).filter(Device.is_simulated.is_(True)).first()
            if device is None:
                device = Device(
                    device_uid="twin-001",
                    device_name="Digital Twin (Simulated)",
                    location=self.location,
                    mode=MODE_SIMULATION,
                    is_simulated=True,
                    status="ONLINE",
                    sensor_health="HEALTHY",
                )
                db.add(device)
                db.flush()
            now = dt.datetime.now(dt.timezone.utc)
            for offset in range(total, 0, -step):
                sim_seconds = self.elapsed_sim_seconds - offset
                ts = now - dt.timedelta(seconds=offset)
                sample = self._compute_sample(sim_seconds, ts, persist=False)
            db.add(self._row(device.id, ts, sample))

            # Persist anomaly findings from the live sample (dedup handled
            # by the shared ingest helper).
            from app.services.ingest import persist_anomalies

            persist_anomalies(db, sample, device.id)
            db.commit()
            log.info("Backfilled %d historical telemetry rows", total // step)
        finally:
            db.close()

    # ---- tick ------------------------------------------------------------
    def tick(self) -> dict | None:
        self.ticks += 1
        self.elapsed_sim_seconds += self.tick_seconds * self.speed
        now = dt.datetime.now(dt.timezone.utc)
        sample = self._compute_sample(self.elapsed_sim_seconds, now, persist=True)
        self.last_sample = sample
        return sample

    def _compute_sample(self, sim_seconds: float, ts: dt.datetime, persist: bool) -> dict:
        sc = SCENARIOS.get(self.scenario, SCENARIOS["D"])
        ambient = self.ambient_override
        if ambient is None:
            ambient = physics.ambient_temperature(sim_seconds)
        river = self.river_temperature_override
        if river is None:
            river = physics.river_temperature(sim_seconds)

        irradiance = physics.solar_irradiance(sim_seconds, self.cloudiness, self.solar_intensity)
        # Adaptive cooling in scenario D: effectiveness follows delta-T demand.
        cooling = self.cooling_effectiveness
        if sc["ai"]:
            cooling = min(1.0, 0.45 + 0.08 * max(0.0, (ambient - 26.0)))
            if "cooling_degradation" in self.faults:
                cooling *= 0.35
        elif not sc["river_cooling"]:
            cooling = 0.0

        t_hot, t_cold, delta_t, heat_flux = physics.thermal_states(
            irradiance, ambient, river, cooling
        )
        pv_w, t_cell = physics.pv_power(irradiance, ambient)

        if not sc["teg"]:
            delta_t = 0.0
            t_hot = ambient
            t_cold = ambient
            heat_flux = 0.0
            teg_v = teg_i = teg_p = 0.0
        else:
            teg_v, teg_i, teg_p = physics.teg_output(delta_t)

        # MPPT on the PV curve.
        curve = PvCurve.from_conditions(irradiance, t_cell)
        op_voltage = self.mppt.track(curve)
        pv_voltage = op_voltage
        pv_current = curve.current(op_voltage)
        pv_power_out = curve.power(op_voltage)

        # Faults mutate the observed values (as real broken sensors would).
        fault_mask = 0
        for name in self.faults:
            fault_mask |= FAULT_BITS.get(name, 0)
        if "sensor_failure" in self.faults:
            irradiance = 0.0
            pv_power_out = 0.0
            pv_voltage = 0.0
        if "overheating" in self.faults:
            t_hot += 45.0
            delta_t = max(0.0, t_hot - t_cold)
            teg_v, teg_i, teg_p = physics.teg_output(delta_t)
        if "low_irradiance" in self.faults:
            irradiance *= 0.15
            pv_power_out *= 0.15
        if "voltage_spike" in self.faults:
            pv_voltage = min(curve.voc * 1.15, pv_voltage * 1.4)
            pv_power_out = min(pv_power_out * 1.6, curve.p_mpp * 1.4)
        if "comm_failure" in self.faults:
            # Telemetry keeps flowing locally but device is flagged.
            pass

        total_power = pv_power_out + teg_p
        eff = physics.system_efficiency(pv_power_out, teg_p, max(irradiance, 1.0))
        cooling_eff = physics.cooling_efficiency(cooling, delta_t)

        # Battery integration (simple coulomb counting with limits).
        load = 4.0 + random.uniform(-1.0, 1.0)
        dt_h = self.tick_seconds / 3600.0
        net_wh = (total_power - load) * dt_h
        self._battery_soc = max(5.0, min(100.0, self._battery_soc + net_wh / 26.0 * 100.0 / 100.0))
        self._battery_voltage = 10.8 + (self._battery_soc / 100.0) * 2.6

        sample = {
            "timestamp": ts.isoformat(),
            "data_source": "DIGITAL_TWIN" if not self.demo_mode else "SIMULATED_DATA",
            "irradiance": round(irradiance, 2),
            "ambient_temperature": round(ambient, 2),
            "hot_temperature": round(t_hot, 2),
            "cold_temperature": round(t_cold, 2),
            "river_temperature": round(river, 2),
            "heat_flux": round(heat_flux, 2),
            "pv_voltage": round(pv_voltage, 3),
            "pv_current": round(pv_current, 3),
            "pv_power": round(pv_power_out, 3),
            "teg_voltage": round(teg_v, 3),
            "teg_current": round(teg_i, 3),
            "teg_power": round(teg_p, 3),
            "total_power": round(total_power, 3),
            "battery_voltage": round(self._battery_voltage, 3),
            "battery_soc": round(self._battery_soc, 2),
            "mppt_duty": round(self.mppt.voltage / max(curve.voc, 0.01), 3),
            "cooling_efficiency": round(cooling_eff, 2),
            "system_efficiency": round(eff, 3),
            "delta_t": round(delta_t, 2),
            "fault_state": fault_mask,
            "scenario": self.scenario,
        }

        if persist:
            self._persist(sample, total_power, ts)
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._broadcast(sample))
            except RuntimeError:
                pass  # No running loop (e.g. synchronous test callers)
        return sample

    def _row(self, device_id: int, ts: dt.datetime, sample: dict) -> SensorTelemetry:
        return SensorTelemetry(
            timestamp=ts,
            device_id=device_id,
            data_source=sample["data_source"],
            irradiance=sample["irradiance"],
            ambient_temperature=sample["ambient_temperature"],
            hot_temperature=sample["hot_temperature"],
            cold_temperature=sample["cold_temperature"],
            river_temperature=sample["river_temperature"],
            heat_flux=sample["heat_flux"],
            pv_voltage=sample["pv_voltage"],
            pv_current=sample["pv_current"],
            pv_power=sample["pv_power"],
            teg_voltage=sample["teg_voltage"],
            teg_current=sample["teg_current"],
            teg_power=sample["teg_power"],
            battery_voltage=sample["battery_voltage"],
            battery_soc=sample["battery_soc"],
            mppt_duty=sample["mppt_duty"],
            cooling_efficiency=sample["cooling_efficiency"],
            system_efficiency=sample["system_efficiency"],
            delta_t=sample["delta_t"],
            fault_state=sample["fault_state"],
        )

    def _persist(self, sample: dict, total_power: float, ts: dt.datetime) -> None:
        db = SessionLocal()
        try:
            device = db.query(Device).filter(Device.is_simulated.is_(True)).first()
            if device is None:
                device = Device(
                    device_uid="twin-001",
                    device_name="Digital Twin (Simulated)",
                    location=self.location,
                    mode=MODE_SIMULATION,
                    is_simulated=True,
                    status="ONLINE",
                    sensor_health="HEALTHY",
                )
                db.add(device)
                db.flush()
            device.last_seen = ts
            device.status = "OFFLINE" if "comm_failure" in self.faults else "ONLINE"
            device.sensor_health = health_for(sample)
            db.add(self._row(device.id, ts, sample))

            # Energy integration: interval Wh from this tick.
            interval_h = self.tick_seconds / 3600.0
            pv_wh = sample["pv_power"] * interval_h
            teg_wh = sample["teg_power"] * interval_h
            today = ts.date()
            if self._daily_day != today:
                self._daily_day = today
                self._daily_energy = 0.0
            self._daily_energy += pv_wh + teg_wh
            self._cumulative_energy += pv_wh + teg_wh
            db.add(
                EnergyRecord(
                    timestamp=ts,
                    device_id=device.id,
                    pv_energy=pv_wh,
                    teg_energy=teg_wh,
                    total_energy=pv_wh + teg_wh,
                    daily_energy=self._daily_energy,
                    cumulative_energy=self._cumulative_energy,
                    day=today,
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            log.exception("Persist failed")
        finally:
            db.close()

    async def _broadcast(self, sample: dict) -> None:
        try:
            from app.websocket.manager import manager

            await manager.broadcast({"type": "telemetry", "data": sample})
            findings = detect(sample, fault_state=sample.get("fault_state", 0))
            if findings:
                await manager.broadcast(
                    {
                        "type": "anomaly",
                        "data": {
                            "parameter": findings[0].parameter,
                            "severity": findings[0].severity,
                            "message": findings[0].message,
                        },
                    }
                )
        except Exception:
            pass  # WebSocket is best-effort; never break the sim loop.

    # ---- controls --------------------------------------------------------
    def set_scenario(self, scenario: str) -> None:
        if scenario in SCENARIOS:
            self.scenario = scenario

    def set_fault(self, name: str, enabled: bool) -> None:
        if name not in FAULT_BITS:
            raise ValueError(f"Unknown fault: {name}")
        if enabled:
            self.faults.add(name)
        else:
            self.faults.discard(name)
        log.info("Fault %s %s", name, "enabled" if enabled else "cleared")

    def clear_faults(self) -> None:
        self.faults.clear()

    def update_params(
        self,
        speed: float | None = None,
        tick_seconds: float | None = None,
        cloudiness: float | None = None,
        solar_intensity: float | None = None,
        river_temperature: float | None = None,
        ambient_temperature: float | None = None,
        cooling_effectiveness: float | None = None,
        mppt_algorithm: str | None = None,
        location: str | None = None,
    ) -> None:
        if speed is not None:
            self.speed = speed
        if tick_seconds is not None:
            self.tick_seconds = tick_seconds
        if cloudiness is not None:
            self.cloudiness = cloudiness
        if solar_intensity is not None:
            self.solar_intensity = solar_intensity
        if river_temperature is not None:
            self.river_temperature_override = river_temperature
        if ambient_temperature is not None:
            self.ambient_override = ambient_temperature
        if cooling_effectiveness is not None:
            self.cooling_effectiveness = cooling_effectiveness
        if mppt_algorithm is not None:
            self.mppt.algorithm = mppt_algorithm
        if location is not None:
            self.location = location

    def state(self) -> dict:
        return {
            "running": self.running,
            "paused": self.paused,
            "speed": self.speed,
            "tick_seconds": self.tick_seconds,
            "elapsed_sim_seconds": round(self.elapsed_sim_seconds, 1),
            "ticks": self.ticks,
            "faults": sorted(self.faults),
            "data_source": "DIGITAL_TWIN",
            "scenario": self.scenario,
            "params": {
                "cloudiness": self.cloudiness,
                "solar_intensity": self.solar_intensity,
                "river_temperature": self.river_temperature_override,
                "ambient_temperature": self.ambient_override,
                "cooling_effectiveness": self.cooling_effectiveness,
                "mppt_algorithm": self.mppt.algorithm,
                "location": self.location,
                "scenario_label": SCENARIOS[self.scenario]["label"],
                "weather_note": self._weather_note,
            },
        }


engine = SimulationEngine()
