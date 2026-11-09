#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
docker image inspect agent-de-sandbox:local >/dev/null
export DEMO_MODE=false SANDBOX_BACKEND=docker
export LLM_PROVIDER=builtin
exec .venv/bin/python -m streamlit run app.py --server.port "${FLOWPILOT_PORT:-8504}"
