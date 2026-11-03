"""
Run performance metrics: collected while the agent works, summarised when it finishes.

Output: a console scorecard, exports/metrics_<timestamp>.json (full detail) and one line appended to
dataset/run_history.jsonl so each run can be compared with the previous one.
"""

import os
import json
import time
from collections import Counter
from datetime import datetime

from src.config import BASE_DIR, Style

# Cost figures are ESTIMATES from per-model list prices in src/llm.py (PRICES).

from src import llm

HISTORY_PATH = os.path.join(BASE_DIR, "dataset", "run_history.jsonl")
STOP_LABELS = {
    "target_reached": "Target lead count reached",
    "time_limit": "Time limit reached",
    "safety_halt": "Stopped by account-safety guard",
    "stagnation": "Stopped early: searches kept matching nothing",
    "turn_cap": "Turn cap reached",
    "agent_finished": "Agent ended the campaign",
    "error": "Crashed with an error",
    "interrupted": "Interrupted by the user",
}


def _pct(a, b):
    return round(100.0 * a / b, 1) if b else 0.0


def _div(a, b, nd=2):
    return round(a / b, nd) if b else 0.0


class RunMetrics:
    def __init__(self, mission=None, target=0, starting_leads=0):
        self.started = time.time()
        self.started_at = datetime.now().isoformat(timespec="seconds")
        self.mission = mission
        self.target = target
        self.starting_leads = starting_leads
        self.c = Counter()
        self.tool_calls = Counter()
        self.judged_categories = Counter()
        self.queries = []
        self.leads = []
        self.first_lead_sec = None
        self.stop_reason = ""
        self.turns = 0

    # ── collection hooks ─────────────────────────────────────────────────
    def inc(self, key, n=1):
        self.c[key] += n

    def tool(self, name):
        self.tool_calls[name] += 1

    def agent_llm(self, usage=None, ok=True):
        self.c["agent_llm_calls" if ok else "agent_llm_errors"] += 1
        if usage:
            self.c["agent_prompt_tokens"] += int(usage.get("prompt_tokens", 0) or 0)
            self.c["agent_completion_tokens"] += int(usage.get("completion_tokens", 0) or 0)

    def judged(self, category):
        self.c["judged"] += 1
        self.judged_categories[category] += 1

    def query_done(self, entry):
        self.queries.append(entry)

    def lead_saved(self, author, headline, query, verdict, fit_score, location):
        if self.first_lead_sec is None:
            self.first_lead_sec = round(time.time() - self.started, 1)
        v = verdict or {}
        self.leads.append({
            "author": author, "headline": (headline or "")[:120], "query": query,
            "need_type": v.get("need_type", ""), "confidence": v.get("confidence"),
            "fit_score": fit_score, "location": location,
            "found_after_sec": round(time.time() - self.started, 1),
        })

    # ── report ───────────────────────────────────────────────────────────
    def build_report(self, judge=None, usage=None, leads_total=0, stop_reason="", turns=0, halt_reason="", engine=None):
        c = self.c
        dur = max(time.time() - self.started, 0.001)
        leads = len(self.leads)
        searches = c["searches"]
        judged = c["judged"]
        buyers = c["judge_buyers"]
        new_cards = max(c["dom_cards_seen"] - c["known_duplicates"] - c["too_short"], 0)

        judge_calls = getattr(judge, "calls", 0)
        judge_hits = getattr(judge, "cache_hits", 0)
        j_in, j_out = getattr(judge, "prompt_tokens", 0), getattr(judge, "completion_tokens", 0)
        a_in, a_out = c["agent_prompt_tokens"], c["agent_completion_tokens"]
        agent_model, judge_model = llm.model_for("agent"), getattr(judge, "model", None) or llm.model_for("judge")
        ap, jp = llm.price_for(agent_model), llm.price_for(judge_model)
        cost = (a_in * ap[0] + a_out * ap[1] + j_in * jp[0] + j_out * jp[1]) / 1e6

        confs = [l["confidence"] for l in self.leads if isinstance(l.get("confidence"), (int, float))]
        fits = [l["fit_score"] for l in self.leads if isinstance(l.get("fit_score"), (int, float))]
        need_types = Counter(l["need_type"] for l in self.leads if l.get("need_type"))

        funnel = [
            ("Posts seen on page", c["dom_cards_seen"]),
            ("New posts (not seen before)", new_cards),
            ("Judged by LLM", judged),
            ("Matched the mission", buyers),
            ("Passed author/location checks", c["location_confirmed"]),
            ("Saved as leads", leads),
        ]

        report = {
            "run": {
                "started_at": self.started_at,
                "ended_at": datetime.now().isoformat(timespec="seconds"),
                "duration_sec": round(dur, 1),
                "stop_reason": stop_reason,
                "stop_label": STOP_LABELS.get(stop_reason, stop_reason),
                "halt_reason": halt_reason,
                "target_leads": self.target,
                "leads_found": leads,
                "goal_met": leads >= self.target > 0,
                "leads_in_session_csv": leads_total,
                "agent_turns": turns,
            },
            "mission": {
                "title": getattr(self.mission, "title", ""),
                "summary": getattr(self.mission, "summary", ""),
                "custom": bool(self.mission and not self.mission.is_default),
                "location_scope": getattr(self.mission, "location_scope", "US"),
                "raw_intent": getattr(self.mission, "raw_intent", ""),
            },
            "funnel": [{"stage": s, "count": n} for s, n in funnel],
            "efficiency": {
                "leads_per_hour": _div(leads * 3600, max(dur, 60)),  # runs under a minute are rated as one minute
                "minutes_per_lead": _div(dur / 60, leads, 1) if leads else None,
                "seconds_to_first_lead": self.first_lead_sec,
                "searches_per_lead": _div(searches, leads, 1) if leads else None,
                "posts_judged_per_lead": _div(judged, leads, 1) if leads else None,
                "judge_match_rate_pct": _pct(buyers, judged),
                "lead_conversion_of_judged_pct": _pct(leads, judged),
                "duplicate_post_rate_pct": _pct(c["known_duplicates"], c["dom_cards_seen"]),
                "zero_result_search_rate_pct": _pct(c["zero_result_searches"], searches),
                "location_pass_rate_pct": _pct(c["location_confirmed"], c["profile_visits"]) if c["profile_visits"] else None,
            },
            "quality": {
                "avg_judge_confidence": round(sum(confs) / len(confs), 2) if confs else None,
                "min_judge_confidence": round(min(confs), 2) if confs else None,
                "avg_fit_score": round(sum(fits) / len(fits), 1) if fits else None,
                "need_types": dict(need_types),
                "judged_categories": dict(self.judged_categories.most_common()),
            },
            "search": {
                "searches": searches,
                "zero_result_searches": c["zero_result_searches"],
                "weekly_fallbacks": c["weekly_fallbacks"],
                "scrolls": c["scrolls"],
                "profile_visits": c["profile_visits"],
                "non_us_rejected_after_visit": c["non_us_rejected"],
                "auto_rejected_posts": c["auto_rejected"],
                "prefiltered_without_llm": c["prefiltered"],
                "llm_skips": c["llm_skips"],
                "lead_save_rejections": c["lead_rejections"],
            },
            "cost": {
                "agent_llm_calls": c["agent_llm_calls"],
                "agent_llm_errors": c["agent_llm_errors"],
                "judge_api_calls": judge_calls,
                "judge_cache_hits": judge_hits,
                "judge_errors": getattr(judge, "errors", 0),
                "tokens_in": a_in + j_in,
                "tokens_out": a_out + j_out,
                "provider": llm.provider(), "agent_model": agent_model, "judge_model": judge_model,
                "estimated_usd": round(cost, 4),
                "estimated_usd_per_lead": round(cost / leads, 4) if leads else None,
            },
            "safety": {
                "searches_used_today": usage.used("searches") if usage else None,
                "profile_visits_used_today": usage.used("profile_visits") if usage else None,
                "searches_left_today": usage.remaining("searches") if usage else None,
                "profile_visits_left_today": usage.remaining("profile_visits") if usage else None,
            },
            "tool_calls": dict(self.tool_calls.most_common()),
            "queries": self.queries,
            "query_engine": engine.summary() if engine is not None else None,
            "leads": self.leads,
        }
        report["insights"] = self._insights(report)
        return report

    def _insights(self, r):
        out = []
        run, eff, srch, cost = r["run"], r["efficiency"], r["search"], r["cost"]
        productive = [q for q in r["queries"] if q.get("leads")]
        matched = [q for q in r["queries"] if q.get("matches")]
        if run["leads_found"] == 0:
            if run["stop_reason"] == "safety_halt":
                out.append(f"No leads: the run was stopped early ({run['halt_reason'] or 'account-safety guard'}).")
            elif r["funnel"][2]["count"] == 0:
                out.append("No leads: no new posts reached the judge (searches empty or everything already seen).")
            elif r["funnel"][3]["count"] == 0:
                out.append("No leads: posts were judged but none matched the mission - try different search phrasing or a broader mission.")
            else:
                out.append("No leads: posts matched the mission but failed the author/location checks.")
        elif not run["goal_met"]:
            out.append(f"Found {run['leads_found']} of {run['target_leads']} requested leads before stopping ({run['stop_label'].lower()}).")
        if productive:
            top = max(productive, key=lambda q: q["leads"])
            out.append(f"Best query: '{top['query']}' produced {top['leads']} lead(s) from {top['posts_judged']} posts.")
            if len(productive) == 1 and len(r["queries"]) > 3:
                out.append(f"All leads came from 1 of {len(r['queries'])} queries - the other phrasings added little.")
        elif matched:
            out.append(f"{len(matched)} queries surfaced mission matches, but none passed the location/author checks.")
        if eff["zero_result_search_rate_pct"] >= 25 and srch["searches"] >= 4:
            out.append(f"{eff['zero_result_search_rate_pct']:.0f}% of searches returned nothing - queries may be too narrow.")
        if eff["duplicate_post_rate_pct"] >= 60:
            out.append(f"{eff['duplicate_post_rate_pct']:.0f}% of posts were seen in earlier runs, so fresh supply for these queries is limited.")
        if eff["location_pass_rate_pct"] is not None and srch["profile_visits"] >= 3 and eff["location_pass_rate_pct"] < 50:
            out.append(f"Only {eff['location_pass_rate_pct']:.0f}% of profile visits confirmed the required location.")
        if cost["judge_errors"] or cost["agent_llm_errors"]:
            out.append(f"{cost['judge_errors']} judge and {cost['agent_llm_errors']} agent LLM call(s) failed - check the API key/rate limits.")
        left = r["safety"]["searches_left_today"]
        if left is not None and left <= 10:
            out.append(f"Only {left} LinkedIn searches left in today's safety budget.")
        return out

    # ── output ───────────────────────────────────────────────────────────
    @staticmethod
    def _fmt_dur(sec):
        sec = int(sec)
        return f"{sec // 3600}h {sec % 3600 // 60}m" if sec >= 3600 else f"{sec // 60}m {sec % 60:02d}s"

    @staticmethod
    def previous_run():
        try:
            with open(HISTORY_PATH, "r", encoding="utf-8") as f:
                lines = [l for l in f if l.strip()]
            return json.loads(lines[-1]) if lines else None
        except Exception:
            return None

    def render(self, r, prev=None):
        B, D, X = Style.BOLD, Style.DIM, Style.RESET
        run, eff, q, srch, cost, saf = r["run"], r["efficiency"], r["quality"], r["search"], r["cost"], r["safety"]
        ok = run["goal_met"]
        col = Style.GREEN if ok else (Style.YELLOW if run["leads_found"] else Style.RED)
        bar = "=" * 80
        lines = ["", f"{Style.CYAN}{B}{bar}", " 📊 RUN PERFORMANCE METRICS", f"{bar}{X}"]
        lines.append(f" Mission : {B}{r['mission']['title']}{X}" + (f" {D}(custom){X}" if r["mission"]["custom"] else f" {D}(default){X}"))
        lines.append(f" Result  : {col}{B}{run['leads_found']}/{run['target_leads']} leads{X}  in {self._fmt_dur(run['duration_sec'])}"
                     f"  |  stopped: {run['stop_label']}")
        if prev:
            d = run["leads_found"] - prev.get("leads_found", 0)
            lines.append(f" {D}vs previous run: {prev.get('leads_found', 0)} leads, {prev.get('leads_per_hour', 0)}/h "
                         f"→ now {run['leads_found']} leads, {eff['leads_per_hour']}/h ({'+' if d >= 0 else ''}{d} leads){X}")

        lines.append(f"\n {B}Funnel{X} (posts → leads)")
        top = max(r["funnel"][0]["count"], 1)
        prev_n = None
        for st in r["funnel"]:
            n = st["count"]
            bar_len = int(30 * n / top)
            step = f"  {D}({_pct(n, prev_n):.0f}% of previous){X}" if prev_n else ""
            lines.append(f"  {st['stage']:<31}{n:>5}  {Style.CYAN}{'█' * bar_len}{X}{step}")
            prev_n = n if n else None

        lines.append(f"\n {B}Efficiency{X}")
        lines.append(f"  Leads/hour: {eff['leads_per_hour']}   Min/lead: {eff['minutes_per_lead'] if eff['minutes_per_lead'] is not None else '-'}"
                     f"   First lead after: {self._fmt_dur(eff['seconds_to_first_lead']) if eff['seconds_to_first_lead'] is not None else '-'}")
        lines.append(f"  Searches/lead: {eff['searches_per_lead'] if eff['searches_per_lead'] is not None else '-'}"
                     f"   Posts judged/lead: {eff['posts_judged_per_lead'] if eff['posts_judged_per_lead'] is not None else '-'}"
                     f"   Judge match rate: {eff['judge_match_rate_pct']}%")
        lines.append(f"  Duplicate posts: {eff['duplicate_post_rate_pct']}%   Empty searches: {eff['zero_result_search_rate_pct']}% "
                     f"({srch['zero_result_searches']}/{srch['searches']})")

        lines.append(f"\n {B}Lead quality{X}")
        lines.append(f"  Avg judge confidence: {q['avg_judge_confidence'] if q['avg_judge_confidence'] is not None else '-'}"
                     f"   Avg fit score: {q['avg_fit_score'] if q['avg_fit_score'] is not None else '-'}"
                     f"   Need types: {', '.join(f'{k}×{v}' for k, v in q['need_types'].items()) or '-'}")
        if q["judged_categories"]:
            lines.append("  Judged posts by category: " + ", ".join(f"{k} {v}" for k, v in list(q["judged_categories"].items())[:6]))

        if r["queries"]:
            lines.append(f"\n {B}Queries{X} (posts judged / matches / leads)")
            for e in sorted(r["queries"], key=lambda e: (-e["leads"], -e["matches"], -e["posts_judged"]))[:8]:
                mark = "✅" if e["leads"] else ("➖" if e["matches"] else "  ")
                lines.append(f"  {mark} {e['query'][:42]:<42} {e['posts_judged']:>3} / {e['matches']:>2} / {e['leads']:>2}   {D}{e.get('freshness', '')}{X}")
            if len(r["queries"]) > 8:
                lines.append(f"  {D}… {len(r['queries']) - 8} more in the JSON report{X}")

        qe = r.get("query_engine")
        if qe:
            lines.append(f"\n {B}Query learning{X}")
            lines.append(f"  {qe['queries_run']} queries run, {qe['replans']} strategy change(s), {qe['pool_size']} candidates planned")
            if qe["last_diagnosis"]:
                lines.append(f"  Diagnosis: {qe['last_diagnosis'][:200]}")
            if qe["avoid_terms"]:
                lines.append(f"  Learned to avoid: {', '.join(qe['avoid_terms'])}")
            if qe["angles_that_matched"]:
                lines.append(f"  Angles that matched: {', '.join(qe['angles_that_matched'])}")

        lines.append(f"\n {B}Cost & safety{X}")
        lines.append(f"  LLM: {cost['agent_llm_calls']} agent calls + {cost['judge_api_calls']} judge calls ({cost['judge_cache_hits']} cache hits)"
                     f"   ~${cost['estimated_usd']:.3f}" + (f" (${cost['estimated_usd_per_lead']:.3f}/lead)" if cost["estimated_usd_per_lead"] else ""))
        lines.append(f"  LinkedIn today: {saf['searches_used_today']} searches ({saf['searches_left_today']} left), "
                     f"{saf['profile_visits_used_today']} profile visits ({saf['profile_visits_left_today']} left)   This run: {srch['profile_visits']} visits")

        if r["insights"]:
            lines.append(f"\n {B}Insights{X}")
            lines += [f"  • {i}" for i in r["insights"]]
        lines.append(f"{Style.CYAN}{B}{bar}{X}")
        return "\n".join(lines)

    def save(self, r):
        """Writes the JSON report and appends a one-line summary to the run history. Returns the report path."""
        path = ""
        try:
            out_dir = os.path.join(BASE_DIR, "exports")
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(out_dir, f"metrics_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(r, f, indent=2, ensure_ascii=False)
        except Exception:
            path = ""
        try:
            os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
            with open(HISTORY_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "started_at": r["run"]["started_at"], "mission": r["mission"]["title"],
                    "duration_sec": r["run"]["duration_sec"], "leads_found": r["run"]["leads_found"],
                    "target_leads": r["run"]["target_leads"], "leads_per_hour": r["efficiency"]["leads_per_hour"],
                    "searches": r["search"]["searches"], "judged": r["funnel"][2]["count"],
                    "estimated_usd": r["cost"]["estimated_usd"], "stop_reason": r["run"]["stop_reason"],
                }, ensure_ascii=False) + "\n")
        except Exception:
            pass
        return path
