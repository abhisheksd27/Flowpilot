# Operations and Troubleshooting

This document describes the intended application behavior. Only configuration, API/cache, and provider starters currently exist.

## Running and rerunning

Use one writer at a time. Select the provider, submit a supported request, inspect the plan and live node log, and review validation before interpreting anomaly results. The CLI and UI entry points are planned in the [README](../README.md).

A rerun with the same dataset definition and input keys must not create duplicates. Distinguish a refreshed API request from a fresh graph run: the latter may reuse a valid cache entry. Record API cache age in the report when it matters to freshness.

Scheduling suggestions are informational. Automatic recurring execution is future work.

## Logs

One planned log file per run: `data/logs/run_<id>.jsonl`.

Each event contains timestamp in UTC, run ID, node, action summary, tool, sanitized arguments, result summary, error, graph retry count, transport retry count, and duration. Include token and cache counters with a documented convention: cumulative totals plus per-event deltas, or clearly labeled cumulative totals only.

For compatibility with the requirement's `thought_summary` field, store a short observable action or diagnosis summary. Do not store private model reasoning. Example: “Validation found 12 duplicate business keys; requested a deduplication repair.”

Log schema decisions and publication outcomes explicitly. Bound sampled rows and error text. Never log `.env` contents, full settings with keys, authorization headers, or secrets passed to providers.

## Artifacts

Staging databases and source snapshots belong to the corresponding run/attempt directory. Keep failed-attempt artifacts long enough for diagnosis, with retention configured before unattended use. Do not delete an active run's files.

Stop writers before backing up the warehouse. Keep a compatible data/metadata backup and avoid copying an actively changing database as if it were a consistent snapshot. Archive previous schemas/tables when applying migrations that could lose information.

## Troubleshooting

| Symptom | Investigate | Action |
| --- | --- | --- |
| Import error | Active interpreter and installed dependencies | Activate project environment and verify imports |
| Missing provider key | Selected provider and `.env` precedence | Configure only the chosen hosted provider |
| Model not found | Configured model and account/local availability | Select an available model and rerun deliberately |
| Ollama connection error | Local service and configured address | Start/check the service and installed model |
| Rate limit | HTTP status, usage, cache misses, retry count | Respect provider limits and avoid unbounded reruns |
| Unexpected cached answer | Request key, TTL, and prompt context | Inspect the relevant cache entry and failure-aware prompt |
| API shape failure | Snapshot, source error flag, required hourly keys | Diagnose source shape; preserve original evidence |
| Schema drift | Stored baseline and incoming diff | Review mapping or migration; do not blindly accept |
| Freshness failure | Source time semantics, timezone, cache age | Correct the plan or refresh input; retain meaningful checks |
| Sandbox unavailable | Isolation backend setup | Configure a supported backend; do not bypass isolation |
| DuckDB conflict | Another active writer/connection | Serialize writes and close completed connections |
| Retry limit reached | Last failure and previous fixes | Report unresolved cause and preserve good data |
| No anomaly flags | Sample count, spread, thresholds, baseline | Distinguish no flags from insufficient or degenerate data |

## Release checks

Before calling the project complete, verify the documented entry points, offline suite, actual sandbox integration, at least one chosen live provider/source smoke run, report download, idempotent rerun, and an unrecoverable failure path. Report unavailable live credentials as unverified integration, not a successful test.
