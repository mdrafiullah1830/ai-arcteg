"use client";

import { useEffect, useState } from "react";
import { api, getUser } from "../../lib/api";

export default function AiPage() {
  const [insights, setInsights] = useState(null);
  const [model, setModel] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [user, setUser] = useState(null);

  async function load() {
    try {
      const [i, m] = await Promise.all([api("/ai/insights"), api("/ai/model")]);
      setInsights(i);
      setModel(m);
      setError("");
    } catch (err) {
      setError(String(err.message || err));
    }
  }

  useEffect(() => {
    setUser(getUser());
    load();
    const id = setInterval(load, 20000);
    return () => clearInterval(id);
  }, []);

  async function train() {
    setBusy(true);
    setMsg("");
    try {
      const res = await api("/ai/train", { method: "POST" });
      setMsg(
        res.status === "trained"
          ? `Trained on ${res.data_rows} rows (${res.data_label}) — power R²=${res.metrics?.power?.r2}`
          : `Not enough data (${res.data_rows} rows). Start the simulation first.`,
      );
      await load();
    } catch (err) {
      setMsg(String(err.message || err));
    } finally {
      setBusy(false);
    }
  }

  const levelBadge = (level) =>
    level === "critical" ? "crit" : level === "warning" ? "warn" : "ok";

  return (
    <div>
      <div className="row">
        <div>
          <h1 className="page-title">AI / ML</h1>
          <p className="page-sub">Forecasting + recommendations from GradientBoosting models</p>
        </div>
        <div className="spacer" />
        {user && user.role !== "VIEWER" && (
          <button disabled={busy} onClick={train}>
            {busy ? "Training…" : "Train models"}
          </button>
        )}
      </div>
      {error && <div className="error">{error}</div>}
      {msg && <div className="muted" style={{ marginBottom: 12 }}>{msg}</div>}

      <div className="grid cols-4" style={{ marginBottom: 14 }}>
        <div className="card">
          <h3>Predicted power</h3>
          <div className="stat-value">
            {insights?.predicted_power_w != null ? Number(insights.predicted_power_w).toFixed(2) : "—"}
            <span className="stat-unit">W</span>
          </div>
          <div className="muted">
            confidence {insights?.power_confidence != null ? Number(insights.power_confidence).toFixed(3) : "—"}
          </div>
        </div>
        <div className="card">
          <h3>Hot side (forecast)</h3>
          <div className="stat-value">
            {insights?.predicted_hot_c != null ? Number(insights.predicted_hot_c).toFixed(1) : "—"}
            <span className="stat-unit">°C</span>
          </div>
          <div className="muted">ΔT {insights?.predicted_delta_t != null ? Number(insights.predicted_delta_t).toFixed(1) : "—"} K</div>
        </div>
        <div className="card">
          <h3>Efficiency (forecast)</h3>
          <div className="stat-value">
            {insights?.predicted_efficiency_pct != null ? Number(insights.predicted_efficiency_pct).toFixed(1) : "—"}
            <span className="stat-unit">%</span>
          </div>
        </div>
        <div className="card">
          <h3>Model</h3>
          <div className="stat-value" style={{ fontSize: 20, color: model?.trained ? "#34d399" : "#fbbf24" }}>
            {model?.trained ? "Trained" : "Untrained"}
          </div>
          <div className="muted">{model?.trained_at ? new Date(model.trained_at).toLocaleString() : "no artifacts"}</div>
        </div>
      </div>

      {!insights?.available && insights?.reason && (
        <div className="card" style={{ marginBottom: 14 }}>
          <span className="badge warn">Model unavailable</span> <span className="muted">{insights.reason}</span>
        </div>
      )}

      <div className="grid cols-2">
        <div className="card">
          <h3>Recommendations</h3>
          {(insights?.recommendations || []).map((r, i) => (
            <div key={i} className="row" style={{ marginBottom: 8, alignItems: "flex-start" }}>
              <span className={`badge ${levelBadge(r.level)}`}>{r.level}</span>
              <div>
                <div style={{ fontWeight: 600 }}>{r.title}</div>
                <div className="muted" style={{ fontSize: 12 }}>{r.detail}</div>
              </div>
            </div>
          ))}
        </div>
        <div className="card">
          <h3>Model metrics</h3>
          <table>
            <thead>
              <tr>
                <th>Model</th>
                <th>Metric</th>
                <th>Value</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(model?.metrics || {}).flatMap(([name, metrics]) =>
                Object.entries(metrics).map(([k, v]) => (
                  <tr key={`${name}-${k}`}>
                    <td>{name}</td>
                    <td className="muted">{k}</td>
                    <td>{String(v)}</td>
                  </tr>
                )),
              )}
              {!Object.keys(model?.metrics || {}).length && (
                <tr>
                  <td colSpan={3} className="muted">
                    No metrics — train the model first.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
