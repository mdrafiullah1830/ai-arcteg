"use client";

import { useEffect, useState } from "react";
import LineChart from "../components/LineChart";
import { api, WS_BASE } from "../lib/api";

export default function Dashboard() {
  const [live, setLive] = useState(null);
  const [energy, setEnergy] = useState(null);
  const [powerSeries, setPowerSeries] = useState([]);
  const [thermalSeries, setThermalSeries] = useState([]);
  const [source, setSource] = useState(null);
  const [health, setHealth] = useState(null);
  const [error, setError] = useState("");

  // Poll slow-moving endpoints.
  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const [e, s, p, t, h] = await Promise.all([
          api("/energy/summary"),
          api("/telemetry/data-source"),
          api("/telemetry/series?parameter=total_power&hours=12&resolution=15m"),
          api("/telemetry/series?parameter=delta_t&hours=12&resolution=15m"),
          api("/system/health"),
        ]);
        if (!alive) return;
        setEnergy(e);
        setSource(s);
        setPowerSeries(p.points || []);
        setThermalSeries(t.points || []);
        setHealth(h);
        setError("");
      } catch (err) {
        if (alive) setError(String(err.message || err));
      }
    }
    load();
    const id = setInterval(load, 15000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  // Live telemetry over WebSocket, with polling fallback.
  useEffect(() => {
    let ws = null;
    let poll = null;
    async function pollOnce() {
      try {
        setLive(await api("/telemetry/current"));
      } catch {
        /* server not ready */
      }
    }
    try {
      ws = new WebSocket(`${WS_BASE}/ws/live`);
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === "telemetry") setLive(msg.data);
        } catch {
          /* ignore malformed frames */
        }
      };
      ws.onerror = () => pollOnce();
    } catch {
      pollOnce();
    }
    poll = setInterval(pollOnce, 8000);
    pollOnce();
    return () => {
      if (ws) ws.close();
      clearInterval(poll);
    };
  }, []);

  const stat = (label, value, unit, cls) => (
    <div className="card">
      <h3>{label}</h3>
      <div className="stat-value" style={cls ? { color: cls } : undefined}>
        {value}
        <span className="stat-unit">{unit}</span>
      </div>
    </div>
  );

  const fmt = (v, d = 1) => (v === undefined || v === null ? "—" : Number(v).toFixed(d));

  return (
    <div>
      <div className="row">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="page-sub">Hybrid PV + TEG system — live overview</p>
        </div>
        <div className="spacer" />
        {source && (
          <span className={`badge ${source.simulated ? "warn" : "ok"}`}>{source.label}</span>
        )}
        {health && (
          <span className={`badge ${health.status === "up" ? "ok" : "crit"}`}>
            API {health.status} · ML {health.ml} · SIM {health.simulation}
          </span>
        )}
      </div>

      {error && <div className="error">{error}</div>}

      <div className="grid cols-4" style={{ marginBottom: 14 }}>
        {stat("Total power", fmt(live?.total_power, 2), "W", "#38bdf8")}
        {stat("PV power", fmt(live?.pv_power, 2), "W", "#34d399")}
        {stat("TEG power", fmt(live?.teg_power, 3), "W", "#fbbf24")}
        {stat("ΔT (hot−cold)", fmt(live?.delta_t, 1), "K", "#f87171")}
      </div>

      <div className="grid cols-4" style={{ marginBottom: 14 }}>
        {stat("Irradiance", fmt(live?.irradiance, 0), "W/m²")}
        {stat("Hot side", fmt(live?.hot_temperature, 1), "°C")}
        {stat("Battery SoC", fmt(live?.battery_soc, 0), "%", live?.battery_soc < 25 ? "#f87171" : undefined)}
        {stat("System efficiency", fmt(live?.system_efficiency, 1), "%")}
      </div>

      <div className="grid cols-2" style={{ marginBottom: 14 }}>
        <div className="card">
          <h3>Total power — last 12 h</h3>
          <LineChart points={powerSeries} color="#38bdf8" unit=" W" />
        </div>
        <div className="card">
          <h3>ΔT — last 12 h</h3>
          <LineChart points={thermalSeries} color="#f87171" unit=" K" />
        </div>
      </div>

      <div className="grid cols-3">
        <div className="card">
          <h3>Energy today</h3>
          <div className="stat-value">
            {fmt(energy?.today_energy_wh, 2)}
            <span className="stat-unit">Wh</span>
          </div>
          <div className="muted" style={{ marginTop: 6 }}>
            PV {fmt(energy?.pv_share_pct, 1)}% · TEG {fmt(energy?.teg_share_pct, 1)}%
          </div>
        </div>
        <div className="card">
          <h3>Cumulative energy</h3>
          <div className="stat-value">
            {fmt(energy?.cumulative_energy_wh, 1)}
            <span className="stat-unit">Wh</span>
          </div>
          <div className="muted" style={{ marginTop: 6 }}>
            avg power {fmt(energy?.avg_power_w, 2)} W
          </div>
        </div>
        <div className="card">
          <h3>MPPT / thermal</h3>
          <div className="muted" style={{ lineHeight: 1.9 }}>
            hot {fmt(live?.hot_temperature, 1)} °C · cold {fmt(live?.cold_temperature, 1)} °C
            <br />
            cooling eff {fmt(live?.cooling_efficiency, 0)}% · duty {fmt(live?.mppt_duty, 2)}
            <br />
            data source: {live?.data_source || "—"}
          </div>
        </div>
      </div>
    </div>
  );
}
