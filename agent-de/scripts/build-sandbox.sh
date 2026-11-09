#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
task_context=$(mktemp -d)
mkdir "$task_context/tools"
# Copy only public worker inputs; exclude credentials and macOS metadata.
cp Dockerfile.sandbox "$task_context/Dockerfile"
cp tools/_sandbox_worker.py "$task_context/tools/_sandbox_worker.py"
COPYFILE_DISABLE=1 docker build -t agent-de-sandbox:local "$task_context"
