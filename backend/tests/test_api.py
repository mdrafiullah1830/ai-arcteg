"""Telemetry, devices, ingest, simulation and ML endpoint behaviour."""
from __future__ import annotations

import time

from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    resp = client.get("/api/v1/system/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["database"] == "up"
    assert body["ml"] in {"trained", "untrained"}


def test_system_info(client: TestClient) -> None:
    body = client.get("/api/v1/system/info").json()
    assert body["app"] == "AI-ARCTEG"
    assert "Dhaka" in body["locations"]


def test_device_crud(client: TestClient, auth_headers: dict) -> None:
    create = client.post(
        "/api/v1/devices",
        headers=auth_headers,
        json={"device_uid": "hw-001", "device_name": "Field Unit", "is_simulated": False},
    )
    assert create.status_code == 201, create.text
    device_id = create.json()["id"]

    dup = client.post(
        "/api/v1/devices",
        headers=auth_headers,
        json={"device_uid": "hw-001", "device_name": "Field Unit"},
    )
    assert dup.status_code == 409

    listing = client.get("/api/v1/devices").json()
    assert any(d["device_uid"] == "hw-001" for d in listing["items"])

    patched = client.patch(
        f"/api/v1/devices/{device_id}",
        headers=auth_headers,
        json={"location": "Chattogram"},
    )
    assert patched.status_code == 200
    assert patched.json()["location"] == "Chattogram"

    deleted = client.delete(f"/api/v1/devices/{device_id}", headers=auth_headers)
    assert deleted.status_code == 200
    assert client.get(f"/api/v1/devices/{device_id}").status_code == 404


def test_ingest_requires_api_key(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/ingest/telemetry",
        json={
            "device_uid": "hw-002",
            "irradiance": 500,
            "ambient_temperature": 30,
            "hot_temperature": 60,
            "cold_temperature": 30,
            "river_temperature": 25,
            "pv_voltage": 18,
            "pv_current": 2,
            "teg_voltage": 1.2,
            "teg_current": 0.3,
        },
    )
    assert resp.status_code == 401


def test_ingest_and_telemetry_flow(client: TestClient) -> None:
    from app.core.config import settings

    frame = {
        "device_uid": "hw-002",
        "irradiance": 850,
        "ambient_temperature": 31,
        "hot_temperature": 78,
        "cold_temperature": 33,
        "river_temperature": 26,
        "pv_voltage": 17.5,
        "pv_current": 2.4,
        "teg_voltage": 1.9,
        "teg_current": 0.35,
        "battery_voltage": 12.7,
        "battery_soc": 88,
    }
    resp = client.post(
        "/api/v1/ingest/telemetry",
        json=frame,
        headers={"X-API-Key": settings.device_ingest_api_key},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True

    current = client.get("/api/v1/telemetry/current")
    assert current.status_code == 200
    body = current.json()
    assert body["data_source"] in {"LIVE_HARDWARE", "DIGITAL_TWIN", "SIMULATED_DATA"}
    assert "total_power" in body

    series = client.get(
        "/api/v1/telemetry/series?parameter=total_power&hours=24&resolution=1m"
    )
    assert series.status_code == 200
    assert series.json()["count"] >= 1


def test_sim_start_stop(client: TestClient, auth_headers: dict) -> None:
    start = client.post(
        "/api/v1/simulation/command", headers=auth_headers, json={"action": "start"}
    )
    assert start.status_code == 200, start.text
    assert start.json()["running"] is True

    state = client.get("/api/v1/simulation/state").json()
    assert state["running"] is True

    stop = client.post(
        "/api/v1/simulation/command", headers=auth_headers, json={"action": "stop"}
    )
    assert stop.status_code == 200
    assert stop.json()["running"] is False


def test_sim_faults(client: TestClient, auth_headers: dict) -> None:
    client.post("/api/v1/simulation/command", headers=auth_headers, json={"action": "start"})
    enable = client.post(
        "/api/v1/simulation/faults",
        headers=auth_headers,
        json={"fault": "overheating", "enable": True},
    )
    assert enable.status_code == 200
    assert "overheating" in enable.json()["faults"]

    bad = client.post(
        "/api/v1/simulation/faults",
        headers=auth_headers,
        json={"fault": "not_a_fault", "enable": True},
    )
    assert bad.status_code == 422

    cleared = client.post(
        "/api/v1/simulation/faults/clear", headers=auth_headers
    )
    assert cleared.json()["faults"] == []
    client.post("/api/v1/simulation/command", headers=auth_headers, json={"action": "stop"})


def test_sim_requires_engineer(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/simulation/command", json={"action": "start"}
    )
    assert resp.status_code == 401


def test_mppt_endpoints(client: TestClient) -> None:
    state = client.get("/api/v1/mppt/state")
    assert state.status_code == 200
    assert state.json()["algorithm"] in {"P&O", "INC"}
    assert 0 <= state.json()["tracking_efficiency"] <= 100

    curve = client.get("/api/v1/mppt/pv-curve").json()
    assert len(curve["voltage"]) == 40
    assert curve["mpp_power"] > 0


def test_analytics(client: TestClient) -> None:
    stats = client.get("/api/v1/analytics/stats?parameter=irradiance&hours=24")
    assert stats.status_code == 200
    assert stats.json()["count"] >= 0

    corr = client.get("/api/v1/analytics/correlation?a=irradiance&b=pv_power")
    assert corr.status_code == 200
    body = corr.json()
    assert body["pair"] == ["irradiance", "pv_power"]
    assert -1.0 <= body["pearson_r"] <= 1.0


def test_energy_and_thermal(client: TestClient) -> None:
    assert client.get("/api/v1/energy/summary").status_code == 200
    assert client.get("/api/v1/energy/series?hours=24").status_code == 200
    assert client.get("/api/v1/thermal/current").status_code == 200


def test_ml_train_and_predict(client: TestClient, auth_headers: dict) -> None:
    # Generate enough rows for training via ingest + simulation.
    from app.core.config import settings

    client.post("/api/v1/simulation/command", headers=auth_headers, json={"action": "start"})
    deadline = time.time() + 30
    rows_ok = False
    while time.time() < deadline:
        resp = client.get("/api/v1/telemetry/current")
        if resp.status_code == 200:
            rows_ok = True
            break
        time.sleep(1)
    client.post("/api/v1/simulation/command", headers=auth_headers, json={"action": "stop"})
    assert rows_ok, "telemetry never appeared"

    train = client.post("/api/v1/ai/train", headers=auth_headers)
    assert train.status_code == 200, train.text
    body = train.json()
    assert body["status"] in {"trained", "insufficient_data"}
    if body["status"] == "trained":
        assert body["metrics"]["power"]["r2"] > 0.5

        model = client.get("/api/v1/ai/model").json()
        assert model["trained"] is True

        insights = client.get("/api/v1/ai/insights").json()
        assert insights["available"] is True
        assert isinstance(insights["recommendations"], list)

        predict = client.post("/api/v1/ai/predict", params={"horizon_minutes": 5})
        assert predict.status_code == 200
        assert predict.json()["confidence"] is not None


def test_reports(client: TestClient, auth_headers: dict) -> None:
    resp = client.get("/api/v1/reports?hours=24")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("summary", "energy", "thermal", "mppt", "anomalies", "ai", "series"):
        assert key in body

    pdf = client.get("/api/v1/reports/pdf?hours=24", headers=auth_headers)
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")


def test_settings_roundtrip(client: TestClient, auth_headers: dict) -> None:
    initial = client.get("/api/v1/settings").json()
    assert "simulation_speed" in initial

    update = client.put(
        "/api/v1/settings",
        headers=auth_headers,
        json={"anomaly_threshold": 0.75},
    )
    assert update.status_code == 200

    after = client.get("/api/v1/settings").json()
    assert after["anomaly_threshold"]["value"] == 0.75


def test_anomalies_endpoints(client: TestClient, auth_headers: dict) -> None:
    listing = client.get("/api/v1/anomalies?limit=5")
    assert listing.status_code == 200
    assert "items" in listing.json()

    summary = client.get("/api/v1/anomalies/summary")
    assert summary.status_code == 200
    assert set(summary.json()) == {"open", "warning", "critical", "total", "recent"}


def test_experiments_flow(client: TestClient, auth_headers: dict) -> None:
    scenarios = client.get("/api/v1/experiments/scenarios").json()["scenarios"]
    assert {s["id"] for s in scenarios} == {"A", "B", "C", "D"}

    created = client.post(
        "/api/v1/experiments",
        headers=auth_headers,
        json={"name": "Unit test run", "scenario": "C", "config": {"k": 1}},
    )
    assert created.status_code == 201, created.text
    exp_id = created.json()["id"]
    assert created.json()["status"] == "RUNNING"

    bad = client.post(
        "/api/v1/experiments",
        headers=auth_headers,
        json={"name": "bad", "scenario": "Z"},
    )
    assert bad.status_code == 422

    stopped = client.post(f"/api/v1/experiments/{exp_id}/stop", headers=auth_headers)
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "COMPLETED"
    assert "energy_wh" in stopped.json()["summary"]

    again = client.post(f"/api/v1/experiments/{exp_id}/stop", headers=auth_headers)
    assert again.status_code == 409

    client.delete(f"/api/v1/experiments/{exp_id}", headers=auth_headers)


def test_data_source_endpoint(client: TestClient) -> None:
    body = client.get("/api/v1/telemetry/data-source").json()
    assert body["data_source"]
    assert isinstance(body["simulated"], bool)
    assert body["label"]
