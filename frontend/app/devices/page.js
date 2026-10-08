"use client";

import { useEffect, useState } from "react";
import { api, getUser } from "../../lib/api";

export default function DevicesPage() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ device_uid: "", device_name: "", location: "Dhaka" });
  const [user, setUser] = useState(null);

  async function load() {
    try {
      const data = await api("/devices");
      setItems(data.items);
      setTotal(data.total);
      setError("");
    } catch (err) {
      setError(String(err.message || err));
    }
  }

  useEffect(() => {
    setUser(getUser());
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, []);

  async function createDevice(e) {
    e.preventDefault();
    try {
      await api("/devices", { method: "POST", body: { ...form, is_simulated: false } });
      setForm({ device_uid: "", device_name: "", location: "Dhaka" });
      load();
    } catch (err) {
      setError(String(err.message || err));
    }
  }

  async function remove(id) {
    if (!confirm("Delete this device?")) return;
    try {
      await api(`/devices/${id}`, { method: "DELETE" });
      load();
    } catch (err) {
      setError(String(err.message || err));
    }
  }

  const healthBadge = (h) => {
    const cls = h === "HEALTHY" ? "ok" : h === "DEGRADED" ? "warn" : h === "FAULT" ? "crit" : "";
    return <span className={`badge ${cls}`}>{h}</span>;
  };

  return (
    <div>
      <h1 className="page-title">Devices</h1>
      <p className="page-sub">{total} registered · simulated + hardware rigs</p>
      {error && <div className="error">{error}</div>}

      <div className="card" style={{ marginBottom: 14 }}>
        <table>
          <thead>
            <tr>
              <th>UID</th>
              <th>Name</th>
              <th>Location</th>
              <th>Mode</th>
              <th>Status</th>
              <th>Health</th>
              <th>Last seen</th>
              {user && user.role !== "VIEWER" && <th />}
            </tr>
          </thead>
          <tbody>
            {items.map((d) => (
              <tr key={d.id}>
                <td>{d.device_uid}</td>
                <td>{d.device_name}</td>
                <td>{d.location}</td>
                <td>
                  <span className={`badge ${d.is_simulated ? "warn" : "ok"}`}>{d.mode}</span>
                </td>
                <td>{d.status}</td>
                <td>{healthBadge(d.sensor_health)}</td>
                <td className="muted">{d.last_seen ? new Date(d.last_seen).toLocaleString() : "never"}</td>
                {user && user.role !== "VIEWER" && (
                  <td>
                    {user.role === "ADMIN" && (
                      <button className="danger" onClick={() => remove(d.id)}>
                        Delete
                      </button>
                    )}
                  </td>
                )}
              </tr>
            ))}
            {!items.length && (
              <tr>
                <td colSpan={8} className="muted">
                  No devices — start the simulation or POST to /api/v1/ingest/telemetry
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {user && user.role !== "VIEWER" && (
        <form className="card row" onSubmit={createDevice}>
          <input
            placeholder="device_uid (e.g. esp32-rig-02)"
            value={form.device_uid}
            onChange={(e) => setForm({ ...form, device_uid: e.target.value })}
            required
            style={{ minWidth: 220 }}
          />
          <input
            placeholder="Device name"
            value={form.device_name}
            onChange={(e) => setForm({ ...form, device_name: e.target.value })}
            required
            style={{ minWidth: 180 }}
          />
          <input
            placeholder="Location"
            value={form.location}
            onChange={(e) => setForm({ ...form, location: e.target.value })}
            style={{ minWidth: 140 }}
          />
          <button type="submit">Register device</button>
        </form>
      )}
    </div>
  );
}
