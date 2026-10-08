"""Schemas for simulation control, settings, reports and system."""
from typing import Any, Literal

from pydantic import BaseModel, Field


class SimulationState(BaseModel):
    running: bool
    paused: bool
    speed: float
    tick_seconds: float
    elapsed_sim_seconds: float
    ticks: int
    faults: list[str]
    data_source: str
    scenario: str
    params: dict[str, Any]


class SimulationCommand(BaseModel):
    action: Literal["start", "stop", "pause", "resume"]


class SimulationParams(BaseModel):
    speed: float | None = Field(default=None, ge=0.1, le=120)
    tick_seconds: float | None = Field(default=None, ge=0.5, le=300)
    cloudiness: float | None = Field(default=None, ge=0, le=1)
    solar_intensity: float | None = Field(default=None, ge=0.2, le=1.5)
    river_temperature: float | None = Field(default=None, ge=5, le=45)
    ambient_temperature: float | None = Field(default=None, ge=5, le=50)
    cooling_effectiveness: float | None = Field(default=None, ge=0, le=1)
    mppt_algorithm: Literal["P&O", "INC"] | None = None
    location: str | None = None


class FaultCommand(BaseModel):
    fault: Literal[
        "sensor_failure",
        "overheating",
        "low_irradiance",
        "cooling_degradation",
        "voltage_spike",
        "comm_failure",
    ]
    enable: bool = True


class DemoCommand(BaseModel):
    enable: bool = True


class SettingsUpdate(BaseModel):
    simulation_speed: float | None = Field(default=None, ge=0.1, le=120)
    sampling_interval_seconds: float | None = Field(default=None, ge=0.5, le=300)
    hot_temperature_limit: float | None = Field(default=None, ge=50, le=250)
    cold_temperature_limit: float | None = Field(default=None, ge=0, le=100)
    max_power_w: float | None = Field(default=None, ge=1, le=10000)
    anomaly_threshold: float | None = Field(default=None, ge=0.1, le=1.0)
    mppt_algorithm: Literal["P&O", "INC"] | None = None
    power_model: str | None = None
    data_retention_days: int | None = Field(default=None, ge=1, le=3650)
    location: str | None = None
    device_config: dict[str, Any] | None = None


class ReportResponse(BaseModel):
    title: str
    generated_at: str
    date_from: str
    date_to: str
    data_label: str
    summary: dict[str, Any]
    energy: dict[str, Any]
    thermal: dict[str, Any]
    mppt: dict[str, Any]
    anomalies: dict[str, Any]
    ai: dict[str, Any]
    series: dict[str, list[dict[str, Any]]]


class SystemInfo(BaseModel):
    app: str
    version: str
    environment: str
    data_source: str
    locations: list[str]
    units: dict[str, str]
