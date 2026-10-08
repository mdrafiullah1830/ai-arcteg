"use client";

import { useEffect, useState } from "react";
import { api, getUser } from "../../lib/api";

const FAULTS = [
  "sensor_failure",
  "overheating",
  "low_irradiance",
  "cooling_degradation",
  "voltage_spike",
  "comm_failure",
];

const SCENARIOS = [
  ["A", "Normal solar system"],
  ["B", "Solar + TEG"],
  ["C", "Solar + TEG + river cooling"],
  ["D", "Solar + TEG + adaptive cooling + AI"],
];

export default function SimulationPage() {
  const [state, setState] = useState(null);
  const [error, setError] = useState("");
  const [user, setUser] = useState(null);
  const [params, setParams] = useState({
    speed: 1,
    cloudiness: 0.25,
    solar_intensity: 1,
    cooling_effectiveness: 0.7,
    mppt_algorithm: "P&O",
  });

  const canControl = user && user.role !== "VIEWER";

  async function load() {
    try {
      setState(await api("/simulation/state"));
      setError("");
    } catch (err) {
      setError(String(err.message || err));
    }
  }

  useEffect(() => {
    setUser(getUser());
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  async function command(action) {
    try {
      setState(await api("/simulation/command", { method: "POST", body: { action } }));
    } catch (err) {
      setError(String(err.message || err));
    }
  }

  async function setFault(fault, enable) {
    try {
      setState(await api("/simulation/faults", { method: "POST", body: { fault, enable } }));
    } catch (err) {
      setError(String(err.message || err));
    }
  }

  async function applyParams(e) {
    e.preventDefault();
    try {
      setState(await api("/simulation/params", { method: "POST", body: params }));
    } catch (err) {
      setError(String(err.message || err));
    }
  }

  async function setScenario(s) {
    try {
      setState(await api("/simulation/scenario", { method: "POST", body: { scenario: s } }));
    } catch (err) {
      setError(String(err.message || err));
    }
  }

  return (
    <div>
      <h1 className="page-title">Simulation (Digital Twin)</h1>
      <p className="page-sub">Physics-informed model — clearly labelled as simulated data</p>
      {error && <div className="error">{error}</div>}

      <div className="grid cols-4" style={{ marginBottom: 14 }}>
        <div className="card">
          <h3>Status</h3>
          <div className="stat-value" style={{ color: state?.running ? "#34d399" : "#8ea0bf" }}>
            {state ? (state.running ? (state.paused ? "Paused" : "Running") : "Stopped") : "…"}
          </div>
          <div className="muted" style={{ marginTop: 6 }}>
            ticks {state?.ticks ?? 0} · {state?.speed ?? 1}x · {state?.tick_seconds ?? 5}s/tick
          </div>
        </div>
        <div className="card">
          <h3>Scenario</h3>
          <div className="stat-value" style={{ fontSize: 20 }}>
            {state?.scenario || "—"}
          </div>
          <div className="muted" style={{ marginTop: 6 }}>
            {state?.params?.scenario_label || ""}
          </div>
        </div>
        <div className="card">
          <h3>Active faults</h3>
          {state?.faults?.length ? (
            state.faults.map((f) => (
              <span key={f} className="badge crit" style={{ marginRight: 6 }}>
                {f}
              </span>
            ))
          ) : (
            <span className="badge ok">none</span>
          )}
        </div>
        <div className="card">
          <h3>Controls</h3>
          <div className="row">
            <button disabled={!canControl || state?.running} onClick={() => command("start")}>
              Start
            </button>
            <button
              className="secondary"
              disabled={!canControl || !state?.running}
              onClick={() => command(state?.paused ? "resume" : "pause")}
            >
              {state?.paused ? "Resume" : "Pause"}
            </button>
            <button className="danger" disabled={!canControl || !state?.running} onClick={() => command("stop")}>
              Stop
            </button>
          </div>
        </div>
      </div>

      <div className="grid cols-2">
        <form className="card" onSubmit={applyParams}>
          <h3>Parameters</h3>
          <div className="grid cols-2">
            <div className="field">
              <label>Speed ({params.speed}x)</label>
              <input
                type="number"
                step="0.1"
                min="0.1"
                max="120"
                value={params.speed}
                onChange={(e) => setParams({ ...params, speed: Number(e.target.value) })}
              />
            </div>
            <div className="field">
              <label>Cloudiness ({params.cloudiness})</label>
              <input
                type="number"
                step="0.05"
                min="0"
                max="1"
                value={params.cloudiness}
                onChange={(e) => setParams({ ...params, cloudiness: Number(e.target.value) })}
              />
            </div>
            <div className="field">
              <label>Solar intensity ({params.solar_intensity})</label>
              <input
                type="number"
                step="0.05"
                min="0.2"
                max="1.5"
                value={params.solar_intensity}
                onChange={(e) => setParams({ ...params, solar_intensity: Number(e.target.value) })}
              />
            </div>
            <div className="field">
              <label>Cooling effectiveness ({params.cooling_effectiveness})</label>
              <input
                type="number"
                step="0.05"
                min="0"
                max="1"
                value={params.cooling_effectiveness}
                onChange={(e) => setParams({ ...params, cooling_effectiveness: Number(e.target.value) })}
              />
            </div>
            <div className="field">
              <label>MPPT algorithm</label>
              <select
                value={params.mppt_algorithm}
                onChange={(e) => setParams({ ...params, mppt_algorithm: e.target.value })}
              >
                <option value="P&O">P&amp;O</option>
                <option value="INC">INC</option>
              </select>
            </div>
          </div>
          <button type="submit" disabled={!canControl}>
            Apply parameters
          </button>
        </form>

        <div className="card">
          <h3>Scenario (research mode)</h3>
          <div className="grid" style={{ gap: 8 }}>
            {SCENARIOS.map(([id, label]) => (
              <button
                key={id}
                className={state?.scenario === id ? "" : "secondary"}
                disabled={!canControl}
                onClick={() => setScenario(id)}
              >
                {id} — {label}
              </button>
            ))}
          </div>

          <h3 style={{ marginTop: 18 }}>Fault injection (testing)</h3>
          <div className="row">
            {FAULTS.map((f) => {
              const active = state?.faults?.includes(f);
              return (
                <button
                  key={f}
                  className={active ? "danger" : "secondary"}
                  disabled={!canControl}
                  onClick={() => setFault(f, !active)}
                >
                  {f}
                </button>
              );
            })}
            <button
              className="secondary"
              disabled={!canControl}
              onClick={() => api("/simulation/faults/clear", { method: "POST" }).then(load)}
            >
              Clear all
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
