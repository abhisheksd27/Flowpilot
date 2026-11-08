# Verification

```bash
python -m pytest -q
FLOWPILOT_SANDBOX_TESTS=1 python -m pytest tests/test_sandbox.py -q
python -m eval.run_eval
```

The default suite tests the actual graph, transformations, Pandera/SQL validation, publication, idempotency, source drift, bounded failures, API policy/cache/retries, model wire formats, SQL restrictions and timezone scheduling. Its fixture executor accepts only known repository transformation templates; it does not execute arbitrary generated code on the host.

Opt-in sandbox tests execute the real OS backend and check valid transformation, denied unrelated-file and symlink access, denied writes, blocked direct requests, timeout and bounded output. They require host sandbox permissions. Live external LLM credentials were not exercised. Docker isolation was subsequently exercised by a successful real-data GitHub Actions deployment; the opt-in security suite was run on macOS.

Live Bengaluru ingestion separately exercised real Open-Meteo HTTP, macOS isolation, staging, validation, transactional publication, anomalies and report output. A second live run retained 139 rows with zero net-new rows, proving overlap idempotency. Tests never assert a model quality rate from fixture results.
