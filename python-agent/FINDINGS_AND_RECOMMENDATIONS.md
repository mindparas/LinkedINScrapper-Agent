# LinkedIn Lead Agent: Findings and Recommendations

Written 2026-11-03. This document separates **what was measured** from **what is a hypothesis**. Where something has not been tested, it says so.

---

## 1. Summary

- The agent works end to end: intent in, mission interpreted, queries planned, posts judged, leads saved, metrics report out.
- **It has not yet found a verified lead with the new Claude-based setup.** Across today's three Claude runs (about 15 queries, about 100 judged posts) the result was 0 leads. Earlier OpenAI batch runs found 1 lead that still needs manual verification.
- **The bottleneck is not the judge, the model, or the intent. It is what the LinkedIn search returns.** Searches return posts that mention the topic, not posts that ask for help. The judge rejected them correctly (checked by hand on 21 near-misses).
- Three things are unknown and decide what to do next: (a) whether buyer posts for this intent exist in volume in a 24h or 1-week window, (b) whether relevance sorting surfaces them, (c) whether a narrower intent does better. The next test in section 7 answers these.

---

## 2. What was built

### 2.1 Intent-driven search (feature 1)
The user describes the posts wanted. An LLM turns it into a **Mission** (summary, post types, author profile, must-have, exclude, location scope, seed queries). Everything downstream follows the mission: query planning, the judge prompt, location checks, outreach text, the agent's system prompt.

| Piece | File |
|---|---|
| Mission + interpreter + confirmation loop | `src/agent/mission.py` |
| Mission-aware judge prompt | `src/judge/lead_judge.py` |
| Per-mission memory namespaces (skip list, query stats) | `src/agent/planner.py`, `src/tools/agent_tools.py` |
| `--intent` flag, interactive prompt | `run_autonomous_leads.py`, `src/agent/cli.py` |

### 2.2 Post-run performance metrics (feature 2)
Funnel, efficiency, quality, per-query table, cost estimate, LinkedIn budget use, insights, comparison with the previous run. Full JSON in `exports/metrics_<timestamp>.json`, history in `dataset/run_history.jsonl`. (`src/metrics.py`)

### 2.3 Claude and OpenAI support
All model calls go through `src/llm.py`. Choose with `LLM_PROVIDER=anthropic|openai`; per-role models with `LLM_MODEL_JUDGE`, `LLM_MODEL_AGENT`, `LLM_MODEL_INTERPRETER`. Default is Claude Sonnet 5.5 for all three roles when an Anthropic key exists. The metrics report prices each role with its own model. `.env.example` and the README document the settings.

Claude-specific choices:
- No `temperature` is sent (Sonnet 5.5 and Haiku 5.5 reject non-default values).
- Thinking is turned off for the agent loop (`between_tools` on Sonnet 5.5). The loop edits older history, which would invalidate replayed thinking blocks.
- The judge and interpreter use low and medium effort.

### 2.4 Adaptive query engine (this session)
`src/agent/query_engine.py`, wired into `planner.py` and `agent_tools.py`.

- **Strategist (LLM):** writes about 14 queries across different angles in the target author's voice; later re-plans from evidence.
- **Re-planning:** after 3 consecutive queries with no match (2 if results were mostly sellers/recruiters) it reads the category mix and junk examples, writes a diagnosis, and produces new queries with a different approach. The planner can replace a query the agent picked.
- **Learner:** an online Bayesian bandit. Each word and word pair has a Beta posterior for "returns matching posts" and a contamination rate for sellers/recruiters. Candidates are ranked by Thompson sampling. Stored per mission in `dataset/query_learning.json`.
- **Exact phrases:** the strategist can propose quoted phrases (3 to 6 words); they are tried first until the learner has evidence on them.
- **Time filters:** past-24h first; past-week added when 24h returns under 10 posts (past-week contains the 24h posts, newest first). If 24h is usually thin for a mission, it goes straight to past-week.
- **Early cutoffs:** a query is abandoned after 8 judged posts with no match; a run stops if 9 queries in a row match nothing (`QUERY_STAGNATION_LIMIT`).

Settings: `QUERY_ENGINE=off` turns the engine off and restores the fixed query lists.

---

## 3. What was measured

### 3.1 Runs

| Run | Setup | Searches | Posts judged | Matches | Leads | Cost |
|---|---|---|---|---|---|---|
| Intent batch (6 intents rewritten from `intents.md`) | OpenAI gpt-4o-mini | many | not recorded in this note | intents 1 and 2: none; intent 3: 1 lead needing manual verification (Grace A. Huntley, Right Balance) | 1 | about $0.054 for 3 intents |
| Intents 4, 5, 6 | OpenAI | n/a | n/a | n/a | n/a | Not run: OpenAI `429 insufficient_quota` |
| Broad intent, run A | Claude Sonnet 5.5, 5.6 min, interrupted | 9 | 32 | 0 | 0 | $0.35 |
| Broad intent, run B | Claude, 5.2 min, full-scan queries | 5 | 61 | 0 | 0 | $0.46 |
| Broad intent, run C | Claude, 3 quoted-phrase searches | 3 | 8 | 0 | 0 | $0.11 |

The daily LinkedIn search budget (75) was used up at the end of run C (69 used by the cap I set; 66 before run C).

### 3.2 Judge accuracy
In run B, 61 posts were judged: 38 no-need, 13 seller, 7 investor/media, 2 recruiter, 1 non-US. I read the 21 posts that looked closest to a request. The judge was right on all of them: AI thought-leadership, event promotion, a visa explainer, a podcast, a security write-up. **The judge is not the problem.**

### 3.3 Query behaviour
- **Unquoted multi-word queries match words anywhere in a post.** "need a CTO" returned any post mentioning a CTO. Run B: three of the first four strategist queries were identity-style ("non technical founder", "need a CTO", "who built your MVP") and returned noise.
- **Queries containing "agency" pull sellers.** Run A: "looking for dev agency", "need software agency" returned lead-gen sellers, agency owners and hiring posts.
- **Long exact phrases return nothing.** Run C: `"any recommendations for software development companies"` and `"looking to outsource app development"` each returned 0 posts in both 24h and week.
- **Short exact phrases that do match pull sellers.** Run C: `"looking for a development partner"` returned 6 posts; 6 of 8 judged were sellers (agencies recruiting commission-based sales partners).
- **Supply is thin and repetitive.** Each search returned 0 to 12 post cards; in run B, 59% of posts had already been seen in earlier runs.

### 3.4 Cost
- The cost of a 5-minute run on Claude Sonnet 5.5 was $0.35 to $0.46 when queries were fully scanned, and $0.11 with the early cutoff. My earlier up-front estimate (about $0.03 per minute) was too low for full-scan runs: agent turns resend a growing history.
- A strategist call costs about $0.03.
- Using `LLM_MODEL_AGENT=claude-haiku-5-5` should cut the agent-loop share by about 80% (not measured).

### 3.5 Pricing used (per 1M tokens, input/output)
Fable 5.1 $10/$50, Opus 5.5 $4/$20, Sonnet 5.5 $2/$10, Haiku 5.5 $0.10/$0.50, gpt-4o-mini $0.15/$0.60. OpenAI figures come from the constants that were already in the code; I could not check current OpenAI prices.

---

## 4. Findings and diagnosis

1. **The search method is the limit.** Keyword search ranks by recency among posts that mention the words. Buyer posts are a tiny share of all posts that mention "developer", "MVP" or "CTO". Hypothesis, supported by 3 runs.
2. **Seller vocabulary overlaps buyer vocabulary.** "Development partner", "agency", "dev shop" are the words both sides use, and sellers post far more often. Measured in runs A and C.
3. **Exact phrases are a precision tool with a narrow sweet spot.** Too long returns zero; short and generic returns sellers. The right phrases have not yet been found.
4. **Time filter is not the cause.** Past-week contains past-24h; checking both barely changed volumes.
5. **First-batch query quality was weak.** The strategist's first batch contained identity-style queries that wasted about 45 posts and about 3 minutes before the first re-plan. (Mitigated, not solved: the dry-query cutoff now limits the cost.)
6. **Daily search budget (75) caps experimentation.** A full day allows about 10 to 12 queries at the current pace of 35 to 50 seconds per search.

---

## 5. Known defects (not yet fixed)

| # | Defect | Impact | Suggested fix |
|---|---|---|---|
| 1 | `qualify_and_save_lead` prefers the model-supplied `profile_url` over the scanned card's `author_url` (`clean_profile_url = (profile_url or card.get("author_url", ""))`). Earlier output showed a likely fabricated URL (`amine-khalil-123456`). | A saved lead could point to a wrong or non-existent profile. | Always use the card's `author_url`; ignore the model value. |
| 2 | City-anchored variants of queries with 4 or more words return nothing. | Wasted searches (default mission and US-scoped missions). | Do not add a city to queries of 4+ words. |
| 3 | Metrics: the "earlier runs" duplicate insight is misleading. | Confusing report. | Reword to "X% were seen in earlier runs, so fresh supply is limited" only when above a threshold. |
| 4 | Metrics: a dead LLM (bad key, no credit) is not flagged and the stop reason shows `time_limit`. | A run can look like a search failure when the model was unreachable. | Stop the run and report an `llm_unavailable` reason after N consecutive agent or judge failures. |
| 5 | The one saved lead (Grace A. Huntley, Right Balance) has not been verified by hand. | Unknown quality. | Verify manually before using it as evidence. |
| 6 | The Anthropic `.env` handling: the `.env` file contains a bare OpenAI key on its own line. | A secret was printed once into a tool output in this session. | Rotate that key; keep `.env` out of git. |

---

## 6. Recommended changes (priority order)

### P1: Fix the search signal (most likely to change results)
1. **Sort by relevance, not only by date.** The code forces `sortBy=date_posted`. Relevance-ranked results may put posts that contain the exact wording first. Make it a per-search choice the learner can compare. *Untested.*
2. **Search for situations, not for the service.** Intents built on a trigger event ("our developer left", "our MVP is stalled", "just raised and need to build", "agency dropped us") describe buyers who post less often but whose posts contain no seller vocabulary. Provide 2 or 3 such intents as presets. *Untested.*
3. **Use short, common exact phrases (3 to 4 words).** Examples to test: `"need a developer"`, `"looking for developers"`, `"need an MVP"`. Already encouraged in the strategist prompt. *Untested.*
4. **Seed negative evidence.** Start each mission with known bad words ("partner", "services", "agency") so the first batch avoids them. The learner already learns this after two bad queries.

### P2: Make failure cheaper and faster
5. **Judge only a sample first.** Judge 4 posts per query; continue only if at least one is a plausible match (the dry-query cutoff does this at 8 posts).
6. **Cheaper agent loop.** Set `LLM_MODEL_AGENT=claude-haiku-5-5`; keep Sonnet 5.5 for the judge and strategist. Measure before keeping.
7. **Pre-filter obvious junk without an LLM call** for custom missions (for example "we are hiring", "join our team", event promotion) using a short, mission-neutral rule list.
8. **Lower the stagnation limit for short runs** (for example 6) so a 5-minute test stops when it is clearly dry.

### P3: Correctness and reporting
9. Fix defects 1 to 4 in section 5.
10. Add a metrics section showing query mode (phrase or keywords) results, so the learner's choices are visible.
11. Record the judge cache and learner files in `.gitignore` (done for `query_learning.json`, `run_history.jsonl`, `judge_cache.json`).

### P4: Strategy (decide with the BDE team)
12. **LinkedIn content search may be the wrong main source for this intent.** If section 7 does not produce leads, consider other sources: posts under hiring-adjacent hashtags, founder communities, or a smaller list of target accounts followed over time. This is a product decision, not a code change.
13. **Account safety stays as is.** The 75 searches and 60 profile visits per day are conservative on purpose; do not raise them to compensate for a weak search signal.

---

## 7. Next test (needs a fresh search budget)

Run on a new day. Budget about 12 searches. Run the changes in this order, one at a time, so results can be attributed:

1. **Short exact phrases, newest-first** (current code): 4 searches. Expect: more posts than long phrases; record the seller share.
2. **Same phrases, relevance sort** (after change P1.1): 4 searches. Compare matches per 10 posts with step 1.
3. **A situation-based intent** (P1.2), for example: "US founders who say their developer, freelancer or agency left or failed and who now need someone to take over or rebuild their app": 4 searches.

Decision rule:
- If any step yields 1 or more genuine buyers per 20 judged posts, continue with that approach and let the learner tune it.
- If all three yield 0 in about 60 judged posts, stop tuning LinkedIn keyword search and take the P4 discussion to the team.

How to run (example):
```bash
./run_leads.sh -n 5 -t 6 --niche "Software, mobile and AI development agency" --intent "<intent text>"
```
Use `BDE_MAX_SEARCHES_PER_DAY=<used today + 4>` in the shell to cap a test run to a fixed number of searches.

---

## 8. Open questions

- How many genuine buyer posts per day exist for each intent in `intents_rewritten.md`? No source of ground truth exists yet. A manual check (a person runs the same searches in a browser and counts) would settle whether the agent or the market is the limit.
- Does Claude Sonnet 5.5 judge differently from gpt-4o-mini on the same posts? Proposed comparison: run both on about 100 saved cards in `dataset/cards.jsonl` and review only the disagreements. Not done.
- Are intents 4, 5 and 6 (MVP build, product rescue, specialised capability) more productive than the broad intent? They were not run (OpenAI quota failure). Run `.venv/bin/python run_intents.py --only 4,5,6` on a fresh budget.

---

## 9. Reference

| Item | Location |
|---|---|
| Intents (original / rewritten) | `intents.md`, `intents_rewritten.md` |
| Batch runner | `run_intents.py` |
| Batch report | `exports/intents_report_2026-11-03_132929.{md,json}` |
| Broad-intent run logs | `logs/broad_run_5min.txt`, `logs/quoted_test.txt` |
| Metrics reports | `exports/metrics_*.json` |
| Learner state | `dataset/query_learning.json` |
| Judge cache | `dataset/judge_cache.json` |
| Run history | `dataset/run_history.jsonl` |
| Settings template | `.env.example` |
