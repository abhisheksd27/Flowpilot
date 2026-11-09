# FlowPilot

A weather and air-quality data engineering project with real Open-Meteo data, validated DuckDB tables, anomaly analysis, reports and an interactive workflow view.

- [Run the full pipeline locally with Docker (manual operation)](agent-de/docs/local-runtime.md)
- [Setup, saved data and background operation](agent-de/docs/interview.md)
- [Project overview and architecture](agent-de/README.md)
- [Detailed architecture](agent-de/docs/architecture.md)
- [Feature guide: forecasts, analytics, recovery, rules, API and retention](agent-de/docs/features.md)
- [Public dashboard](https://abhisheksd27.github.io/Flowpilot/)

```bash
git clone https://github.com/abhisheksd27/Flowpilot.git
cd Flowpilot/agent-de
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
sh scripts/build-sandbox.sh
sh scripts/run-local-docker.sh
```

Ask “What is the current temperature in Bangalore?” in the main interface, or use the sidebar to build the full weather and air-quality dataset. The free local demo uses trusted built-in transformations. Optional AI providers and isolated generated-code execution remain available in full mode.

Stop with Ctrl+C and run the last command again when needed. Saved data stays locally in `agent-de/data/`; refresh to update it. The interview guide explains timestamps, API caching, background collection and historical gaps.
