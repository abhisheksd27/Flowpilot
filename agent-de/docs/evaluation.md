# Evaluation

Run `python -m eval.run_eval` to regenerate [measured results](../eval/results.md). Nine injected cases cover renamed/removed fields, new fields, numeric type drift, missing values, duplicates, timeout, malformed JSON and out-of-range data. Each scenario starts from a valid published baseline and evaluates recovery and warehouse integrity.

This is deterministic built-in repair evaluation with fixture API responses and a restricted trusted-template executor. It measures the implemented orchestration and repair policies, not live-model intelligence, live service reliability or sandbox security. Persistent fault tests separately verify bounded failure and preservation of valid data. Actual OS isolation and real HTTP ingestion have separate integration checks.
