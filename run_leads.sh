#!/usr/bin/env bash
# One-click standalone launcher for Autonomous LinkedIn USA BDE Lead Generation
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/python-agent"

if [ -f ".venv/bin/python" ]; then
    PYTHON_EXEC=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_EXEC="python3"
else
    echo "❌ Error: Python 3 not found."
    exit 1
fi

exec "$PYTHON_EXEC" run_autonomous_leads.py "$@"
