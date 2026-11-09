# Full local runtime: manual operation

This runs the actual ingestion, Docker execution, validation, publication, anomaly analysis and reporting path. Lightweight mode is disabled. No scheduler is started by these commands.

From `agent-de`, with Python dependencies installed and Docker Desktop running:

```bash
sh scripts/build-sandbox.sh
sh scripts/run-local-docker.sh
```

Open http://localhost:8504 and click **Run pipeline now**. Each manual run fetches fresh source responses. The full flow shows actual events. Browse saved results, charts and validation checks under Advanced options. Run history and files remain in `data/` between restarts. Stop the UI with Ctrl+C.

To run the identical full pipeline manually from a terminal:

```bash
sh scripts/run-pipeline-docker.sh --request "Track weather and air quality for Bengaluru and flag anomalies."
```

Built-in uses deterministic planning and the repository transformation, executed inside the real Docker sandbox. To use a configured model for planning/code generation:

```bash
LLM_PROVIDER=ollama sh scripts/run-pipeline-docker.sh
```

Gemini and Groq are also supported when configured. Model failures are reported and invalid outputs are never published; there is no silent switch to a successful built-in run. Weather questions use the current-weather endpoint separately, and show timestamps for modeled conditions.

Local operation uses the same pipeline and Docker isolation as the GitHub worker. It is a single-writer application, not a hardened multi-user public hosting service. A public deployment additionally needs authentication, request limits, backups and service supervision. Do not expose Docker's socket to browser users.

## Hourly collection and weather answers

The dashboard shows the scheduler heartbeat, next run, and last outcome. If no watcher is active, run `sh scripts/watch-local-docker.sh` in a second terminal. It collects Bengaluru immediately and then hourly, saving validated records and checking data quality and anomalies. A duplicate watcher is rejected by the scheduler lock. Keep Docker Desktop and the computer running. Do not start this command when an existing watcher is already active.

Ask about current rain, humidity, wind, clouds, temperature or conditions in the dashboard. A question without a city uses the selected city. Answers fetch fresh modeled conditions and show the source timestamp. Historical questions, forecasts and arbitrary weather advice are not supported by this current-conditions field.
