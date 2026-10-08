"""v1 API router aggregation. All /api/v1 endpoints mount from here."""
from fastapi import APIRouter

from app.api.v1 import (
    ai,
    analytics,
    anomalies,
    auth,
    devices,
    experiments,
    ingest,
    reports,
    simulation,
    system,
    telemetry,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(system.router)
api_router.include_router(devices.router)
api_router.include_router(telemetry.router)
api_router.include_router(ingest.router)
api_router.include_router(ai.router)
api_router.include_router(anomalies.router)
api_router.include_router(analytics.router)
api_router.include_router(experiments.router)
api_router.include_router(simulation.router)
api_router.include_router(reports.router)

__all__ = ["api_router"]
