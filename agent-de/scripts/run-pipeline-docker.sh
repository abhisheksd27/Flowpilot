#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
docker image inspect agent-de-sandbox:local >/dev/null
export DEMO_MODE=false SANDBOX_BACKEND=docker
export LLM_PROVIDER="${LLM_PROVIDER:-builtin}"
exec .venv/bin/python main.py run --refresh --provider "$LLM_PROVIDER" "$@"
