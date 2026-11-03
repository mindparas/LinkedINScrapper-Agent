"""
Adaptive query engine: the agent learns how to search instead of following fixed phrase lists.

Three cooperating parts
  QueryStrategist  an LLM that reads the mission and, later, the evidence of what actually came back
                   (queries, category mix, junk samples) and writes new queries. It diagnoses WHY a
                   query failed ("results are sellers because 'agency' attracts them") and changes tactic.
  QueryLearner     an online Bayesian bandit. Every word and word-pair is a feature with a Beta posterior
                   of "share of returned posts that matched the mission" plus a contamination rate
                   (sellers/recruiters). It is persisted per mission in dataset/query_learning.json, so
                   each run starts smarter. New queries are ranked by Thompson sampling over these
                   posteriors: they generalise to phrases never run before and balance exploring/exploiting.
  QueryEngine      the pool of candidate queries, selection, dry-streak detection, re-planning and the
                   stagnation stop, so a run does not wait out the clock when nothing is matching.
"""

import json
import os
import random
import re
import time
from datetime import datetime

from src import llm
from src.config import BASE_DIR, llm_setting

LEARN_PATH = os.path.join(BASE_DIR, "dataset", "query_learning.json")
STOPWORDS = {"a", "an", "the", "of", "to", "for", "and", "or", "in", "on", "at", "is", "it", "with", "we", "i",
             "our", "my", "us", "are", "be", "can", "you", "your", "any", "that", "this", "who", "do"}
PRIOR_A, PRIOR_B = 0.4, 4.6          # prior belief: roughly 8% of returned posts match


def _words(q):
    return re.findall(r"[a-z0-9\+\#\.]+", (q or "").lower())


def is_exact(query):
    return str(query or "").strip().startswith('"') and str(query).strip().endswith('"')


def features(query):
    w = _words(query)
    uni = [x for x in w if x not in STOPWORDS and len(x) > 1]
    bi = [f"{a} {b}" for a, b in zip(w, w[1:])]
    return list(dict.fromkeys(uni + bi + ["mode:phrase" if is_exact(query) else "mode:keywords"]))


def _int_setting(name, default):
    try:
        return int(llm_setting(name, str(default)))
    except ValueError:
        return default


# ─────────────────────────────────────────────────────────────────────────────
class QueryLearner:
    """Persistent per-mission statistics. ns = mission key ('' for the default mission)."""

    def __init__(self, ns="", path=None):
        self.ns = ns or "default"
        self.path = path or LEARN_PATH
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self.all = json.load(f)
        except Exception:
            self.all = {}
        self.d = self.all.setdefault(self.ns, {"feat": {}, "queries": {}, "fresh": {"24h": [0, 0], "week": [0, 0]}})

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.all, f, ensure_ascii=False)
        except Exception:
            pass

    def observe(self, query, posts, buyers, cats):
        """posts = posts judged; buyers = matches; cats = {category: count}."""
        bad = cats.get("SELLER", 0) + cats.get("RECRUITER", 0)
        for f in features(query):
            s = self.d["feat"].setdefault(f, {"n": 0, "b": 0, "bad": 0, "q": 0})
            s["n"] += posts
            s["b"] += buyers
            s["bad"] += bad
            s["q"] += 1
        qs = self.d["queries"].setdefault(query.lower(), {"runs": 0, "n": 0, "b": 0, "last": ""})
        qs["runs"] += 1
        qs["n"] += posts
        qs["b"] += buyers
        qs["last"] = datetime.now().isoformat(timespec="seconds")
        self.save()

    def observe_freshness(self, cards_24h, cards_week):
        f = self.d.setdefault("fresh", {"24h": [0, 0], "week": [0, 0]})
        f["24h"][0] += 1
        f["24h"][1] += cards_24h
        if cards_week is not None:
            f["week"][0] += 1
            f["week"][1] += cards_week
        self.save()

    # ── scoring ──────────────────────────────────────────────────────────
    def expected_yield(self, query, sample=True):
        fs = features(query)
        if not fs:
            return 0.0
        draws, bad_rates = [], []
        for f in fs:
            s = self.d["feat"].get(f, {"n": 0, "b": 0, "bad": 0})
            a, b = PRIOR_A + s["b"], PRIOR_B + max(s["n"] - s["b"], 0)
            draws.append(random.betavariate(a, b) if sample else a / (a + b))
            if s["n"] >= 6 and s.get("q", 0) >= 2 and not f.startswith("mode:"):
                bad_rates.append(s["bad"] / s["n"])
        score = sum(draws) / len(draws)
        if bad_rates:                                         # words that mostly pull sellers/recruiters
            score *= 1 - min(0.8, 1.5 * (sum(bad_rates) / len(bad_rates)))
        q = self.d["queries"].get(query.lower())
        if q and q["n"] >= 5 and q["b"] == 0:                 # already proven dry
            score *= 0.2
        return score

    def blocked_terms(self, min_posts=8, min_bad=0.5, limit=6):
        out = [(f, s["bad"] / s["n"], s["n"]) for f, s in self.d["feat"].items()
               if s["n"] >= min_posts and s.get("q", 0) >= 2 and s["bad"] / s["n"] >= min_bad and " " not in f
               and not f.startswith("mode:")]
        return sorted(out, key=lambda x: -x[1])[:limit]

    def winners(self, limit=6):
        out = [(q, s["b"], s["n"]) for q, s in self.d["queries"].items() if s["b"] > 0]
        return sorted(out, key=lambda x: -(x[1] / max(x[2], 1)))[:limit]

    def losers(self, limit=8):
        out = [(q, s["n"]) for q, s in self.d["queries"].items() if s["b"] == 0 and s["n"] >= 4]
        return sorted(out, key=lambda x: -x[1])[:limit]

    def week_first(self):
        """True when the 24h filter has been too thin on average to be worth its own page load."""
        f = self.d.get("fresh", {})
        runs, cards = f.get("24h", [0, 0])
        return runs >= 4 and cards / runs < 4


# ─────────────────────────────────────────────────────────────────────────────
STRATEGIST_PROMPT = """You are the search strategist of an autonomous LinkedIn lead-finding agent. You write the LinkedIn CONTENT-SEARCH queries. Finding the right queries is the whole job: the posts exist, the agent only fails when its queries are wrong.

How LinkedIn content search behaves
- It matches keywords against the text of posts (ranked by relevance by default). Short natural phrases of 2-4 words work best; long sentences, quotes and boolean operators return nothing or noise.
- Write what the TARGET AUTHOR would literally type in the post, in their voice (first person: "we need", "looking for", "can anyone recommend", "who can build"). Do not write how an analyst would describe the target.
- Words that sellers, recruiters and marketers use pull THEM instead of buyers (examples: "agency", "services", "solutions", "we help", "hiring", "join our team", "DM me", "expert", "specialist"). Avoid a word when the evidence shows it attracts the wrong authors; keep it only if the post type needs it.
- EXACT PHRASES are the most precise tool. Unquoted words are matched anywhere in a post, so "need a CTO" returns every post that mentions a CTO. A phrase in quotes must appear in that order, so it returns only posts that literally say it. For the posts that carry the need, set "exact": true and give the 3-6 word wording a buyer would really write ("looking for a development partner", "can anyone recommend a dev shop"). Keep exact phrases SHORT (3-4 words) and very common; long or unusual phrasings return zero posts (in testing, 5-6 word phrases such as "any recommendations for software development companies" returned nothing). Use "exact": false (2-4 plain keywords) for a minority of broader probes. Aim for roughly 70% exact phrases.
- SITUATIONS beat service words. Buyers often post about a trigger event without naming any service: a developer or agency left or went silent, a project stalled or is behind schedule, just raised funding and need to build, the current vendor failed. Include several such situation phrases (angle names like trigger_event, vendor_failed, stalled_project); they carry no seller vocabulary.
- Start by avoiding the words "partner", "services", "agency", "solutions" in exact phrases unless the post type truly needs them: they pull sellers.
- Different authors phrase the same need differently. Cover genuinely different ANGLES (direct ask, recommendation request, project announcement, pain/problem statement, stage signal such as just funded or pre-seed, role or skill wording, introduction request...) and invent others that fit the mission. Do not output near-duplicates.
- No city or country names; location is checked later on the profile. Avoid contractions and apostrophes (write "do not", not "don't").

Return JSON only:
{"diagnosis": "1-3 sentences: what the evidence shows about WHY earlier queries failed or worked (empty on the first plan)",
 "strategy": "1-2 sentences: how the new queries differ from before",
 "queries": [{"q": "the words (no quote characters)", "exact": true, "angle": "short_snake_case_angle", "why": "one short clause"}]}"""


class QueryStrategist:
    def __init__(self, mission, niche="", logger=None):
        self.mission = mission
        self.niche = niche
        self.logger = logger

    def _mission_block(self):
        m = self.mission
        parts = [f"MISSION: {m.summary}"]
        if getattr(m, "raw_intent", ""):
            parts.append(f"User's words: {m.raw_intent[:600]}")
        if m.post_types:
            parts.append("Qualifying post types: " + "; ".join(m.post_types))
        parts.append(f"Author: {m.author_profile}")
        if m.must_have:
            parts.append("Must have: " + "; ".join(m.must_have))
        if m.exclude:
            parts.append("Must NOT match: " + "; ".join(m.exclude))
        if self.niche:
            parts.append(f"Searcher's business: {self.niche}")
        return "\n".join(parts)

    def propose(self, n, evidence="", tried=None):
        user = self._mission_block()
        if evidence:
            user += "\n\nEVIDENCE FROM THE SEARCHES SO FAR\n" + evidence
        if tried:
            user += "\n\nALREADY TRIED (do not repeat or lightly reword):\n" + "; ".join(sorted(tried)[:60])
        user += f"\n\nWrite {n} new queries."
        data, _usage, _model = llm.complete_json(STRATEGIST_PROMPT, user, "interpreter", max_tokens=2500, timeout=90)
        from src.agent.mission import _clean_query
        out, seen = [], {t.lower() for t in (tried or [])}
        for item in data.get("queries", []):
            if isinstance(item, str):
                item = {"q": item}
            cq = _clean_query(item.get("q", ""))
            if cq and item.get("exact") and 3 <= len(cq.split()) <= 6:
                cq = f'"{cq}"'
            if cq and cq.lower() not in seen:
                seen.add(cq.lower())
                out.append({"q": cq, "angle": re.sub(r"\W+", "_", str(item.get("angle", "general")).lower())[:30] or "general",
                            "why": str(item.get("why", ""))[:120]})
        return str(data.get("diagnosis", ""))[:500], str(data.get("strategy", ""))[:300], out[:n]


# ─────────────────────────────────────────────────────────────────────────────
class QueryEngine:
    DRY_REPLAN_AFTER = 3          # consecutive queries with no match -> re-plan with fresh evidence
    SEED_QUERIES = 14
    REPLAN_QUERIES = 8

    def __init__(self, mission, niche="", logger=None, builtin=None):
        self.mission = mission
        self.logger = logger
        self.enabled = llm_setting("QUERY_ENGINE", "on").lower() != "off"
        self.stagnation_limit = _int_setting("QUERY_STAGNATION_LIMIT", 6)
        self.learner = QueryLearner(mission.key if not mission.is_default else "")
        self.strategist = QueryStrategist(mission, niche, logger)
        self.pool = []                 # [{q, angle, why, source}]
        self.history = []              # per-query outcomes this run
        self.generation = 0
        self.replans = 0
        self.dry_streak = 0
        self.since_replan = 0           # dry queries since the strategy last changed
        self.last_diagnosis = ""
        self.last_strategy = ""
        self.prepared = False
        self._pick = None
        self._builtin = builtin or {}
        self._add_seed_pool()

    # ── pool ─────────────────────────────────────────────────────────────
    def _add_seed_pool(self):
        for fam, qs in (self.mission.query_families or {}).items():
            for q in qs:
                self._add(q, fam, "from the interpreted mission", "mission")
        if not self.pool:
            for fam, qs in self._builtin.items():
                for q in qs:
                    self._add(q, fam, "built-in fallback phrasing", "builtin")

    def _add(self, q, angle, why, source):
        if q and all(p["q"].lower() != q.lower() for p in self.pool):
            self.pool.append({"q": q, "angle": angle, "why": why, "source": source, "gen": self.generation})

    def tried(self):
        return {h["q"] for h in self.history}

    def prepare(self):
        """Ask the strategist for the first batch (once). Safe to call without an API key."""
        if self.prepared:
            return
        self.prepared = True
        if not (self.enabled and llm.api_key_present()):
            return
        try:
            ev = self._learned_evidence()
            diag, strat, qs = self.strategist.propose(self.SEED_QUERIES, ev, tried={p["q"] for p in self.pool})
            for item in qs:
                self._add(item["q"], item["angle"], item["why"], "strategist")
            self.last_strategy = strat
            if self.logger:
                self.logger.info(f"Query strategist seeded {len(qs)} queries. Strategy: {strat}")
        except Exception as e:
            if self.logger:
                self.logger.error(f"Query strategist unavailable, using mission/builtin queries: {llm.describe_error(e)}")
        self._pick = None

    # ── choosing ─────────────────────────────────────────────────────────
    def suggest(self, skip=None):
        """Next query to run. Cached until a query finishes, so repeated peeks are free and stable."""
        if self._pick and self._pick["q"].lower() not in {s.lower() for s in (skip or ())}:
            return self._pick["q"]
        done = {q.lower() for q in self.tried()} | {s.lower() for s in (skip or ())}
        cands = [p for p in self.pool if p["q"].lower() not in done]
        if not cands:
            return ""
        if self.learner.d["feat"].get("mode:phrase", {"n": 0})["n"] < 20:
            exact = [p for p in cands if is_exact(p["q"])]    # no evidence on phrases yet: try them first
            cands = exact or cands
        last_angles = [h["angle"] for h in self.history[-2:]]
        best, best_score = None, -1.0
        for p in cands:
            score = self.learner.expected_yield(p["q"])
            if p["angle"] in last_angles:
                score *= 0.7                                  # vary the angle
            if p["source"] == "strategist":
                score *= 1.25                                 # written by the strategist with the evidence in hand
            if score > best_score:
                best, best_score = p, score
        self._pick = best
        return best["q"]

    def angle_of(self, query):
        for p in self.pool:
            if p["q"].lower() == (query or "").lower():
                return p["angle"]
        return "agent_choice"

    def predicted_poor(self, query):
        """True when the query's words have a proven record of pulling the wrong authors / nothing."""
        return self.learner.expected_yield(query, sample=False) < 0.015 and \
            any(self.learner.d["feat"].get(f, {}).get("n", 0) >= 10 for f in features(query))

    # ── learning ─────────────────────────────────────────────────────────
    def observe(self, query, freshness, dom_cards, posts, buyers, cats, leads, samples):
        """Record one finished query. Returns a short event string when the brain changed, else ''."""
        angle = self.angle_of(query)
        self.learner.observe(query, posts, buyers, cats)
        self.history.append({"q": query, "angle": angle, "posts": posts, "buyers": buyers, "cats": dict(cats),
                             "leads": leads, "cards": dom_cards, "fresh": freshness, "samples": samples[:4]})
        self.dry_streak = 0 if buyers > 0 else self.dry_streak + 1
        self.since_replan = 0 if buyers > 0 else self.since_replan + 1
        self._pick = None
        event = ""
        contaminated = posts >= 4 and (cats.get("SELLER", 0) + cats.get("RECRUITER", 0)) >= 0.5 * posts
        need = 2 if contaminated and self.since_replan >= 2 and self._prev_contaminated() else self.DRY_REPLAN_AFTER
        if self.enabled and llm.api_key_present() and (self.since_replan >= need or self._pool_exhausted()):
            event = self.replan()
        return event

    def _prev_contaminated(self):
        h = self.history[-2]
        return h["posts"] >= 4 and (h["cats"].get("SELLER", 0) + h["cats"].get("RECRUITER", 0)) >= 0.5 * h["posts"]

    def _pool_exhausted(self):
        done = {q.lower() for q in self.tried()}
        return all(p["q"].lower() in done for p in self.pool)

    def stagnant(self):
        return self.stagnation_limit > 0 and self.dry_streak >= self.stagnation_limit and \
            not any(h["leads"] for h in self.history)

    def freshness_first(self):
        return "past-week" if self.learner.week_first() else "past-24h"

    # ── re-planning (the "change the brain" step) ────────────────────────
    def _learned_evidence(self):
        lines = []
        w = self.learner.winners()
        if w:
            lines.append("Queries that found matching posts in earlier runs: " +
                         "; ".join(f"'{q}' ({b} of {n} posts)" for q, b, n in w))
        bt = self.learner.blocked_terms()
        if bt:
            lines.append("Words that mostly pulled sellers/recruiters: " +
                         ", ".join(f"'{t}' ({r:.0%} of {n} posts)" for t, r, n in bt))
        lo = self.learner.losers()
        if lo:
            lines.append("Queries that returned posts but no matches: " + "; ".join(f"'{q}'" for q, _ in lo))
        return "\n".join(lines)

    def _run_evidence(self):
        lines = []
        for h in self.history[-8:]:
            cats = ", ".join(f"{k}:{v}" for k, v in sorted(h["cats"].items(), key=lambda kv: -kv[1])[:4])
            lines.append(f"- '{h['q']}' [{h['angle']}]: {h['cards']} posts on page, {h['posts']} judged, "
                         f"{h['buyers']} matched ({cats or 'none returned'})")
        samples = [s for h in self.history[-5:] for s in h["samples"]][:8]
        if samples:
            lines.append("Examples of posts these queries returned and why they were rejected:")
            lines += [f"  * [{s['cat']}] {s['who']} - \"{s['text']}\" -> {s['why']}" for s in samples]
        extra = self._learned_evidence()
        return "\n".join(lines) + ("\n" + extra if extra else "")

    def replan(self):
        self.replans += 1
        self.generation += 1
        self.since_replan = 0
        try:
            diag, strat, qs = self.strategist.propose(self.REPLAN_QUERIES, self._run_evidence(), tried=self.tried() | {p["q"] for p in self.pool})
        except Exception as e:
            if self.logger:
                self.logger.error(f"Query re-plan failed: {llm.describe_error(e)}")
            return ""
        for item in qs:
            self._add(item["q"], item["angle"], item["why"], "strategist")
        self.last_diagnosis, self.last_strategy = diag, strat
        self._pick = None
        if self.logger:
            self.logger.info(f"QUERY RE-PLAN #{self.replans}: {diag} | {strat} | +{len(qs)} queries")
        return f"New search brain #{self.generation}: {diag} New approach: {strat}"

    # ── reporting ────────────────────────────────────────────────────────
    def summary(self):
        return {
            "enabled": self.enabled, "replans": self.replans, "generations": self.generation,
            "pool_size": len(self.pool), "queries_run": len(self.history),
            "dry_streak_at_end": self.dry_streak, "last_diagnosis": self.last_diagnosis,
            "last_strategy": self.last_strategy,
            "angles_that_matched": sorted({h["angle"] for h in self.history if h["buyers"]}),
            "avoid_terms": [t for t, _, _ in self.learner.blocked_terms()],
        }
