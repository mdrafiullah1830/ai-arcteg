"use client";

import { useEffect, useState } from "react";
import { api, getUser } from "../../lib/api";

export default function AnomaliesPage() {
  const [summary, setSummary] = useState(null);
  const [items, setItems] = useState([]);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("");
  const [user, setUser] = useState(null);

  async function load() {
    try {
      const q = filter ? `?status=${filter}&limit=100` : "?limit=100";
      const [s, l] = await Promise.all([api("/anomalies/summary"), api(`/anomalies${q}`)]);
      setSummary(s);
      setItems(l.items);
      setError("");
    } catch (err) {
      setError(String(err.message || err));
    }
  }

  useEffect(() => {
    setUser(getUser());
    load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, [filter]);

  async function setStatus(id, status) {
    try {
      await api(`/anomalies/${id}`, { method: "PATCH", body: { status } });
      load();
    } catch (err) {
      setError(String(err.message || err));
    }
  }

  const badge = (sev) => (sev === "CRITICAL" ? "crit" : sev === "WARNING" ? "warn" : "ok");

  return (
    <div>
      <div className="row">
        <div>
          <h1 className="page-title">Anomalies</h1>
          <p className="page-sub">Rule-based + ML detector findings with dedup windows</p>
        </div>
        <div className="spacer" />
        <select style={{ width: 170 }} value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">All statuses</option>
          <option value="OPEN">Open</option>
          <option value="ACK">Acknowledged</option>
          <option value="RESOLVED">Resolved</option>
        </select>
      </div>
      {error && <div className="error">{error}</div>}

      <div className="grid cols-4" style={{ marginBottom: 14 }}>
        <div className="card">
          <h3>Open</h3>
          <div className="stat-value">{summary?.open ?? 0}</div>
        </div>
        <div className="card">
          <h3>Warning</h3>
          <div className="stat-value" style={{ color: "#fbbf24" }}>{summary?.warning ?? 0}</div>
        </div>
        <div className="card">
          <h3>Critical</h3>
          <div className="stat-value" style={{ color: "#f87171" }}>{summary?.critical ?? 0}</div>
        </div>
        <div className="card">
          <h3>Total</h3>
          <div className="stat-value">{summary?.total ?? 0}</div>
        </div>
      </div>

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Severity</th>
              <th>Parameter</th>
              <th>Observed</th>
              <th>Expected</th>
              <th>Score</th>
              <th>Detector</th>
              <th>Message</th>
              <th>Status</th>
              {user && user.role !== "VIEWER" && <th />}
            </tr>
          </thead>
          <tbody>
            {items.map((a) => (
              <tr key={a.id}>
                <td className="muted">{new Date(a.timestamp).toLocaleString()}</td>
                <td>
                  <span className={`badge ${badge(a.severity)}`}>{a.severity}</span>
                </td>
                <td>{a.parameter}</td>
                <td>{a.observed_value}</td>
                <td className="muted">{a.expected_value}</td>
                <td>{a.anomaly_score}</td>
                <td className="muted">{a.detector}</td>
                <td style={{ maxWidth: 320 }}>{a.message}</td>
                <td>{a.status}</td>
                {user && user.role !== "VIEWER" && (
                  <td>
                    <div className="row" style={{ gap: 6 }}>
                      {a.status === "OPEN" && (
                        <button className="secondary" onClick={() => setStatus(a.id, "ACK")}>
                          Ack
                        </button>
                      )}
                      {a.status !== "RESOLVED" && (
                        <button className="secondary" onClick={() => setStatus(a.id, "RESOLVED")}>
                          Resolve
                        </button>
                      )}
                    </div>
                  </td>
                )}
              </tr>
            ))}
            {!items.length && (
              <tr>
                <td colSpan={10} className="muted">
                  No anomalies match this filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
