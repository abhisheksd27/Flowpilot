#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
docker image inspect agent-de-sandbox:local >/dev/null
export DEMO_MODE=false SANDBOX_BACKEND=docker LLM_PROVIDER=builtin
exec .venv/bin/python main.py watch --provider builtin --frequency hourly --run-now
