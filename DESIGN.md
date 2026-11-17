# LogLens — System Architecture & Design Note

## 1. Problem Overview
Backend services emit logs in inconsistent formats (plain-text pipe-delimited vs. structured JSONL) and mixed timezones (`UTC` vs. `IST`), interspersed with multi-line stack traces, log rotation markers, and truncated lines. LogLens unifies these streams into deterministic 5-minute health windows and surfaces actionable incidents.

## 2. Architecture & Data Flow

```text
+-------------------+      +---------------------+      +------------------------+

|   logs/ folder    | ---> |    src/parser.py    | ---> |   src/aggregator.py    |
| (*.log, *.jsonl)  |      | - Format detection  |      | - Clock-aligned 5-min  |
+-------------------+      | - IST normalization |      |   window bucketing     |

                           | - Stack trace state |      | - Error rate & p50/p95 |
                           | - Bad line counter  |      +------------------------+
                           +---------------------+                   |
                                                                     v
+-------------------+      +---------------------+      +------------------------+

|     output/       | <--- |   src/reporter.py   | <--- |      src/rules.py      |
| - incidents.csv   |      | - Service/time      |      | - Reads config.json    |
| - incidents.json  |      |   filtering         |      | - Evaluates thresholds |
| - summary.csv     |      | - CSV/JSON export   |      | - Merges adjacent      |
| - summary.json    |      | - Console summary   |      |   breaching windows    |
+-------------------+      +---------------------+      +------------------------+
```

## 3. Core Component Design

### A. Ingestion & Fault-Tolerant Parsing (`src/parser.py`)
* **Format Dispatch:** Each non-empty line is inspected; lines starting with `{` are routed to `parse_json_line()`, while others are matched against a compiled regex in `parse_plain_line()`.
* **Stateful Stack Trace Tracking:** The parser tracks `last_was_error` per file. If a line immediately follows an error entry (`status >= 500`) and matches exception/frame signatures (`at ...`, `Caused by:`, `... N more`, `*Exception:`), it is counted under `stack_trace_lines` rather than corrupting request metrics or inflating `unparseable_lines`.
* **Graceful Degradation:** Truncated JSON fragments, rotation banners (`#### log rotated ####`), and malformed fields are caught per line, incrementing `unparseable_lines` without interrupting file processing.

### B. Time-Aligned Aggregation (`src/aggregator.py`)
* **Clock Alignment:** Every IST timestamp is floored to the nearest 5-minute boundary (`minute = (dt.minute // 5) * 5, second = 0, microsecond = 0`), ensuring consistent `[start, end)` intervals regardless of out-of-order log arrivals.
* **Latency Percentiles:** Window latencies are sorted once per bucket, and `p50` / `p95` are extracted via the Nearest-Rank formula (`ceil(P/100 * N) - 1`), guaranteeing deterministic, reproducible results.

### C. Config-Driven Rule Engine & Incident Merging (`src/rules.py`)
* **Decoupled Thresholds:** `config.json` defines `threshold_pct`, `min_requests`, `threshold_ms`, `consecutive_windows`, and `excluded_paths`.
* **Adjacency Verification:** When merging consecutive breaching windows, the engine explicitly checks `current_window.start == previous_window.end` so non-adjacent spikes separated by quiet windows remain distinct incidents.
* **Inclusive Latency Spans:** For sustained latency (`consecutive_windows >= 2`), all qualifying adjacent windows are merged into a single incident spanning `first_window.start` to `last_window.end` with the maximum `p95_latency_ms` recorded as `peak_value`.
