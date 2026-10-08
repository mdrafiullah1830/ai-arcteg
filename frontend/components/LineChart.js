"use client";

/**
 * Dependency-free SVG line chart for telemetry sparklines.
 * points: [{timestamp, value}] — oldest first or newest first (auto-sorted).
 */
export default function LineChart({ points = [], color = "#38bdf8", unit = "", height = 150 }) {
  if (!points.length) {
    return (
      <div className="muted" style={{ height, display: "flex", alignItems: "center", justifyContent: "center" }}>
        No data yet
      </div>
    );
  }

  const values = points.map((p) => Number(p.value) || 0);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const w = 600;
  const h = height;
  const pad = 8;

  const coords = values.map((v, i) => {
    const x = pad + (i / Math.max(values.length - 1, 1)) * (w - 2 * pad);
    const y = h - pad - ((v - min) / span) * (h - 2 * pad);
    return [x, y];
  });

  const path = coords.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${path} L${coords[coords.length - 1][0].toFixed(1)},${h - pad} L${coords[0][0].toFixed(1)},${h - pad} Z`;

  return (
    <div>
      <svg className="chart" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ height }}>
        <path d={area} fill={color} opacity="0.12" />
        <path d={path} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="row muted" style={{ fontSize: 11, justifyContent: "space-between" }}>
        <span>
          min {min.toFixed(2)}{unit}
        </span>
        <span>
          latest {values[values.length - 1].toFixed(2)}{unit}
        </span>
        <span>
          max {max.toFixed(2)}{unit}
        </span>
      </div>
    </div>
  );
}
