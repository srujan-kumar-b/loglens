import math
from collections import defaultdict
from datetime import datetime, timedelta


def get_window_start(dt: datetime) -> datetime:
    """Snap a timestamp down to the nearest fixed 5-minute clock boundary."""
    floored_minute = (dt.minute // 5) * 5
    return dt.replace(minute=floored_minute, second=0, microsecond=0)


def compute_percentile(sorted_values: list[float], percentile: float) -> float:
    """
    Compute percentile using the Nearest-Rank method:
    index = ceil((P / 100) * N) - 1
    """
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    rank = math.ceil((percentile / 100.0) * n) - 1
    rank = max(0, min(rank, n - 1))
    return round(sorted_values[rank], 2)


def aggregate_windows(records: list[dict]) -> dict[str, list[dict]]:
    """
    Group records by service and fixed 5-minute windows.
    Returns a dict mapping service_name -> chronologically sorted list of window metrics.
    """
    buckets = defaultdict(list)

    for rec in records:
        win_start = get_window_start(rec["ts"])
        buckets[(rec["service"], win_start)].append(rec)

    service_windows = defaultdict(list)

    for (service, win_start), items in buckets.items():
        win_end = win_start + timedelta(minutes=5)
        total_requests = len(items)
        error_count = sum(1 for item in items if item["is_error"])
        error_rate = round((error_count / total_requests) * 100.0, 2) if total_requests else 0.0

        latencies = sorted(item["latency_ms"] for item in items)
        p50 = compute_percentile(latencies, 50)
        p95 = compute_percentile(latencies, 95)

        service_windows[service].append({
            "service": service,
            "window_start": win_start,
            "window_end": win_end,
            "request_count": total_requests,
            "error_count": error_count,
            "error_rate_pct": error_rate,
            "p50_latency_ms": p50,
            "p95_latency_ms": p95,
        })

    # Ensure windows for every service are strictly sorted in chronological order
    for service in service_windows:
        service_windows[service].sort(key=lambda w: w["window_start"])

    return dict(service_windows)
