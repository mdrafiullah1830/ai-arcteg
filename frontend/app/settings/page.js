"use client";

import { useEffect, useState } from "react";
import { api, getUser } from "../../lib/api";

const FIELDS = [
  ["simulation_speed", "Simulation speed (x)", "number", 0.1, 120],
  ["sampling_interval_seconds", "Sampling interval (s)", "number", 0.5, 300],
  ["hot_temperature_limit", "Hot limit (°C)", "number", 50, 250],
  ["cold_temperature_limit", "Cold limit (°C)", "number", 0, 100],
  ["max_power_w", "Max expected power (W)", "number", 1, 10000],
  ["anomaly_threshold", "Anomaly threshold", "number", 0.1, 1],
  ["data_retention_days", "Data retention (days)", "number", 1, 3650],
];

export default function SettingsPage() {
  const [settings, setSettings] = useState({});
  const [values, setValues] = useState({});
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [user, setUser] = useState(null);
  const [report, setReport] = useState(null);

  async function load() {
    try {
      const s = await api("/settings");
      setSettings(s);
      const v = {};
      Object.entries(s).forEach(([k, meta]) => {
        v[k] = meta.value;
      });
      setValues(v);
      setError("");
    } catch (err) {
      setError(String(err.message || err));
    }
  }

  useEffect(() => {
    setUser(getUser());
    load();
  }, []);

  async function save(e) {
    e.preventDefault();
    setMsg("");
    try {
      const body = {};
      FIELDS.forEach(([key]) => {
        if (values[key] !== undefined && values[key] !== null) body[key] = Number(values[key]);
      });
      if (values.mppt_algorithm) body.mppt_algorithm = values.mppt_algorithm;
      const res = await api("/settings", { method: "PUT", body });
      setMsg(res.detail || "Saved");
      await load();
    } catch (err) {
      setMsg(String(err.message || err));
    }
  }

  async function downloadPdf() {
    try {
      const token = localStorage.getItem("arcteg_token");
      const base = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000") + "/api/v1";
      const res = await fetch(`${base}/reports/pdf?hours=24`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`PDF failed: ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "arcteg_report.pdf";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setMsg(String(err.message || err));
    }
  }

  async function loadReport() {
    try {
      setReport(await api("/reports?hours=24"));
    } catch (err) {
      setMsg(String(err.message || err));
    }
  }

  const canEdit = user && user.role !== "VIEWER";

  return (
    <div>
      <div className="row">
        <div>
          <h1 className="page-title">Settings &amp; Reports</h1>
          <p className="page-sub">Runtime configuration + generated operations report</p>
        </div>
        <div className="spacer" />
        <button className="secondary" onClick={loadReport}>
          Preview report (JSON)
        </button>
        {canEdit && (
          <button className="secondary" onClick={downloadPdf}>
            Download PDF
          </button>
        )}
      </div>
      {error && <div className="error">{error}</div>}
      {msg && <div className="muted" style={{ marginBottom: 12 }}>{msg}</div>}

      <form className="card" onSubmit={save} style={{ marginBottom: 14 }}>
        <h3>Runtime settings</h3>
        <div className="grid cols-3">
          {FIELDS.map(([key, label, , min, max]) => (
            <div className="field" key={key}>
              <label>
                {label}
                <span className="muted"> — {settings[key]?.description || ""}</span>
              </label>
              <input
                type="number"
                step="any"
                min={min}
                max={max}
                value={values[key] ?? ""}
                onChange={(e) => setValues({ ...values, [key]: e.target.value })}
                disabled={!canEdit}
              />
            </div>
          ))}
          <div className="field">
            <label>MPPT algorithm</label>
            <select
              value={values.mppt_algorithm || "P&O"}
              onChange={(e) => setValues({ ...values, mppt_algorithm: e.target.value })}
              disabled={!canEdit}
            >
              <option value="P&O">P&amp;O</option>
              <option value="INC">INC</option>
            </select>
          </div>
        </div>
        <button type="submit" disabled={!canEdit}>
          Save settings
        </button>
      </form>

      {report && (
        <div className="card">
          <h3>Report preview — {report.title}</h3>
          <div className="grid cols-3">
            <div>
              <div className="muted">Energy today</div>
              <div className="stat-value" style={{ fontSize: 20 }}>
                {Number(report.energy.today_energy_wh).toFixed(2)} Wh
              </div>
            </div>
            <div>
              <div className="muted">Avg power</div>
              <div className="stat-value" style={{ fontSize: 20 }}>
                {Number(report.summary.avg_power_w).toFixed(3)} W
              </div>
            </div>
            <div>
              <div className="muted">Anomalies</div>
              <div className="stat-value" style={{ fontSize: 20 }}>
                {report.anomalies.total} ({report.anomalies.open} open)
              </div>
            </div>
          </div>
          <div className="muted" style={{ marginTop: 10, fontSize: 12 }}>
            Generated {new Date(report.generated_at).toLocaleString()} · data label: {report.data_label} ·
            ML trained: {String(report.ai.trained)}
          </div>
        </div>
      )}
    </div>
  );
}
