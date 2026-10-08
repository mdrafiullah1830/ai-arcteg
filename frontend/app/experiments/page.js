"use client";

import { useEffect, useState } from "react";
import { api, getUser } from "../../lib/api";

const SCENARIOS = [
  ["A", "Normal solar system"],
  ["B", "Solar + TEG"],
  ["C", "Solar + TEG + river cooling"],
  ["D", "Solar + TEG + adaptive cooling + AI"],
];

export default function ExperimentsPage() {
  const [items, setItems] = useState([]);
  const [scenarios, setScenarios] = useState([]);
  const [compare, setCompare] = useState(null);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ name: "", scenario: "D" });
  const [user, setUser] = useState(null);

  async function load() {
    try {
      const [list, sc, cmp] = await Promise.all([
        api("/experiments"),
        api("/experiments/scenarios"),
        api("/analytics/compare"),
      ]);
      setItems(list.items);
      setScenarios(sc.scenarios);
      setCompare(cmp);
      setError("");
    } catch (err) {
      setError(String(err.message || err));
    }
  }

  useEffect(() => {
    setUser(getUser());
    load();
  }, []);

  async function create(e) {
    e.preventDefault();
    try {
      await api("/experiments", { method: "POST", body: { ...form, config: {} } });
      setForm({ name: "", scenario: "D" });
      load();
    } catch (err) {
      setError(String(err.message || err));
    }
  }

  async function stop(id) {
    try {
      await api(`/experiments/${id}/stop`, { method: "POST" });
      load();
    } catch (err) {
      setError(String(err.message || err));
    }
  }

  const canControl = user && user.role !== "VIEWER";

  return (
    <div>
      <h1 className="page-title">Experiments</h1>
      <p className="page-sub">Scenario A/B/C/D research runs — compare energy &amp; thermal outcomes</p>
      {error && <div className="error">{error}</div>}

      <div className="grid cols-2" style={{ marginBottom: 14 }}>
        <div className="card">
          <h3>Runs</h3>
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Scenario</th>
                <th>Started</th>
                <th>Status</th>
                <th>Energy (Wh)</th>
                {canControl && <th />}
              </tr>
            </thead>
            <tbody>
              {items.map((e) => (
                <tr key={e.id}>
                  <td>{e.name}</td>
                  <td>
                    <span className="badge">{e.scenario}</span>
                  </td>
                  <td className="muted">{new Date(e.started_at).toLocaleString()}</td>
                  <td>
                    <span className={`badge ${e.status === "RUNNING" ? "warn" : "ok"}`}>{e.status}</span>
                  </td>
                  <td>{e.summary?.energy_wh != null ? Number(e.summary.energy_wh).toFixed(2) : "—"}</td>
                  {canControl && (
                    <td>
                      {e.status === "RUNNING" && (
                        <button className="secondary" onClick={() => stop(e.id)}>
                          Stop
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
              {!items.length && (
                <tr>
                  <td colSpan={6} className="muted">
                    No experiments yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <form className="card" onSubmit={create}>
          <h3>New experiment</h3>
          <div className="field">
            <label>Name</label>
            <input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="e.g. River cooling trial 2"
              required
            />
          </div>
          <div className="field">
            <label>Scenario</label>
            <select value={form.scenario} onChange={(e) => setForm({ ...form, scenario: e.target.value })}>
              {scenarios.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.id} — {s.label}
                </option>
              ))}
            </select>
          </div>
          <button type="submit" disabled={!canControl}>
            Start run
          </button>
          <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
            Starting a run switches the digital twin to that scenario.
          </div>
        </form>
      </div>

      <div className="card">
        <h3>Scenario comparison</h3>
        <table>
          <thead>
            <tr>
              <th>Scenario</th>
              <th>Label</th>
              <th>Runs</th>
              <th>Avg energy (Wh)</th>
              <th>Avg power (W)</th>
              <th>Note</th>
            </tr>
          </thead>
          <tbody>
            {(compare?.scenarios || []).map((s) => (
              <tr key={s.scenario}>
                <td>
                  <span className="badge">{s.scenario}</span>
                </td>
                <td>{s.label}</td>
                <td>{s.runs}</td>
                <td>{s.energy_wh != null ? Number(s.energy_wh).toFixed(2) : "—"}</td>
                <td>{s.avg_power_w != null ? Number(s.avg_power_w).toFixed(3) : "—"}</td>
                <td className="muted">{s.note || ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
