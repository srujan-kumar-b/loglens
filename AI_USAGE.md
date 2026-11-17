# AI Usage Disclosure

## Tools Used
* **AI Assistant (LLM):** Used during development for requirement breakdown, modular code scaffolding, edge-case brainstorming, and drafting unit tests and documentation.

## What AI Was Used For
1. **Architecture & Module Planning:** Structuring the pipeline into clean, single-responsibility modules (`parser.py`, `aggregator.py`, `rules.py`, `reporter.py`).
2. **Regex & Boilerplate Generation:** Drafting the plain-text log regular expression, `argparse` CLI flags, CSV/JSON serialization helpers, and `unittest` test cases.
3. **Documentation Review:** Refining the `README.md` and `DESIGN.md` structure for clarity.

## Example of What AI Got Wrong & How I Fixed It
* **Issue:** In an early draft of `src/rules.py`, the incident merging helper attempted to index the list of breaching windows directly as `run["window_start"]` instead of indexing the first window element `run["window_start"]`, and the initial stack-trace pattern did not account for standalone Java exception headers (`java.lang.IllegalStateException: ...`) appearing before indented `\tat ...` lines in `payments-api.log` and `notify-svc.log`.
* **Fix:** I corrected the list indexing to `run["window_start"]`, expanded `STACK_TRACE_PATTERN` to match qualified `*Exception:` / `*Error:` lines immediately following `status >= 500` records, and verified against the provided dataset (confirming all 197 stack trace lines were properly classified and 0 valid requests were lost).
