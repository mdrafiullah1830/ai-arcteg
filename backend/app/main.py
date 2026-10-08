"""FastAPI application entrypoint.

Run with:  uvicorn app.main:app --reload  (from backend/)
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime as dt

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import settings
from app.core.database import init_db
from app.core.logging import configure_logging, get_logger
from app.models.user import User
from app.core.security import hash_password
from app.services.settings_store import ensure_defaults
from app.simulation.engine import engine

log = get_logger("main")

DESCRIPTION = """
Hybrid solar PV + TEG (thermoelectric generator) monitoring platform with a
physics-informed digital twin, ML forecasting and anomaly detection.

**Data honesty:** all telemetry carries a `data_source` label —
`LIVE_HARDWARE` for real sensor frames, `DIGITAL_TWIN`/`SIMULATED_DATA` for
the physics simulation. Nothing simulated is ever presented as real.
"""


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    init_db()
    ensure_defaults()
    _seed_admin()
    # Capture the main event loop so sync endpoints can schedule sim tasks.
    engine._loop = asyncio.get_running_loop()
    if settings.simulation_autostart:
        engine.start()
    log.info("%s started (env=%s)", settings.app_name, settings.environment)
    yield
    engine.stop()
    log.info("%s shutdown complete", settings.app_name)


def _seed_admin() -> None:
    """Create the default admin account on first boot."""
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == settings.default_admin_email).first():
            return
        db.add(
            User(
                name="Administrator",
                email=settings.default_admin_email,
                password_hash=hash_password(settings.default_admin_password),
                role="ADMIN",
            )
        )
        db.commit()
        log.info("Seeded default admin account (%s)", settings.default_admin_email)
    finally:
        db.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description=DESCRIPTION,
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        return {
            "app": settings.app_name,
            "docs": "/docs",
            "api": settings.api_v1_prefix,
            "health": f"{settings.api_v1_prefix}/system/health",
            "time": dt.datetime.now(dt.timezone.utc).isoformat(),
        }

    @app.websocket("/ws/live")
    async def websocket_live(websocket: WebSocket) -> None:
        from app.websocket.manager import manager

        await manager.connect(websocket)
        try:
            # Send an immediate snapshot so clients render right away.
            from app.services import queries
            from app.core.database import SessionLocal

            db = SessionLocal()
            try:
                latest = queries.latest_sample(db)
            finally:
                db.close()
            if latest:
                await websocket.send_json({"type": "telemetry", "data": latest})
            while True:
                # Clients may send pings; we just drain them.
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            await manager.disconnect(websocket)

    return app


app = create_app()
