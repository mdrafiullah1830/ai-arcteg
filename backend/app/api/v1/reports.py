"""Report generation: JSON summary + PDF export (fpdf2)."""
from __future__ import annotations

import datetime as dt
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import rate_limit, require_min_role
from app.models.anomaly import Anomaly
from app.models.telemetry import SensorTelemetry
from app.models.user import User
from app.schemas.system import ReportResponse
from app.services import queries

router = APIRouter(prefix="/reports", tags=["reports"])


def _build_report(db: Session, hours: float) -> ReportResponse:
    now = dt.datetime.now(dt.timezone.utc)
    date_from = (now - dt.timedelta(hours=hours)).date()
    data = queries.energy_summary(db)
    sample = queries.latest_sample(db) or {}

    power_stats = queries.stats(db, "total_power", hours=hours)
    hot_stats = queries.stats(db, "hot_temperature", hours=hours)
    delta_stats = queries.stats(db, "delta_t", hours=hours)
    anomaly_data = queries.anomaly_summary(db, limit=20)

    from app.ml import service as ml

    model = ml.model_status()

    def o(r: Anomaly) -> dict:
        return {
            "id": r.id,
            "timestamp": r.timestamp.isoformat(),
            "parameter": r.parameter,
            "severity": r.severity,
            "status": r.status,
            "message": r.message,
        }

    return ReportResponse(
        title=f"{hours:g}h Operations Report",
        generated_at=now.isoformat(),
        date_from=date_from.isoformat(),
        date_to=now.date().isoformat(),
        data_label=data["data_source"],
        summary={
            "avg_power_w": power_stats["mean"],
            "peak_power_w": power_stats["max"],
            "samples": power_stats["count"],
            "location": sample.get("scenario", "D"),
        },
        energy=data,
        thermal={
            "avg_hot_c": hot_stats["mean"],
            "max_hot_c": hot_stats["max"],
            "avg_delta_t": delta_stats["mean"],
            "max_delta_t": delta_stats["max"],
        },
        mppt={
            "algorithm": engine_algorithm(),
            "duty": sample.get("mppt_duty", 0.0),
            "tracking_efficiency": sample.get("system_efficiency", 0.0),
        },
        anomalies={
            "open": anomaly_data["open"],
            "warning": anomaly_data["warning"],
            "critical": anomaly_data["critical"],
            "total": anomaly_data["total"],
            "recent": [o(r) for r in anomaly_data["recent"]],
        },
        ai={
            "trained": model["trained"],
            "trained_at": model["trained_at"],
            "metrics": model["metrics"],
        },
        series={
            "power": queries.series(db, "total_power", hours=hours, resolution="15m")["points"],
            "delta_t": queries.series(db, "delta_t", hours=hours, resolution="15m")["points"],
        },
    )


def engine_algorithm() -> str:
    from app.simulation.engine import engine

    return engine.mppt.algorithm


@router.get("", response_model=ReportResponse)
def report_json(
    hours: float = Query(24.0, gt=0, le=24 * 30),
    _: None = Depends(rate_limit),
    db: Session = Depends(get_db),
) -> ReportResponse:
    return _build_report(db, hours)


@router.get("/pdf")
def report_pdf(
    hours: float = Query(24.0, gt=0, le=24 * 30),
    _: User = Depends(require_min_role("ENGINEER")),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    report = _build_report(db, hours)
    pdf_bytes = _render_pdf(report)
    filename = f"arcteg_report_{report.generated_at[:19].replace(':', '-')}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _render_pdf(report: ReportResponse) -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, report.title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Generated: {report.generated_at}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Range: {report.date_from} to {report.date_to}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Data source: {report.data_label}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    def section(title: str) -> None:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)

    def kv(key: str, value) -> None:
        pdf.cell(60, 6, str(key))
        pdf.cell(0, 6, str(value), new_x="LMARGIN", new_y="NEXT")

    section("Summary")
    for k, v in report.summary.items():
        kv(k, v)
    pdf.ln(2)

    section("Energy")
    for k, v in report.energy.items():
        kv(k, v)
    pdf.ln(2)

    section("Thermal")
    for k, v in report.thermal.items():
        kv(k, v)
    pdf.ln(2)

    section("MPPT")
    for k, v in report.mppt.items():
        kv(k, v)
    pdf.ln(2)

    section("Anomalies")
    kv("open", report.anomalies["open"])
    kv("warning", report.anomalies["warning"])
    kv("critical", report.anomalies["critical"])
    kv("total", report.anomalies["total"])
    pdf.ln(2)

    section("AI / ML")
    kv("trained", report.ai["trained"])
    kv("trained_at", report.ai["trained_at"] or "-")
    for name, metrics in (report.ai.get("metrics") or {}).items():
        if isinstance(metrics, dict):
            kv(f"  {name}", ", ".join(f"{k}={v}" for k, v in metrics.items()))
    pdf.ln(2)

    section("Recent anomalies")
    for item in report.anomalies["recent"][:10]:
        pdf.multi_cell(
            0, 5, f"[{item['severity']}] {item['parameter']}: {item['message']}",
            new_x="LMARGIN", new_y="NEXT",
        )
    pdf.ln(2)

    section("Power series (last points)")
    for point in report.series["power"][-15:]:
        kv(point["timestamp"][11:19], f"{point['value']} W")

    return bytes(pdf.output())
