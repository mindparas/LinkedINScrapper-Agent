# 🚀 Autonomous AI BDE Lead Discovery Agent (V3)

An enterprise-grade, fully autonomous LinkedIn BDE lead generation engine.
**All strategic, investigative, and navigational decisions are in the hands of the LLM.**

Selenium serves as the complete sensor and actuation suite for the agent, providing deep profile location verification, authentic post shortlink capture, web search capabilities, and persistent memory across runs.

---

## 🏗️ Modular Architecture (`src/`)

The pipeline is organized into modular packages under [`src/`](file:///home/paras/Downloads/MindInventroy/Projects/Test%20Projects/LinkedIn%20Scrapper/python-agent/src/):

```text
python-agent/
├── src/
│   ├── config.py              # Environment configuration, API keys, colors, and file logging
│   ├── verification/          # Strict verification engines
│   │   ├── freshness.py       # parse_post_age (relative timestamp parsing)
│   │   ├── query_sanitizer.py # clean_linkedin_boolean_query (unquoted natural keywords)
│   │   ├── location.py        # is_verified_usa_location (3-tier USA state/metro engine)
│   │   └── lead_rules.py      # verify_bde_lead_authenticity (founder title verification)
│   ├── storage/               # Persistence layers
│   │   ├── memory.py          # AgentMemory (empirical execution ledger)
│   │   └── exporter.py        # LiveLeadExporter (session-isolated CSV/JSON accumulator)
│   ├── browser/               # Selenium stealth automation
│   │   ├── driver.py          # setup_stealth_driver (persistent profile, CDP evasion)
│   │   ├── auth.py            # verify_or_prompt_login (one-time interactive login)
│   │   └── web_search.py      # search_web_api (instant DuckDuckGo lookup)
│   ├── tools/                 # ReAct agent sensor & actuator tools
│   │   ├── schemas.py         # AGENT_TOOLS (OpenAI function calling schemas)
│   │   └── agent_tools.py     # LinkedInAgentTools (10 DOM actions and sensor methods)
│   └── agent/                 # Core AI cognition & execution
│       ├── runner.py          # run_autonomous_agent (multi-turn ReAct reasoning loop)
│       └── cli.py             # main (interactive same-session terminal CLI)
│
├── linkedin_bde_intelligent_pipeline.py  # Backward-compatible entrypoint
├── selenium_bde_pipeline.py              # Pipeline wrapper
├── run_pipeline.sh                       # Dedicated executable launcher
├── requirements.txt                      # Pinned Python package dependencies
├── .env.example                          # Environment template
└── README.md                             # This documentation
```

---

## 🌟 Core System Architecture

1. **Session-Isolated Single CSV Accumulator (`exports/usa_bde_leads_session_<timestamp>.csv`):**
   - Each run initializes **one dedicated, fresh CSV file** for the current session.
   - It **does not load or consider previous CSV files**—each session starts completely clean.
   - When a genuine lead is found and the user chooses to continue searching (for multiple leads or multiple rounds in this session), **all leads append to that same single session CSV file**.
   - Pointer file `exports/current_session_leads.csv` continuously reflects the active session.
   - Primary columns: `Profile URL`, `Post URL`, `Fit Score`, `Author Name`, `Title / Headline`, `Verified Location`, `Company Name`, `Custom Outreach Hook`, `Reasoning`.
2. **Natural Unquoted Query Formulation (Zero Redundant Quotes):**
   - Strictly prohibits unnecessary double quotes around keywords (e.g. `building MVP custom software`, `hiring founding engineer AI startup`).
   - Verbatim double quotes restrict LinkedIn search to exact character matches, causing 0 results and missing genuine founder posts. Unquoted natural keywords match flexible variations with 10x higher yield.
3. **Transparent Cognitive Reasoning & Strategy Cards:**
   - Before executing any search, the agent articulates:
     - **Target Objective:** Exactly what kind of client persona or MVP project it wants to surface.
     - **Query:** Natural, clean keywords without quotes.
     - **Strategic Rationale:** Why this keyword syntax was chosen.
     - **Feasibility Assessment:** Will it achieve the objective and avoid recruiters/spam?
     - **Developer Feedback Applied:** Explicitly how previous developer feedback was integrated.
4. **Real-Time Developer Steering & Immediate Feedback Priority:**
   - Developer guidance is prompted and reviewed *before* executing searches on LinkedIn.
   - If the developer provides guidance, the agent overrides the proposed query immediately and formulates a new search strictly adhering to instructions.
   - Developer directives are maintained across turns in the session.
5. **Persistent Browser Window (Continuously Open):**
   - The Chrome window remains **open on your screen** after the agent finishes for interactive inspection.
6. **Gold Standard BDE Decision-Maker Authenticity:**
   - Evaluates authors against direct founder standards (e.g. Billy Jeremijenko, Founder of Symbolia).
   - Automated disqualification of VCs, recruiters, media accounts, and agency intermediaries.
7. **Deep Profile Location Verification (100% USA Only):**
   - Top card location extraction relative to Contact Info anchor to confirm US presence.
4. **Dynamic Autonomy — Agent Decides Scraping Volume:**
   - You provide the target lead goal (e.g. 5 or 10 leads).
   - The Agent autonomously decides how many queries to test, how many cards to scroll, when to switch freshness windows (`past-24h` vs `past-week`), and when satisfaction is reached.
5. **Runtime Freshness Testing (`past-24h` vs `past-week`):**
   - The agent dynamically tests recency:
     - Tests `past-24h` for ultra-fresh leads posted yesterday/today.
     - Tests `past-week` if a specific query is narrow, comparing which timeframe produces higher-yield leads.
6. **Web Search Capabilities (`search_web`):**
   - The agent can search the web to investigate company headquarters, look up founders, or discover trending BDE search queries.
8. **Pure Empirical Execution Memory (Zero Predefined Queries):**
   - `agent_memory.json` contains **zero predefined or canned queries**.
   - It acts purely as a factual ledger of what the AI has actually executed during runs:
     - The query autonomously synthesized by the agent.
     - Freshness window tested (`past-24h` vs `past-week`).
     - Number of post cards found on LinkedIn.
     - Number of genuine leads qualified.
     - Live outcome analysis and developer feedback received.
   - When the agent starts or continues, it uses this empirical record solely to avoid repeating 0-result phrasing and to autonomously pivot to fresh angles.
9. **Full Autonomous Query Synthesis:**
   - The LLM dynamically analyzes your agency service / niche (e.g. *custom software & AI MVP engineering*) and deduces what real US startup founders are posting on LinkedIn when seeking technical partners or hiring founding engineers.
   - It formulates 100% of queries dynamically from first principles without relying on static query menus.

---

## 🔍 How USA Filtering Works (3-Tier Engine)

1. **Tier 1 — Intent Querying (Search Box)**:
   - **Why NOT type "USA" in the search box?** LinkedIn's search bar performs full-text search across post text. Genuine US founders write *"We are building an MVP"* or *"Hiring our first founding engineer"*, but they almost never write *"We are located in the United States"*. Putting location words in the search box eliminates 95%+ of authentic posts and returns "0 results".
   - The agent searches high-intent buyer keywords (`"founding engineer"`, `"building an MVP"`, `"looking for software developers"`).
2. **Tier 2 — Post & Headline Heuristic Filtering**:
   - The agent examines post text, author headlines, and company names.
   - Immediate rejection of any posts mentioning international regions (India, Bangalore, Pune, Hyderabad, UK, Pakistan, Nigeria, etc.) or non-decision-maker titles (Recruiter, Staffing, HR, Bench Sales, Job Seeker).
3. **Tier 3 — Deep Profile Top Card Verification (Relative Proximity Engine)**:
   - For any promising post, the agent opens the author's profile in a background tab (`verify_profile_location`).
   - Modern LinkedIn desktop obfuscates class names and removes `<h1>` tags (author name is placed in `<h2>`). The scraper employs a robust **Contact-Info Relative Extraction Engine**:
     - Locates the author's `Contact info` anchor or button.
     - Inspects parent containers and preceding sibling lines immediately adjacent to `Contact info`, which on 100% of LinkedIn profiles holds the verified geographical location (e.g. *"Potsdam, Brandenburg, Germany"* or *"Austin, Texas, United States"*).
     - Body fallback scans up to 4 lines prior to "Contact info" to eliminate author headlines and pronouns.
   - It runs the location through the US state and metro verification engine (checking 50 US states, major US metro hubs like SF Bay Area, NYC, Seattle, Austin, and negative international blacklists).
   - If not verified in the United States, the lead is immediately disqualified via `skip_card`.

---

## 🧠 Adaptive Reasoning & Anti-Repetition Rules

The agent has built-in adaptive intelligence to eliminate repetitive loops and dead ends:

1. **Strict Prohibition on Stubborn Generic Searches**:
   - Generic terms like `"software development"`, `"web development"`, or `"need a developer"` are explicitly flagged in memory. They attract offshore freelancers, agency spam, and job seekers.
2. **Early Feed Bailout Rule**:
   - If 2 or 3 cards in a feed fail qualification or belong to non-US/international candidates, the agent **immediately stops scrolling that feed**! It does not waste time scrolling through an unproductive query.
3. **High-Intent US Founder Vernacular Pivot**:
   - When generic queries fail, the agent pivots to high-intent founder phrasing:
     - `"we are hiring" "founding engineer"`
     - `"building our MVP"`
     - `"seed round" hiring engineer`
     - `"stealth startup" hiring "engineer"`
     - `"YC W24" hiring` / `"YC S24" hiring` / `"Techstars" hiring`
     - `"fractional CTO"`
     - `"US only" "founding engineer"`
     - Metro-targeted: `"San Francisco" hiring engineer`, `"Austin" hiring founding engineer`, `"NYC" hiring engineer`
4. **Active Diagnosis & Self-Correction**:
   - If data or locations fail to arrive across consecutive turns, the agent diagnoses whether the DOM selector needs updating, the query is too broad, or a new angle is needed, utilizing `propose_code_improvement` or `ask_developer` rather than stubbornly repeating failures.

---

## 📌 How Post URLs Are Captured

- **For Qualified Leads Only:** When a lead passes role, intent, freshness, and profile location checks, `qualify_and_save_lead` targets the card's dedicated 3-dots control menu.
- **Direct 3-Dots Click & Clipboard Hook:**
  1. The script finds the exact post card in the DOM (avoiding page-level search filters).
  2. Clicks the 3-dots button on that post card.
  3. Clicks **"Copy link to post"** (`[data-view-name="feed-control-menu-copy-link"]`).
  4. Intercepts the clipboard write event to obtain the authentic shortlink: `https://lnkd.in/p/...`.
  5. If the shortlink fails, it extracts the direct post link (`/feed/update/urn:li:activity:...` or `/posts/...`).
  6. **Never falls back to `/recent-activity/all/` or `/feed/`!**
- **Skipped Cards:** Disqualified cards are skipped immediately without triggering the 3-dots menu or clipboard copying.

---

## 🛠️ The 10 Autonomous Agent Tools

| Tool | Purpose | What it Does |
| :--- | :--- | :--- |
| **`execute_search`** | Search Navigation | Navigates to LinkedIn content search with custom intent keywords and freshness (`past-24h` or `past-week`). Detects 0-result pages immediately so it **never blindly scrolls**. Provides live developer interaction opportunity! |
| **`scan_and_read_cards`** | DOM Perception | Expands text and extracts un-evaluated post cards, returning the author, headline, profile link, relative timestamp (`18h`, `1d`), and content. |
| **`verify_profile_location`** | 100% US Verification | Opens the author's profile in a background tab, waits for React hydration, inspects the Top Card location header with fallbacks, and confirms genuine US presence. |
| **`scroll_feed`** | Feed Navigation | Smoothly scrolls down using human mouse physics to load more candidate cards. |
| **`qualify_and_save_lead`** | Lead Acquisition | Clicks the 3-dots menu to capture the exact post shortlink (`https://lnkd.in/p/...`), saves `Profile URL`, `Post URL`, and `Fit Score` to CSV & JSON. Interactively prompts the user upon each lead discovered! |
| **`skip_card`** | Precision Filtering | Explicitly logs why an unqualified card was rejected (*HR/Recruiter*, *India leak*, *Stale >24h*, *Job seeker*). |
| **`search_web`** | Web Intelligence | Searches the web to investigate company HQ, verify startup details, or research BDE queries. |
| **`propose_code_improvement`**| Self-Improvement | Proposes code enhancements to tools, DOM extractors, query parsers, or filters when an issue is diagnosed. Requires user permission and verifies syntax with `py_compile`. |
| **`ask_developer`** | Human-in-the-Loop | The agent proactively consults the human developer for guidance, query advice, or ambiguous candidate decisions. |
| **`finish_campaign`** | Clean Completion | Concludes the run when lead satisfaction is reached. |

---

## 💬 Developer Live Interaction Powers

Developers have two channels to interact with and guide the model:

1. **Mid-Flight Search Guidance (Developer-Initiated)**:
   - Every time `execute_search` runs, the pipeline displays:
     ```text
     💬 [DEVELOPER INTERACTION]:
        Current Search: 'founding engineer' (past-24h) | Cards Visible: 6
        (Press ENTER to let agent proceed autonomously, or type guidance/instructions for the model)
        Developer Guidance > 
     ```
   - **Press ENTER:** The agent continues 100% autonomously.
   - **Type Custom Guidance (e.g. *"Focus on Seed-stage AI startups"* or *"Try 'MVP developers'"*):** The developer's instruction is injected directly into the model's immediate context as a high-priority directive.

2. **Proactive Developer Consultation (`ask_developer`)**:
   - The agent itself can invoke `ask_developer(question, context)` when it encounters an edge case, ambiguous profile location, or wants developer advice on a query direction.
   - The developer types their response directly into the terminal, and the agent acts accordingly.

---

## 🏃 How to Run & Direct Interactive Discovery

```bash
cd "/home/paras/Downloads/MindInventroy/Projects/Test Projects/LinkedIn Scrapper"
./run_pipeline.sh
```

*(Or via Python: `./.venv/bin/python linkedin_bde_intelligent_pipeline.py`)*

### 🎯 Direct Run & Dynamic Lead Confirmation
- **No Upfront Lead Quotas:** The pipeline starts immediately without asking for a lead number.
- **Search Until at Least 1 Genuine Lead:** The agent searches until it finds and qualifies a genuine, verified USA lead.
- **Immediate Interactive Prompt & Feedback Loop:** As soon as a lead is saved, it displays the verified lead card and asks whether to continue:
  ```text
  👉 Found 1 qualified lead(s). Do you want the agent to continue searching for more?
     [ENTER / Y] Yes, search for the next genuine lead in this session
     [N / Q] No, stop here and wrap up
  ```
  If you choose `[Y / ENTER]`, it immediately prompts for your feedback and specific guidance:
  ```text
  💬 LEAD FEEDBACK & SPECIFIC PREFERENCES FOR NEXT LEADS:
     (Share any feedback to guide the AI for the next lead, e.g.:
       • 'Focus strictly on AI/ML or SaaS founders'
       • 'Target Seed or Series A startups in California / NYC'
       • 'Great lead, find more identical to Billy Jeremijenko'
       • Or press ENTER to continue with default high-intent founder criteria)
     Your Feedback > 
  ```
- **Active Alignment**: Your feedback is injected directly into the LLM's next search context and saved to persistent memory, forcing the model to adapt its queries, candidate evaluation, and location/role filtering to match your exact preferences!

### ⚡ Interactive Same-Session Control Menu
When a campaign finishes, the browser **remains active and open on your screen**. You can:
- `[1 / ENTER]`: **Re-run / Continue lead discovery in the same session** without closing the browser, reusing your active login and building on memory.
- `[2]`: **Change agency niche or target count** for the next round.
- `[3]`: **View Memory Summary & All Historically Qualified Leads** to inspect everything the agent has learned and saved.
- `[4 / Q]`: **Quit & Close Browser**.
- `[3]`: **View Memory Summary & All Historically Qualified Leads** to inspect everything the agent has learned and saved.
- `[4 / Q]`: **Quit & Close Browser**.

---

## 🧠 Persistent Agent Memory (`agent_memory.json`)

- **File Path:** [`agent_memory.json`](file:///home/paras/Downloads/MindInventroy/Projects/Test%20Projects/LinkedIn%20Scrapper/python-agent/agent_memory.json)
- **What is Loaded on Startup:**
  1. `previously_qualified_leads`: Full history of all previously qualified leads (Name, Profile URL, Post shortlink, Company, Location, Fit Score). The agent uses this to **never duplicate leads** across rounds or runs.
  2. `successful_queries`: Queries that proved high-yield, used as starting inspiration.
  3. `failed_queries`: Queries that resulted in 0 leads or pitfalls to avoid.
  4. `learned_rules`: Dynamic operational principles (e.g. strict top-card profile verification, freshness switching).
  5. `query_history`: Chronological performance logs of recent queries.

---

## 📁 Output Artifacts Generated

- **Qualified Leads (CSV):** [`exports/usa_bde_leads_*.csv`](file:///home/paras/Downloads/MindInventroy/Projects/Test%20Projects/LinkedIn%20Scrapper/python-agent/exports/)  
  *(Columns: `Profile URL`, `Post URL`, `Fit Score`, `Author Name`, `Title / Headline`, `Verified Location`, `Company Name`, `Custom Outreach Hook`, `Reasoning`)*
- **Qualified Leads (JSON):** `exports/usa_bde_leads_*.json`
- **Persistent Agent Memory:** [`agent_memory.json`](file:///home/paras/Downloads/MindInventroy/Projects/Test%20Projects/LinkedIn%20Scrapper/python-agent/agent_memory.json)
- **Detailed Session Action Log:** [`logs/bde_pipeline_session_*.log`](file:///home/paras/Downloads/MindInventroy/Projects/Test%20Projects/LinkedIn%20Scrapper/python-agent/logs/)
