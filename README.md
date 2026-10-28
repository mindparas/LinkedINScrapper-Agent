# 🎯 LinkedIn Lead Discovery & Scraping Suite

A modular, enterprise-grade toolkit for discovering and qualifying high-intent BDE leads and startup founders on LinkedIn.

This workspace provides two complementary tools:
1. **[Chrome Extension](chrome-extension/)**: A lightweight Manifest V3 extension featuring side-panel docking, pop-out windows, live search scraping, and client-side OpenAI post qualification.
2. **[Python Autonomous Agent](python-agent/)**: A fully autonomous AI agent utilizing Selenium, persistent Chrome login profiles, 3-tier USA location verification, authentic shortlink capture, and dynamic developer feedback loops.

---

## 📁 Repository Structure

```text
LinkedIn Scrapper/
├── chrome-extension/                  # 🌐 Manifest V3 Chrome Extension
│   ├── icons/                         # Extension icons (16px, 48px, 128px)
│   ├── background.js                  # Service worker handling requests & OpenAI scoring
│   ├── content.js                     # DOM extractor injected into LinkedIn
│   ├── main_world_interceptor.js      # Main world script intercepting feed requests
│   ├── manifest.json                  # Extension manifest configuration
│   ├── popup.css                      # UI styling for popup & side-panel
│   ├── popup.html                     # UI markup
│   ├── popup.js                       # Frontend event handling & options
│   └── README.md                      # Extension installation & usage instructions
│
├── python-agent/                      # 🤖 Autonomous AI BDE Lead Discovery Agent
│   ├── src/                           # Modular core architecture
│   │   ├── config.py                  # Environment config, keys, and session logger
│   │   ├── verification/              # USA location, authenticity, freshness, query sanitization
│   │   ├── storage/                   # Session lead exporter & empirical agent memory
│   │   ├── browser/                   # Stealth Chrome driver & LinkedIn auth verification
│   │   ├── tools/                     # ReAct tool definitions & Selenium DOM extractors
│   │   └── agent/                     # Autonomous ReAct reasoning loop & interactive CLI
│   ├── exports/                       # Verified leads (CSV & JSON format)
│   ├── logs/                          # Granular session execution logs
│   ├── debug/                         # Diagnostic HTML dumps & URL clipboard tests
│   ├── tools/                         # Standalone inspection & developer helper scripts
│   ├── linkedin_chrome_profile/       # Persistent Chrome profile (preserves LinkedIn login)
│   ├── .venv/                         # Python virtual environment
│   ├── .env                           # Local environment credentials (API keys)
│   ├── .env.example                   # Environment configuration template
│   ├── linkedin_bde_intelligent_pipeline.py  # Backward-compatible entrypoint
│   ├── selenium_bde_pipeline.py       # Pipeline launcher & fallback wrapper
│   ├── run_pipeline.sh                # Dedicated bash launcher for the agent
│   ├── requirements.txt               # Pinned Python package dependencies
│   ├── agent_memory.json              # Long-term empirical memory ledger
│   ├── query_performance_analytics.json # Query yield analytics cache
│   └── README.md                      # Comprehensive AI Agent documentation
│
├── run_pipeline.sh                    # 🚀 Root one-click launcher for the Python agent
├── .gitignore                         # Git ignore rules (secrets, venvs, session profiles)
└── README.md                          # Master workspace overview (this document)
```

---

## ⚡ Quick Start

### 1. Running the Autonomous AI Agent (Python)

From the root directory or inside `python-agent/`, execute:

```bash
./run_pipeline.sh
```

- **Authentication:** On first launch, a Chrome window opens. Log into your LinkedIn account once; credentials persist in `linkedin_chrome_profile/`.
- **Target Goal:** By default, the agent searches dynamically until at least 1 genuine lead is found, presents the lead card, and prompts for your direct feedback to steer subsequent searches.
- **Outputs:** Leads are continuously saved to `python-agent/exports/current_session_leads.csv`.

For detailed architecture, tools reference, and heuristic rules, see the **[Python Agent Guide](python-agent/README.md)**.

---

### 2. Installing the Chrome Extension

1. Open Google Chrome and navigate to `chrome://extensions/`.
2. Toggle **Developer mode** on (top-right corner).
3. Click **Load unpacked** (top-left corner).
4. Select the `chrome-extension/` directory from this workspace.
5. Pin the extension to your toolbar, configure your OpenAI API Key, and scrape leads directly within your daily browsing workflow.

For more details, see the **[Chrome Extension Guide](chrome-extension/README.md)**.

---

## 🔒 Security & Best Practices

- **API Keys:** Never commit `.env` or hardcode API keys. Use `.env.example` as a template.
- **Session Profiles:** The `python-agent/linkedin_chrome_profile/` directory holds active session cookies; it is strictly excluded from version control via `.gitignore`.
- **Anti-Ban Architecture:** Both tools adhere to humanized navigation timing and relative DOM extraction to avoid detection.

