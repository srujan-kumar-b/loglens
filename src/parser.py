import json
import os
import re
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

PLAIN_TEXT_PATTERN = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?\s+[+-]\d{4})\s*\|\s*"
    r"(?P<service>[^|]+?)\s*\|\s*"
    r"(?P<level>[^|]+?)\s*\|\s*"
    r"(?P<method>[A-Z]+)\s+(?P<path>\S+)\s*\|\s*"
    r"status=(?P<status>\d+)\s*\|\s*"
    r"latency_ms=(?P<latency>\d+(?:\.\d+)?)\s*\|\s*"
    r"req_id=(?P<req_id>\S+)\s*$"
)

STACK_TRACE_PATTERN = re.compile(
    r"^(\s+at\s+|\s*\.\.\.\s+\d+\s+more|Caused by:|Suppressed:|[\w.$]+(?:Exception|Error|Throwable):)"
)


def parse_timestamp_to_ist(ts_str: str) -> datetime:
    ts_str = ts_str.strip()
    if ts_str.endswith("Z"):
        ts_str = ts_str[:-1] + "+00:00"
    # Handle plain text format like '2026-11-03 14:02:11.532 +0000'
    try:
        dt = datetime.fromisoformat(ts_str)
    except ValueError:
        dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S.%f %z")
    if dt.tzinfo is None:
        raise ValueError("Missing timezone")
    return dt.astimezone(IST)


def parse_json_line(line: str) -> dict:
    data = json.loads(line)
    if not isinstance(data, dict):
        raise ValueError("JSON line is not an object")

    ts = parse_timestamp_to_ist(str(data["ts"]))
    service = str(data["service"]).strip()
    method = str(data["method"]).strip()
    path = str(data["path"]).strip()
    status = int(data["status"])
    latency_ms = float(data["latency_ms"])
    req_id = str(data.get("req_id", "")).strip()

    if not service or not path:
        raise ValueError("Missing required fields")

    return {
        "ts": ts,
        "service": service,
        "method": method,
        "path": path,
        "status": status,
        "latency_ms": latency_ms,
        "req_id": req_id,
        "is_error": status >= 500,
    }


def parse_plain_line(line: str) -> dict:
    match = PLAIN_TEXT_PATTERN.match(line)
    if not match:
        raise ValueError("Does not match plain text log format")

    groups = match.groupdict()
    ts = parse_timestamp_to_ist(groups["ts"])
    status = int(groups["status"])
    latency_ms = float(groups["latency"])

    return {
        "ts": ts,
        "service": groups["service"].strip(),
        "method": groups["method"].strip(),
        "path": groups["path"].strip(),
        "status": status,
        "latency_ms": latency_ms,
        "req_id": groups["req_id"].strip(),
        "is_error": status >= 500,
    }


def parse_logs_directory(logs_dir: str, excluded_paths=None):
    excluded_paths = set(excluded_paths or [])
    records = []
    unparseable_count = 0
    stack_trace_lines = 0
    excluded_count = 0

    for filename in sorted(os.listdir(logs_dir)):
        filepath = os.path.join(logs_dir, filename)
        if not os.path.isfile(filepath):
            continue

        last_was_error = False
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for raw_line in f:
                line = raw_line.rstrip("\r\n")
                if not line.strip():
                    continue

                # Check if this line is part of a multi-line stack trace following an error
                if last_was_error and STACK_TRACE_PATTERN.match(line):
                    stack_trace_lines += 1
                    continue

                try:
                    if line.lstrip().startswith("{"):
                        record = parse_json_line(line)
                    else:
                        record = parse_plain_line(line)

                    last_was_error = record["is_error"]

                    if record["path"] in excluded_paths:
                        excluded_count += 1
                        continue

                    records.append(record)
                except Exception:
                    last_was_error = False
                    unparseable_count += 1

    stats = {
        "parsed_requests": len(records),
        "unparseable_lines": unparseable_count,
        "stack_trace_lines": stack_trace_lines,
        "excluded_requests": excluded_count,
    }
    return records, stats
