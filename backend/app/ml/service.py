"""ML pipeline: train gradient-boosting models from telemetry, serve predictions.

Models are trained on whatever telemetry exists (simulation or live) and stored
as joblib artifacts under ml/models. If no model exists, endpoints report
`available: false` with a clear reason instead of inventing numbers.
"""
from __future__ import annotations

import datetime as dt
import json
import threading
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor, IsolationForest
from sklearn.metrics import (
    accuracy_score,
    mean_absolute_error,
    r2_score,
)
from sklearn.model_selection import train_test_split

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.models.prediction import Prediction
from app.models.telemetry import SensorTelemetry

log = get_logger("ml")

MODEL_DIR = Path(settings.model_path)
MODEL_DIR.mkdir(parents=True, exist_ok=True)

FEATURES = [
    "irradiance",
    "ambient_temperature",
    "hot_temperature",
    "cold_temperature",
    "river_temperature",
    "pv_voltage",
    "battery_soc",
]

_lock = threading.Lock()
_state: dict[str, Any] = {
    "power_model": None,
    "thermal_model": None,
    "efficiency_model": None,
    "anomaly_model": None,
    "metrics": {},
    "trained_at": None,
    "data_label": None,
    "rows": 0,
}


def _load_artifacts() -> None:
    if not settings.model_autoload:
        return
    mapping = {
        "power_model": MODEL_DIR / "power_model.joblib",
        "thermal_model": MODEL_DIR / "thermal_model.joblib",
        "efficiency_model": MODEL_DIR / "efficiency_model.joblib",
        "anomaly_model": MODEL_DIR / "anomaly_model.joblib",
    }
    for key, path in mapping.items():
        if path.exists():
            try:
                _state[key] = joblib.load(path)
            except Exception:
                log.warning("Could not load %s", path)
    meta_path = MODEL_DIR / "metrics.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
            _state.update(meta)
        except Exception:
            pass


_load_artifacts()


def model_available() -> bool:
    return _state["power_model"] is not None


def model_status() -> dict[str, Any]:
    return {
        "trained": model_available(),
        "trained_at": _state.get("trained_at"),
        "data_label": _state.get("data_label"),
        "rows": _state.get("rows"),
        "metrics": _state.get("metrics", {}),
    }


def _fetch_dataframe(limit: int = 20000) -> tuple[pd.DataFrame, str]:
    db = SessionLocal()
    try:
        rows = (
            db.query(SensorTelemetry)
            .order_by(SensorTelemetry.timestamp.desc())
            .limit(limit)
            .all()
        )
        data = [
            {
                "timestamp": r.timestamp,
                "irradiance": r.irradiance,
                "ambient_temperature": r.ambient_temperature,
                "hot_temperature": r.hot_temperature,
                "cold_temperature": r.cold_temperature,
                "river_temperature": r.river_temperature,
                "pv_voltage": r.pv_voltage,
                "pv_current": r.pv_current,
                "pv_power": r.pv_power,
                "teg_power": r.teg_power,
                "battery_soc": r.battery_soc,
                "battery_voltage": r.battery_voltage,
                "system_efficiency": r.system_efficiency,
                "cooling_efficiency": r.cooling_efficiency,
                "delta_t": r.delta_t,
                "data_source": r.data_source,
            }
            for r in rows
        ]
    finally:
        db.close()
    df = pd.DataFrame(data)
    if df.empty:
        return df, "NO_DATA"
    label = "LIVE_HARDWARE" if (df["data_source"] == "LIVE_HARDWARE").all() else "SIMULATED_DATA"
    return df, label


def train() -> dict[str, Any]:
    """Train power / thermal / efficiency regressors + anomaly classifier."""
    with _lock:
        df, label = _fetch_dataframe()
        if len(df) < 50:
            return {
                "status": "insufficient_data",
                "metrics": {},
                "data_rows": len(df),
                "data_label": label,
            }

        df = df.sort_values("timestamp")
        df["total_power"] = df["pv_power"] + df["teg_power"]

        X = df[FEATURES]
        metrics: dict[str, Any] = {}

        # --- Power regression ------------------------------------------------
        y_power = df["total_power"]
        X_tr, X_te, y_tr, y_te = train_test_split(X, y_power, test_size=0.2, shuffle=False)
        power_model = GradientBoostingRegressor(random_state=42, n_estimators=120)
        power_model.fit(X_tr, y_tr)
        pred = power_model.predict(X_te)
        metrics["power"] = {
            "mae": round(float(mean_absolute_error(y_te, pred)), 4),
            "r2": round(float(r2_score(y_te, pred)), 4),
        }

        # --- Thermal regression (hot side) -----------------------------------
        y_th = df["hot_temperature"]
        X_tr, X_te, y_tr, y_te = train_test_split(X, y_th, test_size=0.2, shuffle=False)
        thermal_model = GradientBoostingRegressor(random_state=42, n_estimators=100)
        thermal_model.fit(X_tr, y_tr)
        pred = thermal_model.predict(X_te)
        metrics["thermal"] = {
            "mae": round(float(mean_absolute_error(y_te, pred)), 4),
            "r2": round(float(r2_score(y_te, pred)), 4),
        }

        # --- Efficiency regression -------------------------------------------
        y_eff = df["system_efficiency"]
        X_tr, X_te, y_tr, y_te = train_test_split(X, y_eff, test_size=0.2, shuffle=False)
        eff_model = GradientBoostingRegressor(random_state=42, n_estimators=100)
        eff_model.fit(X_tr, y_tr)
        pred = eff_model.predict(X_te)
        metrics["efficiency"] = {
            "mae": round(float(mean_absolute_error(y_te, pred)), 4),
            "r2": round(float(r2_score(y_te, pred)), 4),
        }

        # --- Anomaly classifier ----------------------------------------------
        # Label: rule-based envelope violations become the positive class.
        y_bad = (
            (df["hot_temperature"] > 95)
            | (df["battery_soc"] < 20)
            | (df["system_efficiency"] < 3.0)
            | (df["fault_state"] if "fault_state" in df else False)
        ).astype(int)
        if y_bad.nunique() > 1:
            # Time-ordered split (shuffle=False); stratify is incompatible with it.
            X_tr, X_te, y_tr, y_te = train_test_split(X, y_bad, test_size=0.2, shuffle=False)
            clf = GradientBoostingClassifier(random_state=42, n_estimators=80)
            clf.fit(X_tr, y_tr)
            metrics["anomaly"] = {
                "accuracy": round(float(accuracy_score(y_te, clf.predict(X_te))), 4),
                "positive_rate": round(float(y_bad.mean()), 4),
            }
            _state["anomaly_model"] = clf
            joblib.dump(clf, MODEL_DIR / "anomaly_model.joblib")
        else:
            metrics["anomaly"] = {"accuracy": None, "note": "single class in labels"}

        # IsolationForest for unsupervised scoring (used by anomaly service).
        iso = IsolationForest(contamination=0.05, random_state=42)
        iso.fit(X)
        _state["isolation_forest"] = iso
        joblib.dump(iso, MODEL_DIR / "isolation_forest.joblib")

        _state["power_model"] = power_model
        _state["thermal_model"] = thermal_model
        _state["efficiency_model"] = eff_model
        _state["metrics"] = metrics
        _state["trained_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        _state["data_label"] = label
        _state["rows"] = int(len(df))

        joblib.dump(power_model, MODEL_DIR / "power_model.joblib")
        joblib.dump(thermal_model, MODEL_DIR / "thermal_model.joblib")
        joblib.dump(eff_model, MODEL_DIR / "efficiency_model.joblib")
        (MODEL_DIR / "metrics.json").write_text(
            json.dumps(
                {
                    "trained_at": _state["trained_at"],
                    "data_label": label,
                    "rows": int(len(df)),
                    "metrics": metrics,
                },
                indent=2,
            )
        )

        log.info("Trained ML models on %d rows (%s)", len(df), label)
        return {"status": "trained", "metrics": metrics, "data_rows": int(len(df)), "data_label": label}


def predict_latest(horizon_minutes: int = 5) -> dict[str, Any] | None:
    """Predict power/thermal/efficiency for the newest telemetry row."""
    if not model_available():
        return None
    df, _ = _fetch_dataframe(limit=1)
    if df.empty:
        return None
    row = df.iloc[0]
    X = pd.DataFrame([{f: float(row[f]) for f in FEATURES}])
    try:
        power = float(_state["power_model"].predict(X)[0])
        hot = float(_state["thermal_model"].predict(X)[0])
        eff = float(_state["efficiency_model"].predict(X)[0])
    except Exception:
        return None
    cold = float(row["cold_temperature"])
    delta_t = max(0.0, hot - cold)
    metrics = _state.get("metrics", {})
    r2 = metrics.get("power", {}).get("r2")
    confidence = round(max(0.0, min(1.0, r2 if r2 is not None else 0.5)), 3)
    return {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "kind": "power+thermal+efficiency",
        "horizon_minutes": horizon_minutes,
        "predicted_power": round(power, 3),
        "predicted_hot_temperature": round(hot, 2),
        "predicted_cold_temperature": round(cold, 2),
        "predicted_delta_t": round(delta_t, 2),
        "predicted_efficiency": round(eff, 3),
        "confidence": confidence,
        "model_name": "GradientBoostingRegressor",
        "data_source": _state.get("data_label") or "SIMULATED_DATA",
    }


def store_prediction(result: dict[str, Any], device_id: int | None = None) -> None:
    if not result:
        return
    db = SessionLocal()
    try:
        db.add(
            Prediction(
                timestamp=dt.datetime.fromisoformat(result["timestamp"]),
                kind="combined",
                horizon_minutes=result.get("horizon_minutes", 5),
                predicted_power=result.get("predicted_power"),
                predicted_hot_temperature=result.get("predicted_hot_temperature"),
                predicted_cold_temperature=result.get("predicted_cold_temperature"),
                predicted_delta_t=result.get("predicted_delta_t"),
                predicted_efficiency=result.get("predicted_efficiency"),
                confidence=result.get("confidence"),
                model_name=result.get("model_name", "unavailable"),
                data_source=result.get("data_source", "SIMULATED_DATA"),
            )
        )
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def recommendations(sample: dict | None, pred: dict | None) -> list[dict[str, Any]]:
    """Plain rule-driven advisory messages (no invented data)."""
    out: list[dict[str, Any]] = []
    if not sample:
        return [{"level": "info", "title": "No telemetry", "detail": "Start the simulation or ingest hardware data."}]

    if sample.get("delta_t", 0) < 8 and sample.get("irradiance", 0) > 300:
        out.append({
            "level": "warning",
            "title": "Low ΔT despite sunlight",
            "detail": "Hot/cold side difference is small — check concentrator alignment and cooling loop.",
        })
    if sample.get("hot_temperature", 0) > 95:
        out.append({
            "level": "critical",
            "title": "Hot side approaching limit",
            "detail": "Increase cooling effectiveness or shed TEG load to protect the module.",
        })
    if sample.get("battery_soc", 100) < 25:
        out.append({
            "level": "warning",
            "title": "Battery state of charge low",
            "detail": "Prioritize charging; defer non-critical loads.",
        })
    if 0 < sample.get("system_efficiency", 0) < 4 and sample.get("irradiance", 0) > 400:
        out.append({
            "level": "warning",
            "title": "System efficiency degraded",
            "detail": "Inspect PV mismatch, MPPT tracking, and wiring losses.",
        })
    if pred and pred.get("predicted_hot_temperature", 0) > 110:
        out.append({
            "level": "critical",
            "title": "Thermal runaway predicted",
            "detail": f"Model forecasts {pred['predicted_hot_temperature']:.1f} C hot-side within {pred.get('horizon_minutes', 5)} min.",
        })
    if not out:
        out.append({
            "level": "info",
            "title": "Operating normally",
            "detail": "All parameters within expected bands for the current scenario.",
        })
    return out


def ai_insights(sample: dict | None, pred: dict | None) -> dict[str, Any]:
    status = model_status()
    if not model_available():
        return {
            "available": False,
            "reason": "Model not trained yet. POST /api/v1/ai/train to fit on current telemetry.",
            "recommendations": recommendations(sample, pred),
            "model_metrics": status,
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
    return {
        "available": True,
        "predicted_power_w": pred.get("predicted_power") if pred else None,
        "power_confidence": pred.get("confidence") if pred else None,
        "predicted_hot_c": pred.get("predicted_hot_temperature") if pred else None,
        "predicted_cold_c": pred.get("predicted_cold_temperature") if pred else None,
        "predicted_delta_t": pred.get("predicted_delta_t") if pred else None,
        "predicted_efficiency_pct": pred.get("predicted_efficiency") if pred else None,
        "recommendations": recommendations(sample, pred),
        "model_metrics": status,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
