import os
import tempfile
import unittest
from datetime import datetime
from src.parser import (
    IST,
    parse_json_line,
    parse_plain_line,
    parse_logs_directory,
)
from src.aggregator import get_window_start, compute_percentile, aggregate_windows
from src.rules import evaluate_rules


class TestLogLens(unittest.TestCase):
    def test_parse_plain_text_and_utc_to_ist_conversion(self):
        line = "2026-11-03 14:02:11.532 +0000 | payments-api | INFO | GET /v1/payments/123 | status=200 | latency_ms=184 | req_id=a81f"
        rec = parse_plain_line(line)
        self.assertEqual(rec["service"], "payments-api")
        self.assertEqual(rec["status"], 200)
        self.assertEqual(rec["latency_ms"], 184.0)
        self.assertFalse(rec["is_error"])
        # 14:02:11.532 UTC should equal 19:32:11.532 IST (+05:30)
        self.assertEqual(rec["ts"].tzinfo, IST)
        self.assertEqual(rec["ts"].hour, 19)
        self.assertEqual(rec["ts"].minute, 32)

    def test_parse_json_line_and_error_classification(self):
        line = '{"ts":"2026-11-03T19:32:11.532+05:30","service":"accounts-api","level":"ERROR","method":"POST","path":"/v1/accounts","status":503,"latency_ms":2310,"req_id":"c09d"}'
        rec = parse_json_line(line)
        self.assertEqual(rec["service"], "accounts-api")
        self.assertEqual(rec["status"], 503)
        self.assertTrue(rec["is_error"])
        self.assertEqual(rec["ts"].hour, 19)

    def test_directory_parser_handles_stack_traces_corrupt_lines_and_exclusions(self):
        sample_log = "\n".join([
            "2026-11-03 10:00:01.000 +0530 | notify-svc | ERROR | POST /v1/send | status=500 | latency_ms=420 | req_id=r1",
            "java.lang.IllegalStateException: Downstream timeout",
            "\tat com.pbs.notify.Sender.send(Sender.java:42)",
            "\t... 12 more",
            "2026-11-03 10:00:05.000 +0530 | notify-svc | INFO | GET /health | status=200 | latency_ms=5 | req_id=r2",
            '{"ts":"2026-11-03T10:01:00+05:30","service":"notify-svc","level":"INFO","method":"GET","path":"/v1/ok","status":200,"latency_ms":50,"req_id":"r3"}',
            '{"ts":"2026-11-03T10:02:00+05:30","truncated_json',
            "#### log rotated ####",
        ])
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "mixed.log")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(sample_log)

            records, stats = parse_logs_directory(tmpdir, excluded_paths=["/health"])
            # 2 valid non-health requests (r1 and r3), 1 excluded (/health), 3 stack trace lines, 2 unparseable lines
            self.assertEqual(stats["parsed_requests"], 2)
            self.assertEqual(stats["excluded_requests"], 1)
            self.assertEqual(stats["stack_trace_lines"], 3)
            self.assertEqual(stats["unparseable_lines"], 2)

    def test_clock_aligned_windowing_and_percentiles(self):
        dt = datetime(2026, 11, 3, 14, 4, 59, tzinfo=IST)
        win_start = get_window_start(dt)
        self.assertEqual(win_start, datetime(2026, 11, 3, 14, 0, 0, tzinfo=IST))

        # Nearest-rank percentile check on 1..100
        values = [float(i) for i in range(1, 101)]
        self.assertEqual(compute_percentile(values, 50), 50.0)
        self.assertEqual(compute_percentile(values, 95), 95.0)

    def test_error_rate_rule_min_requests_and_merging(self):
        config = {
            "rules": {
                "high_error_rate": {"enabled": True, "threshold_pct": 5.0, "min_requests": 20},
                "sustained_high_latency": {"enabled": False},
            }
        }
        w1 = datetime(2026, 11, 3, 14, 0, tzinfo=IST)
        w2 = datetime(2026, 11, 3, 14, 5, tzinfo=IST)
        w3 = datetime(2026, 11, 3, 14, 10, tzinfo=IST)

        # Window 1: 10% error rate (2/20) -> BREACH
        # Window 2: 20% error rate (4/20) -> BREACH (adjacent, should merge with W1)
        # Window 3: 50% error rate (5/10) -> NO BREACH (below 20 min_requests)
        records = []
        for i in range(20):
            records.append({"ts": w1, "service": "svc-a", "latency_ms": 100.0, "is_error": i < 2})
        for i in range(20):
            records.append({"ts": w2, "service": "svc-a", "latency_ms": 100.0, "is_error": i < 4})
        for i in range(10):
            records.append({"ts": w3, "service": "svc-a", "latency_ms": 100.0, "is_error": i < 5})

        wins = aggregate_windows(records)
        incidents = evaluate_rules(wins, config)
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0]["start_time"], w1)
        self.assertEqual(incidents[0]["end_time"], datetime(2026, 11, 3, 14, 10, tzinfo=IST))
        self.assertEqual(incidents[0]["peak_value"], 20.0)

    def test_sustained_latency_requires_two_consecutive_windows(self):
        config = {
            "rules": {
                "high_error_rate": {"enabled": False},
                "sustained_high_latency": {"enabled": True, "threshold_ms": 2000.0, "consecutive_windows": 2},
            }
        }
        w1 = datetime(2026, 11, 3, 15, 0, tzinfo=IST)   # isolated spike -> NO incident
        w2 = datetime(2026, 11, 3, 15, 5, tzinfo=IST)   # normal
        w3 = datetime(2026, 11, 3, 15, 10, tzinfo=IST)  # spike 1
        w4 = datetime(2026, 11, 3, 15, 15, tzinfo=IST)  # spike 2 -> triggers incident covering w3..w4

        records = [
            {"ts": w1, "service": "svc-b", "latency_ms": 2500.0, "is_error": False},
            {"ts": w2, "service": "svc-b", "latency_ms": 120.0, "is_error": False},
            {"ts": w3, "service": "svc-b", "latency_ms": 2200.0, "is_error": False},
            {"ts": w4, "service": "svc-b", "latency_ms": 3100.0, "is_error": False},
        ]
        wins = aggregate_windows(records)
        incidents = evaluate_rules(wins, config)
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0]["start_time"], w3)
        self.assertEqual(incidents[0]["end_time"], datetime(2026, 11, 3, 15, 20, tzinfo=IST))
        self.assertEqual(incidents[0]["peak_value"], 3100.0)


if __name__ == "__main__":
    unittest.main()
