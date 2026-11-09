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
