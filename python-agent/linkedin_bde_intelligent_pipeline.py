#!/usr/bin/env python3
"""
================================================================================
  AUTONOMOUS AI BDE LEAD DISCOVERY AGENT (Selenium + OpenAI ReAct Suite)
================================================================================
Full LLM-Controlled Autonomous Architecture:
  1. Complete Tool Control: OpenAI decides queries, freshness, profile verification, web searches, and lead saving.
  2. Persistent Chrome Window: Browser stays continuously open on screen for live user inspection.
  3. Exact CSV Fields: Primary columns are Profile URL, Post URL (authentic shortlink), and Fit Score.
  4. Runtime Freshness Testing: Agent tests past-24h vs past-week dynamically to maximize high-yield results.
  5. Deep Profile Location Verification: Visits author's profile in background tab to confirm 100% exact USA location.
  6. Web Search Tool: Agent can search the web to investigate company HQ, founders, or BDE strategy.
  7. Persistent Agent Memory: Loads and saves agent_memory.json, learning from past queries and avoiding dead-ends.
  8. Cognitive Query Evolution: Agent articulates hypotheses, expected outputs, observations, and critiques.
================================================================================
Modular Architecture (src/):
  - src.config: Environment configuration, terminal colors, and logging setup
  - src.verification: USA location verification, BDE rules, freshness, and query sanitization
  - src.storage: Live session CSV/JSON lead exporter and empirical agent memory
  - src.browser: Stealth Selenium Chrome driver setup and LinkedIn login verification
  - src.tools: ReAct tool definitions (schemas) and execution engine
  - src.agent: Multi-turn ReAct cognitive reasoning loop and CLI entrypoint
================================================================================
"""

import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# Re-export all public API symbols for complete backward compatibility
from src import (
    BASE_DIR,
    Style,
    load_openai_key,
    setup_file_logger,
    OPENAI_API_KEY,
    parse_post_age,
    clean_linkedin_boolean_query,
    is_verified_usa_location,
    verify_bde_lead_authenticity,
    LiveLeadExporter,
    AgentMemory,
    setup_stealth_driver,
    verify_or_prompt_login,
    search_web_api,
    AGENT_TOOLS,
    LinkedInAgentTools,
    run_autonomous_agent,
    main,
)

if __name__ == "__main__":
    main()
