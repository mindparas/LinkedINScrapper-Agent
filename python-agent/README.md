# 🚀 Autonomous AI BDE Lead Discovery Agent (Production Architecture)

An enterprise-grade, fully autonomous LinkedIn BDE lead generation engine.
Designed specifically for offshore IT & software development agencies (such as Indian BDE teams pitching US startup founders), this system executes all query strategy, navigation, deep profile location verification, commercial buying intent filtering, authentic post shortlink resolution, and pitch synthesis autonomously with zero manual intervention required.

---

## 🏗️ Modular Architecture (`src/`)

```text
python-agent/
├── src/
│   ├── config.py                  # Environment config, API keys, colors, and file logging
│   ├── verification/              # Multi-stage strict filtering & verification
│   │   ├── persona_filter.py      # verify_bde_persona (strict founder/CTO vs recruiter/broker gate)
│   │   ├── intent_engine.py       # verify_sales_intent (active MVP build & dev hiring requirement engine)
│   │   ├── location.py            # is_verified_usa_location (3-tier USA state/metro engine)
│   │   ├── freshness.py           # parse_post_age (relative timestamp parsing)
│   │   ├── query_sanitizer.py     # clean_linkedin_boolean_query (unquoted natural keywords)
│   │   └── lead_rules.py          # Unified verification facade (backward-compatible)
│   ├── browser/                   # Selenium stealth automation & DOM sensors
│   │   ├── driver.py              # setup_stealth_driver (persistent profile, CDP evasion)
│   │   ├── auth.py                # verify_or_prompt_login (session verification)
│   │   ├── dom_scanner.py         # scan_linkedin_content_cards (deterministic DOM scanner with unique IDs)
│   │   ├── url_resolver.py        # resolve_post_url (3-tier authentic post URL resolver)
│   │   └── web_search.py          # search_web_api (DuckDuckGo lookup)
│   ├── storage/                   # Persistence & reporting layers
│   │   ├── exporter.py            # LiveLeadExporter (rich BDE lead schema accumulator)
│   │   └── memory.py              # AgentMemory (empirical query execution ledger)
│   ├── tools/                     # ReAct sensor & actuator tools
│   │   ├── schemas.py             # AGENT_TOOLS (OpenAI function calling schemas)
│   │   └── agent_tools.py         # LinkedInAgentTools (sensor & actuator implementations)
│   └── agent/                     # Core AI cognition & execution
│       ├── runner.py              # run_autonomous_agent (multi-turn ReAct reasoning loop)
│       ├── planner.py             # StrategicQueryPlanner (US hub rotation & feed diagnosis)
│       ├── evaluator.py           # BDESalesIntelligenceSynthesizer (pitch kit generator)
│       └── cli.py                 # main (interactive terminal CLI)
│
├── exports/                       # Verified BDE leads (CSV & JSON format)
├── logs/                          # Comprehensive session action logs
├── linkedin_chrome_profile/       # Persistent Chrome profile (preserves authenticated LinkedIn session)
├── run_autonomous_leads.py        # Standalone hands-free launcher
├── run_pipeline.sh                # Executable shell launcher
├── requirements.txt               # Dependencies
└── README.md                      # This documentation
```

---

## 🌟 Core System Highlights

### 1. 100% Hands-Free Autonomous Operation
The user simply runs:
```bash
./run_leads.sh -n 5
```
Or from the `python-agent/` directory:
```bash
python3 run_autonomous_leads.py -n 5 -t 15
```
The agent autonomously:
- Dynamically selects optimal US tech hub queries (`San Francisco`, `Austin`, `Seattle`, `NYC`, `YC`, `Bay Area`, etc.).
- Rotates hubs and accelerators automatically when feeds dry up or become contaminated.
- Scans and evaluates cards in real-time.
- Verifies exact US location via author profile top-cards.
- Resolves authentic, direct post URLs.
- Generates high-converting outreach pitch kits tailored for Indian BDEs.
- Halts automatically when the lead target is achieved.

### 2. Deterministic DOM Card Extraction & Unique Card IDs
- Modern LinkedIn content cards (`role="listitem"`) are stamped with a persistent DOM token (`data-bde-card-id="bde_card_<uuid>"`).
- Eradicates array indexing drift between filtered card lists and raw DOM arrays.

### 3. 3-Tier Post URL Resolution Engine
Guarantees 100% authentic, direct, clickable LinkedIn post URLs with zero `activity:unknown` fallbacks:
- **Tier 1 (Clipboard Interception)**: Targets the 3-dots control menu on the specific card, clicks "Copy link to post", and captures `window.__bdeCapturedUrl`.
- **Tier 2 (Card DOM Parsing)**: Inspects child permalinks, activity URNs, and update IDs in the card element.
- **Tier 3 (Author Activity Matcher)**: Visits author's `/recent-activity/all/`, matches the post text snippet against the author's feed, and extracts the canonical permalink.

### 4. Strict Persona & Decision-Maker Gate
- **Must be**: Authentic direct startup executive (Founder, Co-Founder, CEO, CTO, VP of Engineering, Head of Engineering).
- **Hard disqualification of**:
  - Recruiters, Headhunters, HR, Staffing Agencies (including brokers disguised as founders, e.g. *"Hiring Founding Engineers for AI Startups"*).
  - Intermediaries: VCs, Angel Scouts, Accelerators, Newsletters, Media Curators.
  - Job Seekers: "Open to work", "Seeking opportunities", "Aspiring engineer".
  - Students and Hackathon participants.

### 5. Commercial Buying & Building Intent Engine
- **Must express**: Active technical build need, MVP development, hiring founding/senior engineer, seeking dev shop/agency, or contract/fractional CTO help.
- **Disqualifies**:
  - Roles already filled / hiring closed ("We found our engineer", "Role is filled").
  - Career announcements / job moves ("Excited to announce I joined...").
  - Generic thought leadership, advice, or news reposts.

### 6. BDE Sales Pitch Kit & Comprehensive Lead Schema
Every discovered lead includes an actionable outreach kit ready for an Indian BDE to copy-paste:
- **Lead ID**: Unique sequence (e.g., `BDE-001`)
- **Author Name & First Name**: For personalized merge tags (`Hi {{First Name}}`)
- **Title / Headline & Company Name**
- **Verified Location**: (e.g., `San Francisco, California, United States`)
- **Profile URL & Post URL**: Direct clickable links
- **Commercial Intent Category**: (e.g., `MVP Build Need`, `Hiring Founding Dev (Agency Opportunity)`)
- **Identified Pain Point**: Concise breakdown of what they are building or struggling with
- **Target Tech Stack**: Detected technologies (e.g., `React, Python, FastAPI, Supabase, AWS`)
- **LinkedIn Connection Note (< 300 chars)**: Short, high-acceptance note ready for LinkedIn invites
- **Full BDE InMail / Cold Pitch**: 3-paragraph value-driven message highlighting rapid MVP shipping and dedicated senior engineers at competitive rates
- **Fit Score & Audit Trail Reasoning**

---

## 🚀 Quick Start Guide

### Step 1: Ensure Python Virtual Environment
```bash
cd python-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Step 2: Configure Environment Credentials
Ensure your OpenAI API key is set in `python-agent/.env`:
```text
OPENAI_API_KEY=sk-...
```

### Step 3: Run One-Click Lead Discovery
From the workspace root:
```bash
./run_leads.sh -n 3
```
Or with custom duration and niche:
```bash
./run_leads.sh -n 5 -t 20 --niche "custom software & AI MVP engineering"
```

### Step 4: Access Pristine Leads
Leads are exported in real time to `python-agent/exports/`:
- `latest_usa_sales_leads.csv` (Primary active CSV)
- `latest_usa_sales_leads.json` (Primary active JSON)
- `usa_genuine_sales_leads_<timestamp>.csv` (Dedicated timestamped session archive)
