import argparse
import json
from datetime import datetime
from src.parser import IST, parse_logs_directory
from src.aggregator import aggregate_windows
from src.rules import evaluate_rules
from src.reporter import filter_records, build_service_summary, format_incidents_for_export, write_reports


def parse_cli_time(time_str: str) -> datetime:
    """Parse an ISO timestamp string into IST (assumes IST if offset omitted)."""
    dt = datetime.fromisoformat(time_str.strip())
    if dt.tzinfo is None:
        return dt.replace(tzinfo=IST)
    return dt.astimezone(IST)


def main():
    parser = argparse.ArgumentParser(description="LogLens - Multi-Service Log Analysis and Alerting Tool")
    parser.add_argument("--logs-dir", default="logs", help="Directory containing log files (default: logs)")
    parser.add_argument("--config", default="config.json", help="Path to alert rule config file (default: config.json)")
    parser.add_argument("--output-dir", default="output", help="Directory for CSV/JSON reports (default: output)")
    parser.add_argument("--service", default=None, help="Filter results to a specific service name")
    parser.add_argument("--start", default=None, help="Filter start time in IST (e.g., 2026-11-03T14:00:00)")
    parser.add_argument("--end", default=None, help="Filter end time in IST (e.g., 2026-11-03T17:00:00)")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        config = json.load(f)

    excluded_paths = config.get("excluded_paths", [])
    records, parse_stats = parse_logs_directory(args.logs_dir, excluded_paths=excluded_paths)

    start_dt = parse_cli_time(args.start) if args.start else None
    end_dt = parse_cli_time(args.end) if args.end else None
    filtered_records = filter_records(records, service=args.service, start_dt=start_dt, end_dt=end_dt)

    service_windows = aggregate_windows(filtered_records)
    incidents = evaluate_rules(service_windows, config)
    summaries = build_service_summary(filtered_records, incidents)

    write_reports(args.output_dir, incidents, summaries)

    # Console Summary Output
    print("=== LogLens Analysis Summary (Timezone: IST / +05:30) ===")
    print(
        f"Parsed Requests: {parse_stats['parsed_requests']} | "
        f"Unparseable Lines: {parse_stats['unparseable_lines']} | "
        f"Stack Trace Lines: {parse_stats['stack_trace_lines']} | "
        f"Excluded Requests: {parse_stats['excluded_requests']}"
    )
    if args.service or args.start or args.end:
        print(f"Active Filters -> Service: {args.service or 'ALL'}, Start: {args.start or 'NONE'}, End: {args.end or 'NONE'}")

    print("\n--- Per-Service Summary ---")
    print(f"{'Service':<16} {'Reqs':>7} {'Errors':>7} {'Err%':>7} {'p50(ms)':>9} {'p95(ms)':>9} {'Incidents':>10}")
    for s in summaries:
        print(
            f"{s['service']:<16} {s['total_requests']:>7} {s['error_count']:>7} "
            f"{s['error_rate_pct']:>6.2f}% {s['p50_latency_ms']:>9.2f} {s['p95_latency_ms']:>9.2f} {s['incident_count']:>10}"
        )

    print("\n--- Detected Incidents ---")
    exported_incidents = format_incidents_for_export(incidents)
    if not exported_incidents:
        print("No incidents triggered.")
    else:
        for inc in exported_incidents:
            unit = "%" if inc["rule"] == "high_error_rate" else " ms"
            print(
                f"[{inc['service']}] {inc['rule']} | "
                f"{inc['start_time_ist']} -> {inc['end_time_ist']} "
                f"({inc['duration_minutes']} mins) | Peak: {inc['peak_value']}{unit}"
            )

    print(f"\nReports written to '{args.output_dir}/' (incidents.csv, incidents.json, service_summary.csv, service_summary.json)")


if __name__ == "__main__":
    main()
