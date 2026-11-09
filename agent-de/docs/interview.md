# Local interview guide

## Install once (macOS, Linux or Windows)

Install Python 3.11 and Git, then:

```bash
git clone https://github.com/abhisheksd27/Flowpilot.git
cd Flowpilot/agent-de
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows use `py -3.11 -m venv .venv` and `.venv\Scripts\activate`.

## Run the free local demo

```bash
DEMO_MODE=true LLM_PROVIDER=builtin streamlit run app.py
```

Windows PowerShell:

```powershell
$env:DEMO_MODE="true"
$env:LLM_PROVIDER="builtin"
streamlit run app.py
```

Open the localhost URL printed by Streamlit. No model key or Docker is needed in demo mode. Internet is required to fetch real data.

1. Enter “What is the current temperature in Bangalore?”, “Is it raining in Bengaluru?” or “How is the weather in Mumbai?” in the main question field. Click Get weather. The answer includes conditions, rain, humidity, wind, clouds and feels-like temperature with a source timestamp. Bangalore and Banglore are mapped to Bengaluru. Forecast questions are not supported in this field.
2. Choose a city in the sidebar. Click Refresh data now to build its weather and air-quality dataset.
3. Follow the actual workflow events, then inspect quality checks, trends, DuckDB tables and the downloadable report.
4. Explain the architecture: request → validated plan → allowlisted API broker → raw snapshots → trusted transformation → staging → validation and source reconciliation → transactional DuckDB publication → anomalies and report.

Demo mode applies trusted repository functions. AI code generation and OS isolation remain in the full mode, enabled with DEMO_MODE=false and a configured macOS sandbox or Linux Docker worker. Do not describe the free demo as live AI generation. The temperature question is a supported weather lookup, not a general-purpose chatbot.

## Stop and restart

### Local UI with real Docker execution

Start Docker Desktop, then from `agent-de`:

```bash
sh scripts/build-sandbox.sh
sh scripts/run-local-docker.sh
```

The UI runs at http://localhost:8504. Streamlit runs on the host; each transformation executes inside a short-lived Docker worker with network disabled, read-only root filesystem, reduced privileges and resource limits. The default built-in engine needs no credentials, and uses the real sandbox rather than demo mode. Select a configured AI provider in the sidebar to test generated code. Build the image again after worker changes; otherwise only the launch command is needed. Ctrl+C stops the UI. Docker Desktop must remain running.

Press Ctrl+C in the terminal. Run the same Streamlit command whenever needed. The local `data/` directory keeps the warehouse, raw snapshots, reports, logs and saved results. Restarting displays saved results with their timestamps; it does not automatically fetch new data. Click Refresh data now to update the pipeline. API responses can be reused for up to 900 seconds by default. Older cache entries expire; failed API calls do not silently become fresh data. Get temperature explicitly bypasses the API cache on every click. Previously displayed temperature answers remain on screen until you ask again or end the session.

Pipeline publication updates matching location/timestamp rows without duplicating them. History remains in DuckDB while `data/` is retained. The normal ingestion window is five past days plus today; stopping for longer can leave historical gaps. Do not delete `data/` if you want to preserve results. It is intentionally excluded from GitHub.

## Optional hourly background collection

In a second terminal, activate the virtual environment and run:

```bash
DEMO_MODE=true LLM_PROVIDER=builtin python main.py watch --provider builtin --frequency hourly --run-now
```

This runs once immediately and then hourly for Bengaluru. Keep that terminal open; Ctrl+C stops it. The UI can close independently. For macOS background operation across terminal closure:

```bash
DEMO_MODE=true LLM_PROVIDER=builtin nohup python main.py watch --provider builtin --frequency hourly --run-now > data/watch.log 2>&1 &
```

Save the printed process ID; stop your own watcher with `kill PROCESS_ID`. Do not start multiple watchers. This is free software running on your computer, so it needs power, internet, an awake computer and the project drive mounted. It will not run while the computer is off. It is unnecessary for an interview: manual refresh is sufficient.

## GitHub deployment

GitHub Pages is the public read-only dashboard with issue-backed request reports. Standard public GitHub Actions jobs collect city data hourly independently of your computer. Queued issue requests post reports back to GitHub and the dashboard reads them. This does not host the local Streamlit interface or provide instant live Python execution. Use the local interface to demonstrate interactive execution.

## Checks

```bash
python -m pytest -q
```

Troubleshooting: use the demo environment variables if Docker is unavailable; check internet access for API failures; check source timestamps before presenting saved data as recent; wait for an active run before starting another (the warehouse has a single-writer lock).
