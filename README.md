# LogLens — Multi-Service Log Analysis and Alerting

LogLens is a zero-dependency Python CLI tool that ingests heterogeneous service logs (JSON lines and plain-text logs across mixed timezones), aggregates request health metrics into fixed 5-minute clock-aligned windows, evaluates config-driven alert rules, and exports incident and per-service reports.

## Quick Setup & Run (3 Commands)

Requires **Python 3.10+** (standard library only; no `pip install` needed).

```bash
# 1. Run analysis across all logs using default config.json
python main.py

# 2. Optional: Filter by service and/or IST time range
python main.py --service payments-api --start 2026-11-03T14:00:00 --end 2026-11-03T19:00:00

# 3. Run automated unit tests
python -m unittest discover -s tests -v
```

Generated reports (`incidents.csv`, `incidents.json`, `service_summary.csv`, `service_summary.json`) are written to `output/`.

## Assumptions & Definitions
* **Unified Timezone (`IST / +05:30`):** All incoming timestamps (`Z`, `+0000`, `+05:30`, `+0530`) are normalized to Indian Standard Time (`UTC+05:30`) immediately upon parsing. CLI `--start` and `--end` flags assume IST if no offset is supplied.
* **Error Classification:** Any request with HTTP status `>= 500` counts as an error. `4xx` responses are treated as client responses and do not trigger server error alerts.
* **Multi-line Stack Traces:** Lines immediately following an error (`status >= 500`) that match standard Java/Python stack trace patterns (`at ...`, `... N more`, `Caused by:`, `*Exception:`) are attributed to the preceding error entry. They are counted separately (`stack_trace_lines`) and excluded from both request totals and unparseable line counts.
* **Percentile Method (`Nearest-Rank`):** Latency percentiles (`p50` and `p95`) are calculated using the standard nearest-rank method: `index = ceil((P / 100) * N) - 1` on sorted window latencies.
* **Clock-Aligned Windows:** Windows align strictly to 5-minute clock boundaries (`[start, end)`, e.g., `14:00:00` inclusive to `14:05:00` exclusive).
* **Consecutive Latency Rule:** Requires `p95_latency_ms > threshold_ms` across `N` chronologically adjacent 5-minute windows (`window[i].start == window[i-1].end`). When triggered, the resulting incident spans from the start of the first breaching window through the end of the last consecutive breaching window.

## Key Design Decisions
* **Zero External Dependencies:** Built purely with Python's standard library (`json`, `re`, `datetime`, `csv`, `argparse`, `unittest`) so the tool runs reliably in any environment without dependency conflicts.
* **Line-by-Line Streaming Ingestion:** Files are read line-by-line rather than loaded via `readlines()`, keeping memory overhead low when scanning large log files.
* **Config-Driven Rules & Exclusions:** Thresholds, minimum request floors, consecutive window counts, and excluded paths (e.g., `/health`) live in `config.json` so operational rules can be tuned without modifying source code.
* **Modular Pipeline:** Parsing, aggregation, rule evaluation, and reporting are separated into distinct modules under `src/` for straightforward testing and live extensibility.

## Known Limitations
* **In-Memory Window Buckets:** While log lines are streamed from disk, parsed records are grouped in memory before percentile sorting. For multi-gigabyte logs spanning months, streaming window-by-window flushing or approximate quantile sketches (e.g., t-digest) would further reduce memory usage.
* **Static Config Schema:** Currently supports threshold rules for error rate and consecutive p95 latency; adding arbitrary new metric expressions would require extending the rule evaluator.

## What I Would Do With Another Week
* **Live Tail Mode (`--tail`):** Watch active log files for appended lines and emit real-time console/webhook alerts as 5-minute windows close.
* **HTML/Visual Dashboard:** Generate a lightweight static HTML report with error-rate and p95 latency trend charts per service.
* **Per-Endpoint Breakdown:** Include top failing or slowest API routes (`method + path`) inside each incident summary to speed up root-cause debugging.
