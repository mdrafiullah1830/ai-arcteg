"""Pytest fixtures: isolated temp database, app client, seeded admin token."""
from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

# Point the app at a throw-away SQLite file BEFORE importing app modules.
_TMP_DIR = tempfile.mkdtemp(prefix="arcteg_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DIR}/test.db"
os.environ["SIMULATION_AUTOSTART"] = "false"
os.environ["ENVIRONMENT"] = "test"
os.environ["JWT_SECRET"] = "test-secret-not-for-production"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import init_db  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.settings_store import ensure_defaults  # noqa: E402

ADMIN_EMAIL = "admin@test.local"
ADMIN_PASSWORD = "TestPass!123"


@pytest.fixture(scope="session", autouse=True)
def _setup_db() -> Generator[None, None, None]:
    init_db()
    ensure_defaults()
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == ADMIN_EMAIL).first() is None:
            db.add(
                User(
                    name="Test Admin",
                    email=ADMIN_EMAIL,
                    password_hash=hash_password(ADMIN_PASSWORD),
                    role="ADMIN",
                )
            )
            db.commit()
    finally:
        db.close()
    yield


@pytest.fixture(scope="session")
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def admin_token(client: TestClient) -> str:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture(scope="session")
def auth_headers(admin_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}
