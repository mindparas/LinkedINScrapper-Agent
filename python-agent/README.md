# 🚀 Autonomous AI BDE Lead Discovery Agent (Production Architecture)

An enterprise-grade, fully autonomous LinkedIn BDE lead generation engine.
Designed specifically for offshore IT & software development agencies (such as Indian BDE teams pitching US startup founders), this system executes all query strategy, navigation, deep profile location verification, commercial buying intent filtering, authentic post shortlink resolution, and pitch synthesis autonomously with zero manual intervention required.

---

## 🏗️ Modular Architecture (`src/`)

```text
python-agent/
├── src/
│   ├── config.py                  # Environment config, API keys, colors, and file logging
│   ├── metrics.py                 # RunMetrics: end-of-run performance scorecard + JSON report + run history
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
│       ├── planner.py             # StrategicQueryPlanner (mission-driven query rotation & feed diagnosis)
│       ├── mission.py             # Mission + interpret_intent/resolve_mission (user intent -> search spec)
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
Set a key for the LLM provider you want in `python-agent/.env` (both can be present):
```text
ANTHROPIC_API_KEY=sk-ant-...        # Claude
OPENAI_API_KEY=sk-...               # OpenAI (the older `gpt-apikey=` line also works)
LLM_PROVIDER=anthropic              # or: openai   (unset = anthropic if its key exists, else openai)
# Optional per-role models (defaults: claude-sonnet-5-5 / gpt-4o-mini):
# LLM_MODEL_JUDGE=claude-sonnet-5-5   LLM_MODEL_AGENT=claude-haiku-5-5   LLM_MODEL_INTERPRETER=claude-sonnet-5-5
```
All model calls go through `src/llm.py`; the run prints which provider/models it is using, and the
metrics report prices each role with the model it used. The judge cache is keyed by model, so switching
provider never reuses another model's verdicts.

### Step 3: Run One-Click Lead Discovery
From the workspace root:
```bash
./run_leads.sh -n 3
```
Or with custom duration and niche:
```bash
./run_leads.sh -n 5 -t 20 --niche "custom software & AI MVP engineering"
```

### Step 3b: Tell the agent what kind of posts you want (Intent)
Describe the posts in plain English, either with `--intent` or when prompted (ENTER keeps the default
"US founders needing outsourced engineering"):
```bash
./run_leads.sh -n 3 -t 20 --intent "Healthcare startup founders in the US looking for an AI partner to build a HIPAA-compliant product"
```
An LLM turns that into a **mission**: what qualifies, who the author should be, location rule (US verified on the
profile, or no location filter), what to exclude, and a set of short search phrases. The interpretation is printed;
when you type the intent interactively you can press ENTER to accept, type a correction to refine it, or `q` to cancel.
Vague requests ("good leads") trigger a clarifying question. The mission then drives query planning, the lead judge,
location checks, the agent prompt and the outreach text. Skip memory and query stats are kept per mission, so a post
rejected for one mission is still visible to another. Non-interactive runs (no TTY) use the default mission unless
`--intent` is given. The old interactive CLI (`src/agent/cli.py`) reads the `INTENT` env var in non-interactive mode.

### Step 3d: How the agent learns to search (query engine)
You never write queries. The mission (your intent) is turned into searches by `src/agent/query_engine.py`:
- **Strategist (LLM):** writes ~14 queries across different angles in the voice of the target author, and avoids words that attract sellers/recruiters.
- **Re-planning:** after 3 queries in a row with no matching post (2 if the results were mostly sellers/recruiters) it reads what actually came back (category mix, junk examples, why they were rejected), writes a diagnosis, and produces a new set of queries with a different approach. The planner can override a query the agent picked right after a strategy change or when that query's words have a bad track record.
- **Learner (online Bayesian bandit):** every word / word pair keeps a posterior of how often it returns matching posts and how often it pulls sellers/recruiters. Candidates are ranked by Thompson sampling, so it generalises to phrasings it has never run and balances exploring vs exploiting. Persisted per mission in `dataset/query_learning.json`, so every run starts smarter.
- **Time filters:** past-24h is checked first and past-week is added whenever 24h returns fewer than 10 posts (past-week contains the 24h posts, newest first). If 24h keeps being thin for a mission, the agent goes straight to past-week to save a page load.
- **No endless searching:** if `QUERY_STAGNATION_LIMIT` (default 9) queries in a row match nothing, even after strategy changes, the run stops with the reason and the diagnosis instead of waiting for the clock.

### Step 3c: Performance metrics
When a run ends (target reached, time limit, safety halt, error or Ctrl+C) the agent prints a scorecard: result vs
target, a posts→leads funnel, efficiency (leads/hour, searches per lead, duplicate and empty-search rates), lead
quality (judge confidence, need types), per-query results, estimated LLM cost and today's LinkedIn budget use, plus
plain-language insights and a comparison with the previous run. The full detail is saved to
`exports/metrics_<timestamp>.json`, and one summary line per run is appended to `dataset/run_history.jsonl`.
The cost figure is an estimate based on gpt-4o-mini list prices (constants in `src/metrics.py`).

### Step 4: Access Pristine Leads
Leads are exported in real time to `python-agent/exports/`:
- `latest_usa_sales_leads.csv` (Primary active CSV)
- `latest_usa_sales_leads.json` (Primary active JSON)
- `usa_genuine_sales_leads_<timestamp>.csv` (Dedicated timestamped session archive)
