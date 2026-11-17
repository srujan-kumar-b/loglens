import csv
import json
import os
from datetime import datetime
from src.aggregator import compute_percentile


def filter_records(records: list[dict], service: str = None, start_dt: datetime = None, end_dt: datetime = None) -> list[dict]:
    """Filter parsed log records by optional service name and IST time bounds [start_dt, end_dt)."""
    filtered = []
    for rec in records:
        if service and rec["service"] != service:
            continue
        if start_dt and rec["ts"] < start_dt:
            continue
        if end_dt and rec["ts"] >= end_dt:
            continue
        filtered.append(rec)
    return filtered


def build_service_summary(records: list[dict], incidents: list[dict]) -> list[dict]:
    """Compute overall health summary per service across the analyzed timeframe."""
    by_service = {}
    for rec in records:
        svc = rec["service"]
        if svc not in by_service:
            by_service[svc] = []
        by_service[svc].append(rec)

    incident_counts = {}
    for inc in incidents:
        svc = inc["service"]
        incident_counts[svc] = incident_counts.get(svc, 0) + 1

    summaries = []
    for svc in sorted(by_service.keys()):
        items = by_service[svc]
        total = len(items)
        errors = sum(1 for r in items if r["is_error"])
        error_rate = round((errors / total) * 100.0, 2) if total else 0.0
        latencies = sorted(r["latency_ms"] for r in items)

        summaries.append({
            "service": svc,
            "total_requests": total,
            "error_count": errors,
            "error_rate_pct": error_rate,
            "p50_latency_ms": compute_percentile(latencies, 50),
            "p95_latency_ms": compute_percentile(latencies, 95),
            "incident_count": incident_counts.get(svc, 0),
        })
    return summaries


def format_incidents_for_export(incidents: list[dict]) -> list[dict]:
    """Convert datetime objects to clean ISO-8601 IST strings for CSV/JSON output."""
    formatted = []
    for inc in incidents:
        formatted.append({
            "service": inc["service"],
            "rule": inc["rule"],
            "start_time_ist": inc["start_time"].isoformat(),
            "end_time_ist": inc["end_time"].isoformat(),
            "duration_minutes": int((inc["end_time"] - inc["start_time"]).total_seconds() // 60),
            "window_count": inc["window_count"],
            "peak_value": inc["peak_value"],
        })
    return formatted


def write_reports(output_dir: str, incidents: list[dict], summaries: list[dict]):
    """Write incident reports and per-service summaries in both CSV and JSON formats."""
    os.makedirs(output_dir, exist_ok=True)
    exported_incidents = format_incidents_for_export(incidents)

    # 1. Incidents JSON & CSV
    with open(os.path.join(output_dir, "incidents.json"), "w", encoding="utf-8") as f:
        json.dump(exported_incidents, f, indent=2)

    inc_fields = ["service", "rule", "start_time_ist", "end_time_ist", "duration_minutes", "window_count", "peak_value"]
    with open(os.path.join(output_dir, "incidents.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=inc_fields)
        writer.writeheader()
        writer.writerows(exported_incidents)

    # 2. Per-Service Summary JSON & CSV
    with open(os.path.join(output_dir, "service_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summaries, f, indent=2)

    sum_fields = ["service", "total_requests", "error_count", "error_rate_pct", "p50_latency_ms", "p95_latency_ms", "incident_count"]
    with open(os.path.join(output_dir, "service_summary.csv"), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=sum_fields)
        writer.writeheader()
        writer.writerows(summaries)
