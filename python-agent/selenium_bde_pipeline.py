#!/usr/bin/env python3
"""
LinkedIn BDE Lead Generation Pipeline (Selenium Edition) - V2 Upgraded
Delegates directly to the concurrent USA-Only BDE Intelligent Suite:
  - Max 2-3 Days / Yesterday's Freshness Enforcement
  - Strict USA Geographic Targeting & Indian Geo-Leak Exclusions
  - Strict HR, Recruiter, and Sales Representative Exclusions
  - Persistent One-Time Login (Chrome User Profile)
  - Parallel Selenium Harvester & OpenAI Intelligence Workers
  - Real-time "Model Thinking" Stream & Query Performance Analytics
"""

import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

try:
    from linkedin_bde_intelligent_pipeline import main
    if __name__ == "__main__":
        main()
except ImportError:
    # If run outside venv, relaunch within venv if present
    venv_python = os.path.join(SCRIPT_DIR, ".venv", "bin", "python")
    target_script = os.path.join(SCRIPT_DIR, "linkedin_bde_intelligent_pipeline.py")
    if os.path.exists(venv_python) and sys.executable != venv_python:
        import subprocess
        sys.exit(subprocess.call([venv_python, target_script] + sys.argv[1:]))
    else:
        raise
