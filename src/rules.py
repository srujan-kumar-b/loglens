def _merge_window_runs(service: str, rule_name: str, runs: list[list[dict]], metric_key: str) -> list[dict]:
    """
    Merge consecutive breaching windows for a single service and rule into incidents.
    Each item in `runs` is a list of adjacent breaching window dicts.
    """
    incidents = []
    for run in runs:
        if not run:
            continue
        start_time = run[0]["window_start"]
        end_time = run[-1]["window_end"]
        peak_value = max(w[metric_key] for w in run)
        incidents.append({
            "service": service,
            "rule": rule_name,
            "start_time": start_time,
            "end_time": end_time,
            "window_count": len(run),
            "peak_value": peak_value,
        })
    return incidents


def evaluate_rules(service_windows: dict[str, list[dict]], config: dict) -> list[dict]:
    """Evaluate all enabled alert rules from config and return merged incidents."""
    rules_cfg = config.get("rules", {})
    all_incidents = []

    for service, windows in sorted(service_windows.items()):
        # --- Rule 1: High Error Rate ---
        err_cfg = rules_cfg.get("high_error_rate", {})
        if err_cfg.get("enabled", True):
            threshold_pct = float(err_cfg.get("threshold_pct", 5.0))
            min_requests = int(err_cfg.get("min_requests", 20))

            breaching_runs = []
            current_run = []

            for win in windows:
                is_breach = (
                    win["request_count"] >= min_requests
                    and win["error_rate_pct"] > threshold_pct
                )
                if is_breach:
                    if current_run and win["window_start"] == current_run[-1]["window_end"]:
                        current_run.append(win)
                    else:
                        if current_run:
                            breaching_runs.append(current_run)
                        current_run = [win]
                else:
                    if current_run:
                        breaching_runs.append(current_run)
                        current_run = []

            if current_run:
                breaching_runs.append(current_run)

            all_incidents.extend(
                _merge_window_runs(service, "high_error_rate", breaching_runs, "error_rate_pct")
            )

        # --- Rule 2: Sustained High Latency (N consecutive windows) ---
        lat_cfg = rules_cfg.get("sustained_high_latency", {})
        if lat_cfg.get("enabled", True):
            threshold_ms = float(lat_cfg.get("threshold_ms", 2000.0))
            required_consecutive = int(lat_cfg.get("consecutive_windows", 2))

            candidate_runs = []
            current_run = []

            for win in windows:
                if win["p95_latency_ms"] > threshold_ms:
                    if current_run and win["window_start"] == current_run[-1]["window_end"]:
                        current_run.append(win)
                    else:
                        if current_run:
                            candidate_runs.append(current_run)
                        current_run = [win]
                else:
                    if current_run:
                        candidate_runs.append(current_run)
                        current_run = []

            if current_run:
                candidate_runs.append(current_run)

            qualifying_runs = [
                run for run in candidate_runs if len(run) >= required_consecutive
            ]

            all_incidents.extend(
                _merge_window_runs(service, "sustained_high_latency", qualifying_runs, "p95_latency_ms")
            )

    all_incidents.sort(key=lambda inc: (inc["start_time"], inc["service"], inc["rule"]))
    return all_incidents
