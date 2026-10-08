"""Schemas for devices, telemetry, energy, thermal and MPPT."""
import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---- Devices -------------------------------------------------------------
class DeviceCreate(BaseModel):
    device_uid: str = Field(min_length=3, max_length=64)
    device_name: str = Field(min_length=2, max_length=120)
    location: str = "Dhaka"
    firmware_version: str = "0.0.0"
    is_simulated: bool = True


class DeviceUpdate(BaseModel):
    device_name: str | None = None
    location: str | None = None
    firmware_version: str | None = None
    status: str | None = None


class DeviceOut(BaseModel):
    id: int
    device_uid: str
    device_name: str
    location: str
    mode: str
    firmware_version: str
    status: str
    sensor_health: str
    is_simulated: bool
    last_seen: dt.datetime | None

    model_config = {"from_attributes": True}


# ---- Telemetry -----------------------------------------------------------
TelemetryPayload = dict[str, Any]


class TelemetryIngest(BaseModel):
    """ESP32/HTTP ingestion payload. All physical values validated below."""

    device_uid: str
    timestamp: dt.datetime | None = None
    irradiance: float = Field(ge=0, le=2000)
    ambient_temperature: float = Field(ge=-20, le=70)
    hot_temperature: float = Field(ge=-20, le=250)
    cold_temperature: float = Field(ge=-20, le=150)
    river_temperature: float = Field(ge=-20, le=60)
    pv_voltage: float = Field(ge=0, le=100)
    pv_current: float = Field(ge=0, le=50)
    teg_voltage: float = Field(ge=0, le=100)
    teg_current: float = Field(ge=0, le=50)
    battery_voltage: float = Field(default=12.6, ge=0, le=30)
    battery_soc: float = Field(default=100.0, ge=0, le=100)
    mppt_duty: float = Field(default=0.5, ge=0, le=1)


class TelemetryPoint(BaseModel):
    timestamp: str
    data_source: str
    irradiance: float
    ambient_temperature: float
    hot_temperature: float
    cold_temperature: float
    river_temperature: float
    heat_flux: float
    pv_voltage: float
    pv_current: float
    pv_power: float
    teg_voltage: float
    teg_current: float
    teg_power: float
    total_power: float
    battery_voltage: float
    battery_soc: float
    mppt_duty: float
    cooling_efficiency: float
    system_efficiency: float
    delta_t: float
    fault_state: int


class SeriesResponse(BaseModel):
    resolution: str
    count: int
    data_source: str
    points: list[dict[str, Any]]


# ---- Energy --------------------------------------------------------------
class EnergySummary(BaseModel):
    today_energy_wh: float
    cumulative_energy_wh: float
    pv_share_pct: float
    teg_share_pct: float
    avg_power_w: float
    data_source: str


# ---- Thermal -------------------------------------------------------------
class ThermalCurrent(BaseModel):
    hot_temperature: float
    cold_temperature: float
    river_temperature: float
    ambient_temperature: float
    delta_t: float
    cooling_efficiency: float
    heat_flux: float
    data_source: str


# ---- MPPT ----------------------------------------------------------------
class MpptState(BaseModel):
    algorithm: str
    operating_voltage: float
    operating_current: float
    operating_power: float
    duty_cycle: float
    mpp_voltage: float
    mpp_current: float
    mpp_power: float
    tracking_efficiency: float
    step_count: int
    data_source: str


class MpptSelect(BaseModel):
    algorithm: Literal["P&O", "INC"]


class PvCurveResponse(BaseModel):
    voltage: list[float]
    power: list[float]
    current: list[float]
    mpp_voltage: float
    mpp_power: float
    operating_voltage: float
    operating_power: float
