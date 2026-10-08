"""Auth flow: register, login, role enforcement, duplicate handling."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_login_success(client: TestClient, admin_token: str) -> None:
    assert admin_token


def test_login_wrong_password(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.local", "password": "wrong-password"},
    )
    assert resp.status_code == 401


def test_me_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_with_token(client: TestClient, auth_headers: dict) -> None:
    resp = client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["role"] == "ADMIN"


def test_register_and_duplicate(client: TestClient) -> None:
    payload = {
        "name": "Engineer One",
        "email": "engineer1@test.local",
        "password": "Engineer!123",
        "role": "ENGINEER",
    }
    resp = client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    assert resp.json()["access_token"]

    dup = client.post("/api/v1/auth/register", json=payload)
    assert dup.status_code == 409


def test_register_rejects_bad_email(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/auth/register",
        json={"name": "X Y", "email": "not-an-email", "password": "LongPass!1", "role": "VIEWER"},
    )
    assert resp.status_code == 422


def test_users_admin_only(client: TestClient) -> None:
    assert client.get("/api/v1/users").status_code == 401


def test_users_list(client: TestClient, auth_headers: dict) -> None:
    resp = client.get("/api/v1/users", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
