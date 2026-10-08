"""Simulation control: start/stop/pause, params, faults, demo mode."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import require_min_role
from app.models.user import User
from app.schemas.common import OkResponse
from app.schemas.system import FaultCommand, SimulationCommand, SimulationParams, SimulationState
from app.simulation.engine import FAULT_BITS, SCENARIOS, engine

router = APIRouter(prefix="/simulation", tags=["simulation"])


@router.get("/state", response_model=SimulationState)
async def state() -> SimulationState:
    return SimulationState(**engine.state())


@router.post("/command", response_model=SimulationState)
async def command(
    payload: SimulationCommand,
    _: User = Depends(require_min_role("ENGINEER")),
) -> SimulationState:
    action = payload.action
    if action == "start":
        engine.start()
    elif action == "stop":
        engine.stop()
    elif action == "pause":
        if not engine.running:
            raise HTTPException(status.HTTP_409_CONFLICT, "Simulation is not running")
        engine.pause()
    elif action == "resume":
        if not engine.running:
            raise HTTPException(status.HTTP_409_CONFLICT, "Simulation is not running")
        engine.resume()
    return SimulationState(**engine.state())


@router.post("/params", response_model=SimulationState)
async def params(
    payload: SimulationParams,
    _: User = Depends(require_min_role("ENGINEER")),
) -> SimulationState:
    engine.update_params(
        speed=payload.speed,
        tick_seconds=payload.tick_seconds,
        cloudiness=payload.cloudiness,
        solar_intensity=payload.solar_intensity,
        river_temperature=payload.river_temperature,
        ambient_temperature=payload.ambient_temperature,
        cooling_effectiveness=payload.cooling_effectiveness,
        mppt_algorithm=payload.mppt_algorithm,
        location=payload.location,
    )
    return SimulationState(**engine.state())


@router.post("/faults", response_model=SimulationState)
async def faults(
    payload: FaultCommand,
    _: User = Depends(require_min_role("ENGINEER")),
) -> SimulationState:
    if payload.fault not in FAULT_BITS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown fault")
    engine.set_fault(payload.fault, payload.enable)
    return SimulationState(**engine.state())


@router.post("/faults/clear", response_model=SimulationState)
async def clear_faults(_: User = Depends(require_min_role("ENGINEER"))) -> SimulationState:
    engine.clear_faults()
    return SimulationState(**engine.state())


@router.post("/scenario", response_model=SimulationState)
async def set_scenario(
    payload: dict,
    _: User = Depends(require_min_role("ENGINEER")),
) -> SimulationState:
    scenario = str(payload.get("scenario", "")).upper()
    if scenario not in SCENARIOS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"scenario must be one of {sorted(SCENARIOS)}")
    engine.set_scenario(scenario)
    return SimulationState(**engine.state())


@router.post("/demo", response_model=SimulationState)
async def demo(
    payload: dict,
    _: User = Depends(require_min_role("ENGINEER")),
) -> SimulationState:
    """One-click demo: force afternoon conditions and inject a fault pair."""
    enabled = bool(payload.get("enable", True))
    engine.demo_mode = enabled
    if enabled:
        engine.clear_faults()
        engine.cloudiness = 0.1
        engine.solar_intensity = 1.15
        engine.ambient_override = 34.0
        engine.river_temperature_override = 26.0
        engine.set_scenario("D")
        if not engine.running:
            engine.start()
    else:
        engine.cloudiness = 0.25
        engine.solar_intensity = 1.0
        engine.ambient_override = None
        engine.river_temperature_override = None
    return SimulationState(**engine.state())
