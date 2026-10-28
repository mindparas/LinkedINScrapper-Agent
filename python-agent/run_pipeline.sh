#!/usr/bin/env bash
# One-click launcher for LinkedIn USA BDE Lead Generation Pipeline
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f ".venv/bin/python" ]; then
    exec .venv/bin/python linkedin_bde_intelligent_pipeline.py "$@"
else
    exec python3 linkedin_bde_intelligent_pipeline.py "$@"
fi

