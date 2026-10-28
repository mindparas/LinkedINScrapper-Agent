#!/usr/bin/env bash
# One-click root launcher delegating to the Python BDE Lead Discovery Agent
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/python-agent/run_pipeline.sh" "$@"
