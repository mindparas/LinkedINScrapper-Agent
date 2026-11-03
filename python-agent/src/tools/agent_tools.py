import os
import sys
import time
import json
import random
import urllib.parse
import py_compile
from selenium.webdriver.common.by import By

from src.config import Style, log_tool_result, log_qualified, log_skipped, BASE_DIR
from src.verification import (
    clean_linkedin_boolean_query,
    parse_post_age,
    is_verified_usa_location,
    verify_bde_lead_authenticity,
    verify_sales_buying_intent,
)
from src.browser import (
    search_web_api,
    scan_linkedin_content_cards,
    resolve_post_url
)
from src.agent.planner import StrategicQueryPlanner
from src.agent.evaluator import BDESalesIntelligenceSynthesizer
from src.judge import LeadJudge
from src.safety import UsageBudget, detect_checkpoint
from src.agent.mission import DEFAULT_MISSION
from src.metrics import RunMetrics

class LinkedInAgentTools:
    """
    Sensor and Actuator tool suite executed by the Autonomous AI Agent.
    Interacts directly with the active Selenium Chrome driver.
    """
    def __init__(self, driver, exporter, memory, logger, active_developer_directives=None, mission=None, metrics=None):
        self.driver = driver
        self.exporter = exporter
        self.memory = memory
        self.logger = logger
        self.evaluated_fingerprints = set()
        self.active_developer_directives = active_developer_directives if active_developer_directives is not None else []
        self.mission = mission or DEFAULT_MISSION
        self.metrics = metrics or RunMetrics(mission=self.mission)
        self.planner = StrategicQueryPlanner(memory=memory, mission=self.mission, logger=logger)
        self.engine = self.planner.engine
        self.freshness_counts = ""
        self.dry_cutoff_hit = False
        self.stagnation_reason = ""
        self.brain_event = ""
        self.query_samples = []
        print("🧭 Planning the search strategy (mission → queries)…")
        self.engine.prepare()
        print(f"   {len(self.engine.pool)} candidate queries across {len({p['angle'] for p in self.engine.pool})} angles; "
              f"first: '{self.engine.suggest()}'")
        self.evaluator = BDESalesIntelligenceSynthesizer()
        self.judge = LeadJudge(logger=logger, mission=self.mission)
        self.ns = f"{self.mission.key}::" if self.mission.key else ""   # per-mission memory namespace
        self.query_started = time.time()
        self.query_dom_cards = 0
        self.usage = UsageBudget()
        self.halt_reason = ""
        self.judged_count = 0
        self.posts_judged_on_query = 0
        self.buyers_on_query = 0
        self.us_buyers_on_query = 0
        self.categories_on_query = {}
        self.query_log = []  # compact per-query results for this session (feeds the state summary)
        
        # Pre-seed fingerprints strictly with THIS session's leads
        for l in self.exporter.leads:
            auth = (l.get("Author Name") or "").strip().lower()
            purl = (l.get("Profile URL") or "").strip().lower().split('?')[0].rstrip('/')
            if auth:
                self.evaluated_fingerprints.add(auth)
            if purl:
                self.evaluated_fingerprints.add(purl)
                
        self.current_query = ""
        self.current_freshness = "past-24h"
        self.current_target_objective = ""
        self.current_rationale = ""
        self.current_feasibility = ""
        self.current_developer_alignment = ""
        self.scroll_count_on_query = 0
        self.skipped_count = 0
        self.cards_on_current_query = 0
        self.qualified_on_current_query = 0
        self.consecutive_non_usa_count = 0
        self.consecutive_empty_scrolls = 0
        self.consecutive_zero_card_scans = 0
        self.last_dom_card_count = 0
        self.last_scanned_cards = []
        self.executed_queries = set()
        self.deadline = None  # epoch seconds; long loops stop early when exceeded
        self.auto_skipped_count = 0
        self.profile_visits = 0

    MAX_AUTO_SCROLLS = 3
    MAX_AUTO_VERIFY = 3

    @staticmethod
    def _norm_url(url):
        return (url or "").strip().lower().split('?')[0].rstrip('/')

    @staticmethod
    def _excerpt(text, limit=400):
        t = " ".join((text or "").split())
        return f"post='{t[:limit]}{'…' if len(t) > limit else ''}'"

    def _finalize_query(self):
        """Persist what the current query produced (memory + planner + compact session log), once."""
        if not self.current_query:
            return
        q = self.current_query
        level = self.planner.level_of(q)
        self.memory.record_query(
            query=q,
            freshness=self.current_freshness,
            rationale=self.current_rationale,
            expected_output=self.current_target_objective,
            cards_count=self.cards_on_current_query,
            qualified_count=self.qualified_on_current_query,
        )
        self.memory.record_query_stats(
            self.ns + q, level, self.posts_judged_on_query, self.buyers_on_query,
            self.us_buyers_on_query, self.qualified_on_current_query,
        )
        self.planner.record_query_execution(
            query=q, freshness=self.current_freshness,
            cards_found=self.cards_on_current_query, qualified_count=self.qualified_on_current_query,
        )
        self.planner.record_feed_feedback(
            query=q, total_cards=self.posts_judged_on_query, categories=self.categories_on_query
        )
        event = self.engine.observe(
            q, self.current_freshness, self.query_dom_cards, self.posts_judged_on_query, self.buyers_on_query,
            dict(self.categories_on_query), self.qualified_on_current_query, list(self.query_samples))
        if event:
            self.brain_event = event
            self.planner.last_learned_lesson = event
            self.metrics.inc("query_replans")
            print(f"\n{Style.CYAN}{Style.BOLD}🧠 SEARCH BRAIN CHANGED{Style.RESET} {event}")
        if self.engine.stagnant() and not self.stagnation_reason:
            self.stagnation_reason = (f"{self.engine.dry_streak} consecutive queries matched nothing even after "
                                      f"{self.engine.replans} strategy change(s)")
        self.query_log.append({
            "query": q, "level": level, "posts": self.posts_judged_on_query,
            "buyers": self.buyers_on_query, "us_buyers": self.us_buyers_on_query,
            "leads": self.qualified_on_current_query, "categories": dict(self.categories_on_query),
        })
        self.metrics.query_done({
            "query": q, "freshness": self.current_freshness, "dom_cards": self.query_dom_cards,
            "posts_judged": self.posts_judged_on_query, "matches": self.buyers_on_query,
            "location_confirmed": self.us_buyers_on_query, "leads": self.qualified_on_current_query,
            "duration_sec": round(time.time() - self.query_started, 1),
        })
        self.current_query = ""

    def state_summary(self, leads_target, leads_now):
        """Compact working memory handed to the model every turn instead of the full history."""
        lines = [
            f"LEADS: {leads_now}/{leads_target}. Searches left today: {self.usage.remaining('searches')}.",
        ]
        if not self.mission.is_default:
            lines.append(f"MISSION: {self.mission.summary}")
        if self.query_log:
            lines.append("QUERIES TRIED THIS RUN (level, posts judged, buyers, US buyers, leads, top categories):")
            for e in self.query_log[-8:]:
                cats = ", ".join(f"{k}:{v}" for k, v in sorted(e["categories"].items(), key=lambda kv: -kv[1])[:3])
                lines.append(f"- L{e['level']} '{e['query']}': {e['posts']} posts, {e['buyers']} buyers, {e['us_buyers']} US, {e['leads']} leads [{cats}]")
        if self.current_query:
            lines.append(f"CURRENT QUERY: '{self.current_query}' (L{self.planner.level_of(self.current_query)}), "
                         f"{self.posts_judged_on_query} posts judged so far, {self.buyers_on_query} buyers.")
        lines.append(f"🧠 STRATEGIC COGNITION & LEARNED FEEDBACK:\n  {self.planner.last_learned_lesson}")
        nxt = self.get_next_recommended_query()
        lines.append(f"SEARCH BRAIN #{self.engine.generation} (angle of next query: {self.engine.angle_of(nxt)}; "
                     f"{self.engine.dry_streak} queries in a row without a match; "
                     f"a new strategy is written after {self.engine.DRY_REPLAN_AFTER}). Use the suggested query unless you have clearly better evidence; short natural phrases the target author would write.")
        lines.append(f"SUGGESTED NEXT QUERY (from planner): '{self.get_next_recommended_query()}'")
        return "\n".join(lines)

    def _log_card(self, card, verdict):
        """Append every post the agent sees to dataset/cards.jsonl (raw material for labeling/eval)."""
        try:
            path = os.path.join(BASE_DIR, "dataset", "cards.jsonl")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "seen_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "query": self.current_query,
                    "author": card.get("author", ""),
                    "headline": card.get("headline", ""),
                    "author_url": card.get("author_url", ""),
                    "content": card.get("content", ""),
                    "judge": verdict,
                }, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _safety_halt(self):
        """True (and sets halt_reason) when LinkedIn is challenging the session."""
        reason = detect_checkpoint(self.driver)
        if reason:
            self.halt_reason = reason
            self.logger.error(f"SAFETY HALT: {reason}")
            return True
        return False

    def _time_up(self):
        return self.deadline is not None and time.time() >= self.deadline

    def _register_skip(self, author, profile_url):
        keys = [(author or "").strip().lower(), self._norm_url(profile_url)]
        for k in keys:
            if k:
                self.evaluated_fingerprints.add(k)
        self.memory.record_skips([self.ns + k for k in keys if k])

    def get_next_recommended_query(self):
        return self.planner.get_next_recommended_query(self.executed_queries)

    @property
    def current_expected_output(self):
        return self.current_target_objective

    @current_expected_output.setter
    def current_expected_output(self, val):
        self.current_target_objective = val

    def execute_search(
        self,
        query: str,
        freshness: str = "past-24h",
        target_objective: str = "",
        query_rationale: str = "",
        feasibility_analysis: str = "",
        developer_feedback_alignment: str = "",
        rationale: str = "",
        expected_output: str = ""
    ):
        query_rationale = query_rationale or rationale
        target_objective = target_objective or expected_output

        if self.halt_reason:
            return {"status": "halted", "observation": f"HALTED: {self.halt_reason}. Call finish_campaign."}
        if not self.usage.allow("searches"):
            self.halt_reason = "Daily search limit reached (account-safety budget)"
            return {"status": "halted", "observation": f"HALTED: {self.halt_reason}. Call finish_campaign."}
        raw_q = (query or "").strip()
        if raw_q.startswith('"') and raw_q.endswith('"') and raw_q.count('"') == 2 and 3 <= len(raw_q.split()) <= 6:
            clean_q = '"' + clean_linkedin_boolean_query(raw_q[1:-1]) + '"'   # exact phrase: keep the quotes
        else:
            clean_q = clean_linkedin_boolean_query(query)
        # Ensure query is non-empty and has substance
        if not clean_q or len(clean_q.strip()) < 2:
            clean_q = self.get_next_recommended_query()

        # Prevent duplicate re-execution in the same session by autonomously selecting a fresh unexecuted angle
        if clean_q.lower() in self.executed_queries:
            fresh_q = self.get_next_recommended_query()
            print(f"\n{Style.YELLOW}⚠️ Notice: Query '{clean_q}' was already tested in this session. Autonomously executing fresh angle: '{fresh_q}'{Style.RESET}")
            clean_q = fresh_q

        self._finalize_query()
        if self.stagnation_reason:
            return {"status": "halted", "observation": f"STOPPING: {self.stagnation_reason}. Call finish_campaign."}

        # The learner overrides the agent's pick right after a strategy change, or when the query's words
        # have a proven record of pulling the wrong authors.
        replaced = ""
        if self.brain_event or self.engine.predicted_poor(clean_q):
            better = self.get_next_recommended_query()
            if better and better.lower() != clean_q.lower():
                replaced = (f"Planner replaced '{clean_q}' with '{better}' "
                            + ("(search strategy was just revised)." if self.brain_event else "(its words have a poor track record)."))
                print(f"\n{Style.YELLOW}🔁 {replaced}{Style.RESET}")
                clean_q = better
        self.brain_event = ""
        self.query_samples = []
        self.dry_cutoff_hit = False

        self.scroll_count_on_query = 0
        self.cards_on_current_query = 0
        self.qualified_on_current_query = 0
        self.consecutive_non_usa_count = 0
        self.consecutive_empty_scrolls = 0
        self.consecutive_zero_card_scans = 0
        self.last_dom_card_count = 0
        self.posts_judged_on_query = 0
        self.buyers_on_query = 0
        self.us_buyers_on_query = 0
        self.categories_on_query = {}
        self.current_query = clean_q
        self.query_started = time.time()
        self.query_dom_cards = 0
        self.executed_queries.add(clean_q.lower())
        self.current_freshness = freshness if freshness in ["past-24h", "past-week"] else "past-24h"
        self.current_target_objective = target_objective
        self.current_rationale = query_rationale
        self.current_feasibility = feasibility_analysis
        self.current_developer_alignment = developer_feedback_alignment

        # Prominently display the Agent Cognitive Reasoning Card
        print("\n" + "=" * 80)
        print(f"{Style.CYAN}{Style.BOLD}🧠 [AGENT REASONING & SEARCH STRATEGY]{Style.RESET}")
        print(f"🎯 {Style.BOLD}Target Objective:{Style.RESET}\n   {target_objective or 'Targeting authentic founders building MVPs/software'}")
        print(f"🔍 {Style.BOLD}LinkedIn Search Query:{Style.RESET} {Style.YELLOW}'{clean_q}'{Style.RESET} ({self.current_freshness})")
        print(f"💡 {Style.BOLD}Strategic Rationale:{Style.RESET}\n   {query_rationale or 'Unquoted natural intent query for high recall'}")
        print(f"🚀 {Style.BOLD}Feasibility Assessment:{Style.RESET}\n   {feasibility_analysis or 'Matches active founder vernacular while filtering out recruiters'}")
        if developer_feedback_alignment:
            print(f"💬 {Style.BOLD}Developer Feedback Integrated:{Style.RESET}\n   {Style.GREEN}{developer_feedback_alignment}{Style.RESET}")
        print("=" * 80)

        # Developer Steering Point if interactive mode is explicitly enabled
        dev_hint = ""
        if os.environ.get("NON_INTERACTIVE", "0") != "1":
            print(f"\n{Style.CYAN}{Style.BOLD}💬 [DEVELOPER STEERING (Press ENTER to continue autonomously)]:{Style.RESET}")
            try:
                dev_hint = input(f"   {Style.BOLD}Developer Guidance > {Style.RESET}").strip()
            except (EOFError, KeyboardInterrupt):
                dev_hint = ""

        if dev_hint:
            self.logger.info(f"Developer steered agent during search formulation: '{dev_hint}'")
            self.memory.record_user_feedback(lead_author="Search Formulation", feedback=dev_hint)
            self.active_developer_directives.append(dev_hint)
            print(f"   {Style.GREEN}✓ Developer guidance recorded: '{dev_hint}'{Style.RESET}\n")
            return {
                "status": "developer_guidance_provided",
                "developer_guidance": dev_hint,
                "observation": (
                    f"DEVELOPER OVERRIDE: The developer reviewed your proposed query and gave direct guidance: '{dev_hint}'. "
                    f"Do NOT execute '{clean_q}'. You MUST immediately formulate a new search query strictly incorporating this feedback. "
                    f"Articulate your updated reasoning."
                )
            }

        self.logger.info(f"Agent executing search: '{clean_q}' | Objective: {target_objective} | Rationale: {query_rationale}")
        self.usage.record("searches")
        self.metrics.inc("searches")
        time.sleep(random.uniform(2.5, 4.5))  # human-like pacing between searches

        # Dual-timeframe strategy. The past-week page is a superset of past-24h (both newest-first), so:
        #  - normally load past-24h, and if it is thin (< WEEK_WHEN_BELOW posts) also load past-week and keep
        #    the larger result;
        #  - when the learner has seen that past-24h is almost always thin for this mission, go straight to
        #    past-week (one page load instead of two).
        cards_24h, cards_week = None, None
        freshness_used = "past-24h"
        if self.engine.freshness_first() == "past-week":
            has_no_results, visible_cards = self._load_search(clean_q, "past-week")
            cards_week, freshness_used = visible_cards, "past-week"
        else:
            has_no_results, visible_cards = self._load_search(clean_q, "past-24h")
            cards_24h = visible_cards
        if self._safety_halt():
            return {"status": "halted", "observation": f"HALTED: {self.halt_reason}. Call finish_campaign."}

        if cards_week is None and (has_no_results or visible_cards < self.WEEK_WHEN_BELOW):
            self.logger.info(f"Only {visible_cards} cards in past-24h for '{clean_q}'. Also checking past-week.")
            has_no_results_wk, cards_week = self._load_search(clean_q, "past-week")
            self.metrics.inc("weekly_fallbacks")
            if cards_week > visible_cards:
                has_no_results, visible_cards, freshness_used = has_no_results_wk, cards_week, "past-week"
            elif visible_cards == 0:
                has_no_results, freshness_used = True, "both 24h & past-week evaluated"
        self.engine.learner.observe_freshness(cards_24h if cards_24h is not None else 0, cards_week)
        self.freshness_counts = f"24h={cards_24h if cards_24h is not None else 'skipped'}, week={cards_week if cards_week is not None else 'not needed'}"

        self.current_freshness = freshness_used
        self.cards_on_current_query = visible_cards
        self.last_dom_card_count = visible_cards

        if has_no_results or visible_cards == 0:
            self.metrics.inc("zero_result_searches")
            self.planner.record_zero_yield(clean_q)
            self.planner.record_feed_feedback(clean_q, 0, {})
            next_pattern = self.planner.current_archetype
            next_rec = self.get_next_recommended_query()
            obs = (
                f"0 results found on LinkedIn across BOTH 'past-24h' and 'past-week' for '{clean_q}' ({self.freshness_counts}). "
                f"Page displays 'No results found'. DO NOT SCROLL on this page. "
                f"Pattern automatically shifted to '{next_pattern}'. Recommended next move: execute query '{next_rec}'."
            )
            status = "zero_results"
        else:
            self.planner.record_positive_yield(clean_q)
            obs = (f"Search successfully returned results for '{clean_q}' (cards: {self.freshness_counts}; showing {freshness_used}). "
                   f"Found {visible_cards} post cards visible. " + (replaced + " " if replaced else "") + "Call scan_and_read_cards to inspect them.")
            status = "success"

        return {
            "status": status,
            "has_no_results": has_no_results,
            "query": clean_q,
            "freshness": self.current_freshness,
            "cards_visible_count": visible_cards,
            "observation": obs
        }

    WEEK_WHEN_BELOW = 10
    DRY_CUTOFF = 8          # judged posts with zero matches after which a query is abandoned

    def _load_search(self, clean_q, freshness):
        encoded = urllib.parse.quote(clean_q)
        date_param = "%22past-24h%22" if freshness == "past-24h" else "%22past-week%22"
        # Default is LinkedIn's relevance ranking; SEARCH_SORT=date forces newest-first.
        sort_param = "&sortBy=%5B%22date_posted%22%5D" if os.environ.get("SEARCH_SORT", "relevance").lower() == "date" else ""
        url = f"https://www.linkedin.com/search/results/content/?datePosted={date_param}&keywords={encoded}&origin=GLOBAL_SEARCH_HEADER{sort_param}"
        self.driver.get(url)
        time.sleep(random.uniform(3.5, 4.5))

        body_text = self.driver.find_element(By.TAG_NAME, "body").text
        has_no_results = (
            "No results found" in body_text or
            "Try removing filters or rephrasing your search" in body_text
        )
        comment_btns = self.driver.find_elements(By.CSS_SELECTOR, "button[aria-label*='Comment' i], button[aria-label*='comment']")
        return has_no_results, len(comment_btns)

    def _collect_new_cards(self):
        """One DOM pass: dedupe against evaluated/skipped/qualified, annotate, and auto-skip clear rejects."""
        cards = scan_linkedin_content_cards(self.driver, self.logger)
        self.metrics.inc("dom_cards_seen", len(cards))
        self.query_dom_cards = max(self.query_dom_cards, len(cards))
        qualified_urls = {self._norm_url(ex.get("Profile URL")) for ex in self.exporter.leads}
        fresh, auto_skipped = [], 0

        for c in cards:
            if self.posts_judged_on_query >= self.DRY_CUTOFF and self.buyers_on_query == 0:
                self.dry_cutoff_hit = True      # stop paying to judge a query that is clearly off-target
                break
            auth_low = c.get("author", "").strip().lower()
            url_clean = self._norm_url(c.get("author_url", ""))
            content = c.get("content", "")

            if url_clean in qualified_urls:
                self.metrics.inc("known_duplicates")
                continue
            if any(k and (k in self.evaluated_fingerprints or self.memory.is_skipped(self.ns + k)) for k in (auth_low, url_clean)):
                self.metrics.inc("known_duplicates")
                continue
            if len(content) <= 15:
                self.metrics.inc("too_short")
                continue

            c["parsed_age_days"] = round(parse_post_age(c.get("raw_timestamp", "")), 2)
            is_auth, auth_hint = verify_bde_lead_authenticity(c.get("author", ""), c.get("headline", ""), "", c.get("company", ""), content)
            has_intent, intent_hint = verify_sales_buying_intent(content, c.get("headline", ""))

            # Cheap pre-filter: obvious recruiters/brokers never cost a judge call
            # (only for the default mission: a custom mission may legitimately target recruiters etc.)
            is_broker = self.mission.is_default and (not is_auth) and "disqualified persona pattern" in auth_hint
            if is_broker:
                self.metrics.inc("prefiltered")
            verdict = None
            if not is_broker:
                verdict = self.judge.judge(c.get("author", ""), c.get("headline", ""), content)
                self.judged_count += 1
                self.posts_judged_on_query += 1
                self.categories_on_query[verdict["category"]] = self.categories_on_query.get(verdict["category"], 0) + 1
                if verdict["category"] != "ERROR":
                    self.metrics.judged(verdict["category"])
                if verdict["is_buyer"]:
                    self.buyers_on_query += 1
                    self.metrics.inc("judge_buyers")
                c["judge"] = verdict
                self._log_card(c, verdict)
                if not verdict["is_buyer"] and verdict["category"] != "ERROR" and len(self.query_samples) < 6:
                    self.query_samples.append({
                        "cat": verdict["category"], "who": (c.get("headline", "") or c.get("author", ""))[:50],
                        "text": " ".join(content.split())[:140], "why": verdict["reasoning"][:110]})
            judge_ok = verdict is not None and verdict["category"] != "ERROR"

            if judge_ok:
                # The judge is the primary gate; rules are only a fallback when it is unavailable
                reject = not verdict["is_buyer"] and verdict["confidence"] >= 0.6
                reason = f"Judge: {verdict['category']} ({verdict['confidence']:.2f}) {verdict['reasoning']}"
            elif not self.mission.is_default:
                # The regex fallback encodes the default (dev-shop) mission only: with a custom mission,
                # leave the post unmarked so a later run can judge it once the LLM is reachable again.
                self.logger.warning(f"Judge unavailable for '{c.get('author', '')}' - post left for a later run (custom mission).")
                continue
            else:
                reject = is_broker or (not is_auth and not has_intent)
                reason = auth_hint if is_broker else f"{auth_hint}; {intent_hint}"
            if reject:
                self.metrics.inc("auto_rejected")
                self._register_skip(c.get("author", ""), c.get("author_url", ""))
                self.skipped_count += 1
                auto_skipped += 1
                log_skipped(f"Auto-skip ({c.get('author', 'Unknown')}) — {reason}")
                self.logger.info(f"SKIPPED POST TEXT [auto] {c.get('author', 'Unknown')} | headline='{c.get('headline', '')[:100]}' | {self._excerpt(content)}")
                continue

            if judge_ok:
                c["bde_authenticity_check"] = f"JUDGE: decision_maker={verdict['author_is_decision_maker']}"
                c["sales_intent_check"] = f"JUDGE: {verdict['category']} conf={verdict['confidence']:.2f} — {verdict['evidence_quote']}"
                c["buying_intent_signal"] = verdict["need_summary"] or verdict["evidence_quote"] or "Judge-approved buying signal"
                c["_passes_gates"] = LeadJudge.is_qualified(  # profile visit decides location
                    verdict, us_verified=True, require_dm=self.mission.require_decision_maker)
                if c["_passes_gates"]:
                    self.metrics.inc("passed_gates")
            else:
                c["bde_authenticity_check"] = "PASS: Direct Founder/Exec" if is_auth else f"FLAGGED: {auth_hint}"
                c["sales_intent_check"] = f"HIGH INTENT: {intent_hint}" if has_intent else f"LOW/NO INTENT: {intent_hint}"
                c["buying_intent_signal"] = intent_hint if has_intent else "No commercial technical buying intent"
                c["_passes_gates"] = bool(is_auth and has_intent)
            fresh.append(c)

        self.auto_skipped_count += auto_skipped
        return fresh, auto_skipped

    def scan_and_read_cards(self):
        unevaluated_cards, auto_skipped = self._collect_new_cards()

        # Scroll for more cards before declaring the feed dry
        scrolls = 0
        while not unevaluated_cards and scrolls < self.MAX_AUTO_SCROLLS and not self._time_up() and not self.dry_cutoff_hit:
            scroll_res = self.scroll_feed(steps=1, rationale="auto-scroll: no new candidates in view")
            scrolls += 1
            more, skipped_more = self._collect_new_cards()
            auto_skipped += skipped_more
            unevaluated_cards.extend(more)
            if scroll_res.get("at_end_of_feed") or self.consecutive_non_usa_count >= 2:
                break

        # Auto-verify location (profile visit) for cards that pass both gates
        verified_notes = []
        kept = []
        visits = 0
        for c in unevaluated_cards:
            passes = c.pop("_passes_gates", False)
            if passes and not self.mission.needs_us:
                # Mission has no location filter: no profile visit needed (saves account budget)
                c["verified_location"] = "Not required for this mission"
                c["is_usa_verified"] = True
                self.us_buyers_on_query += 1
                self.metrics.inc("location_confirmed")
                kept.append(c)
                continue
            if passes and visits < self.MAX_AUTO_VERIFY and not self._time_up():
                visits += 1
                res = self.verify_profile_location(author_url=c.get("author_url", ""))
                c["verified_location"] = res.get("exact_location", "Unknown")
                c["is_usa_verified"] = bool(res.get("is_usa_verified"))
                if c["is_usa_verified"] and (c.get("judge") or {}).get("is_buyer"):
                    self.us_buyers_on_query += 1
                    self.metrics.inc("location_confirmed")
                if not c["is_usa_verified"] and res.get("exact_location") not in ("Error inspecting profile", "Unknown"):
                    self.metrics.inc("non_us_rejected")
                    self._register_skip(c.get("author", ""), c.get("author_url", ""))
                    self.skipped_count += 1
                    auto_skipped += 1
                    verified_notes.append(f"{c.get('author')} auto-rejected: non-US ({c['verified_location']})")
                    continue
                verified_notes.append(f"{c.get('author')}: {c['verified_location']} (US={c['is_usa_verified']})")
            kept.append(c)

        for idx, c in enumerate(kept):
            c["card_index"] = idx
        self.last_scanned_cards = kept
        unevaluated_cards = kept

        if len(unevaluated_cards) == 0:
            self.consecutive_zero_card_scans += 1
            diag = self.planner.diagnose_feed_outcome(
                self.last_dom_card_count, self.consecutive_empty_scrolls, self.consecutive_non_usa_count
            )
            next_q = self.get_next_recommended_query()
            obs = (
                f"No new candidate cards after auto-scrolling {scrolls}x ({auto_skipped} auto-rejected as recruiters/no-intent/non-US). "
                f"🛑 FEED EXHAUSTED for query '{self.current_query}'"
                + (f" ({diag['diagnosis']})" if diag["action"] != "continue_feed" else "") + ". "
                f"Recommended next query: '{next_q}'. Execute search with this query now."
            )
            return {"cards_found_count": 0, "cards": [], "auto_skipped": auto_skipped, "observation": obs}

        self.consecutive_zero_card_scans = 0
        dry_hint = ""
        if self.dry_cutoff_hit or (self.posts_judged_on_query >= 8 and self.buyers_on_query == 0):
            dry_hint = (f" ⚠️ This query is DRY: {self.posts_judged_on_query} posts judged, none match the mission. "
                        f"Stop scrolling it and run the next suggested query ('{self.get_next_recommended_query()}').")
        return {
            "cards_found_count": len(unevaluated_cards),
            "cards": unevaluated_cards,
            "auto_skipped": auto_skipped,
            "observation": (
                f"{len(unevaluated_cards)} candidate cards ({auto_skipped} more auto-rejected by code as recruiters/no-intent/non-US; do NOT re-evaluate those). "
                + (f"Profile checks done: {'; '.join(verified_notes)}. " if verified_notes else "")
                + "Cards with verified_location and is_usa_verified=true that show HIGH INTENT can go straight to qualify_and_save_lead; "
                  "call verify_profile_location only for unverified cards you consider promising." + dry_hint
            )
        }

    def verify_profile_location(self, card_index: int = 0, author_url: str = ""):
        # Match author_url from cached card if card_index provided
        if card_index < len(self.last_scanned_cards) and not author_url:
            author_url = self.last_scanned_cards[card_index].get("author_url", "")

        if not author_url or "linkedin.com/in/" not in author_url:
            return {
                "author_url": author_url,
                "exact_location": "Unknown",
                "is_usa_verified": False,
                "observation": f"Invalid or missing profile URL: {author_url}"
            }

        if self.halt_reason:
            return {"author_url": author_url, "exact_location": "Unknown", "is_usa_verified": False,
                    "observation": f"HALTED: {self.halt_reason}"}
        if not self.usage.allow("profile_visits"):
            self.halt_reason = "Daily profile-visit limit reached (account-safety budget)"
            return {"author_url": author_url, "exact_location": "Unknown", "is_usa_verified": False,
                    "observation": f"HALTED: {self.halt_reason}"}
        self.usage.record("profile_visits")
        self.logger.info(f"Opening author profile in background tab to verify exact location: {author_url}")
        original_tab = self.driver.current_window_handle
        self.profile_visits += 1
        self.metrics.inc("profile_visits")

        try:
            # Open profile in new background tab
            self.driver.switch_to.new_window("tab")
            self.driver.get(author_url)

            # Wait dynamically up to 7 seconds for React hydration
            for _ in range(14):
                ready = self.driver.execute_script("""
                    return !!(document.body && (document.body.innerText || '').length > 500);
                """)
                if ready:
                    time.sleep(1.0)
                    break
                time.sleep(0.5)

            extract_loc_script = """
            let location = "";
            let method = "";
            let name = "";
            let headline = "";

            // 1. Author Name (from h2 or h1)
            const h2s = Array.from(document.querySelectorAll('h2, h1')).map(h => (h.innerText || '').trim()).filter(t => t.length > 0 && !/notification|about|experience|activity|featured|ad options/i.test(t));
            if (h2s.length > 0) {
                name = h2s[0];
            }

            // 2. Primary Method: Relative proximity to 'Contact info' anchor or button
            const allEl = Array.from(document.querySelectorAll('a, button, span, div'));
            const contactEl = allEl.find(el => (el.innerText || '').trim().toLowerCase() === 'contact info');

            if (contactEl) {
                let parent = contactEl.parentElement;
                for (let d = 0; d < 6; d++) {
                    if (!parent || parent === document.body) break;
                    const lines = (parent.innerText || '').split('\\n').map(l => l.trim()).filter(l => l.length > 0 && l !== '·' && l.toLowerCase() !== 'contact info');
                    const cIdx = lines.findIndex(l => /contact info/i.test(l));
                    if (cIdx > 0 && lines[cIdx - 1].length >= 3 && lines[cIdx - 1].length <= 100) {
                        location = lines[cIdx - 1];
                        method = "contact_parent_lines";
                        break;
                    } else if (lines.length > 0 && lines[lines.length - 1].length >= 3 && lines[lines.length - 1].length <= 100) {
                        location = lines[lines.length - 1];
                        method = "contact_sibling_line";
                        break;
                    }
                    parent = parent.parentElement;
                }
            }

            // 3. Fallback 1: Parse document.body.innerText lines around 'contact info'
            if (!location) {
                const bodyLines = (document.body.innerText || '').split('\\n').map(l => l.trim()).filter(l => l.length > 0);
                const cIdx = bodyLines.findIndex(l => l.toLowerCase() === 'contact info');
                if (cIdx > 0) {
                    for (let offset = 1; offset <= 4; offset++) {
                        const cand = bodyLines[cIdx - offset];
                        if (cand && cand !== '·' && !/followers|connections|message|follow|he\\/him|she\\/her|mutual|more/i.test(cand) && cand.length >= 3 && cand.length <= 100) {
                            location = cand;
                            method = "body_contact_offset";
                            break;
                        }
                    }
                }
            }

            // 4. Fallback 2: CSS query for top-card location classes
            if (!location) {
                const locCandidates = Array.from(document.querySelectorAll('span.text-body-small.inline.t-black--light.break-words, .pv-text-details__left-panel span.text-body-small, span[class*="location" i]'));
                for (const c of locCandidates) {
                    const raw = (c.innerText || '').trim().split('\\n')[0].replace(/•.*/, '').replace(/Contact info/i, '').trim();
                    if (raw.length >= 3 && raw.length <= 100) {
                        location = raw;
                        method = "css_selector";
                        break;
                    }
                }
            }

            // Clean location string
            if (location) {
                location = location.split('\\n')[0].replace(/·.*/, '').replace(/•.*/, '').replace(/Contact info/i, '').trim();
            }

            return {
                name: name,
                headline: headline,
                location: location,
                method: method
            };
            """
            if self._safety_halt():
                self.driver.close()
                self.driver.switch_to.window(original_tab)
                return {"author_url": author_url, "exact_location": "Unknown", "is_usa_verified": False,
                        "observation": f"HALTED: {self.halt_reason}"}
            profile_info = self.driver.execute_script(extract_loc_script) or {}
            exact_location = profile_info.get("location", "").strip()

            # Close profile tab and return to search
            self.driver.close()
            self.driver.switch_to.window(original_tab)

            # Analyze with our strict US parser
            is_usa, reason = is_verified_usa_location(exact_location)
            if is_usa:
                self.consecutive_non_usa_count = 0
                obs = f"Visited profile {author_url}. Exact top-card location: '{exact_location}'. Confirmed USA: {is_usa} ({reason})."
            else:
                self.consecutive_non_usa_count += 1
                obs = f"Visited profile {author_url}. Exact top-card location: '{exact_location}'. Confirmed USA: {is_usa} ({reason})."
                if self.consecutive_non_usa_count >= 2:
                    obs += f"\n🚨 EARLY BAILOUT ALERT: {self.consecutive_non_usa_count} consecutive cards in this search are from non-US/international locations! This feed is globally contaminated. STOP scrolling this feed immediately and execute a new search query targeting a specific US Metro (e.g. 'San Francisco', 'Austin', 'NYC') or US accelerator ('YC')."

            self.logger.info(f"Profile verification for {author_url}: Location='{exact_location}', Confirmed USA={is_usa} ({reason})")
            print(f"      📍 Profile Top-Card Extracted: '{exact_location}' -> Confirmed USA: {is_usa} ({reason})")

            return {
                "author_url": author_url,
                "exact_location": exact_location or "Location not specified on profile top-card",
                "is_usa_verified": is_usa,
                "verification_reason": reason,
                "observation": obs
            }

        except Exception as e:
            self.logger.error(f"Error checking profile location for {author_url}: {e}")
            try:
                self.driver.close()
                self.driver.switch_to.window(original_tab)
            except Exception:
                pass
            return {
                "author_url": author_url,
                "exact_location": "Error inspecting profile",
                "is_usa_verified": False,
                "observation": f"Could not verify profile location due to: {e}"
            }

    def qualify_and_save_lead(
        self,
        card_index: int,
        author: str,
        profile_url: str,
        headline: str,
        role: str,
        company: str,
        location: str,
        fit_score: int,
        custom_pitch: str,
        reasoning: str,
        buying_intent_signal: str = ""
    ):
        card = {}
        if card_index < len(self.last_scanned_cards):
            card = self.last_scanned_cards[card_index]

        # Match by author or profile_url if card_index points to a different candidate
        if card.get("author") != author:
            for c in self.last_scanned_cards:
                if c.get("author") == author or (profile_url and c.get("author_url") == profile_url):
                    card = c
                    break

        card_content = card.get("content", "")
        card_id = card.get("card_id", "")
        clean_profile_url = (card.get("author_url") or profile_url or "").strip()

        judge = card.get("judge")
        if judge and judge.get("category") != "ERROR":
            # Judge-gated: only an evidence-backed, confident BUYER who is a decision maker is saved
            if not LeadJudge.is_qualified(
                    judge, us_verified=bool(card.get("is_usa_verified")) or not self.mission.needs_us,
                    require_dm=self.mission.require_decision_maker):
                self.metrics.inc("lead_rejections")
                why = (f"Judge verdict {judge['category']} (confidence {judge['confidence']:.2f}, "
                       f"decision_maker={judge['author_is_decision_maker']}, US={judge['us_signal']}): {judge['reasoning']}")
                self.logger.warning(f"Rejected lead qualification for {author}: {why}")
                print(f"      ⚠️ Disqualified Lead Candidate: '{author}' — {why}")
                return {"status": "lead_disqualified", "author": author, "rejection_reason": why,
                        "observation": f"Disqualified '{author}'. {why}"}
            intent_signal = judge["need_summary"] or judge["evidence_quote"]
        elif not self.mission.is_default:
            # The regex guardrails below encode the default dev-shop mission only
            self.metrics.inc("lead_rejections")
            return {"status": "lead_disqualified", "author": author,
                    "rejection_reason": "no judge verdict available for this card",
                    "observation": f"Cannot save '{author}': the lead judge produced no verdict for this card."}
        else:
            # Strict Authenticity Guardrail
            is_authentic, auth_reason = verify_bde_lead_authenticity(
                author=author,
                headline=headline,
                role=role,
                company=company,
                post_content=card_content
            )
            if not is_authentic:
                self.logger.warning(f"Rejected lead qualification for {author}: {auth_reason}")
                print(f"      ⚠️ Disqualified Lead Candidate: '{author}' — Reason: {auth_reason}")
                return {
                    "status": "lead_disqualified",
                    "author": author,
                    "rejection_reason": auth_reason,
                    "observation": f"Disqualified lead candidate '{author}'. Reason: {auth_reason}. Lead MUST be an authentic direct Founder/CTO/CEO/VP of their own tech startup, NOT a recruiter or broker."
                }

            # Strict B2B Sales Intent Filter
            has_intent, auto_intent_signal = verify_sales_buying_intent(card_content or reasoning, headline)
            if not has_intent:
                self.logger.warning(f"Rejected lead qualification for {author}: {auto_intent_signal}")
                print(f"      ⚠️ Disqualified Lead Candidate: '{author}' — No Commercial Buying Intent: {auto_intent_signal}")
                return {
                    "status": "lead_disqualified",
                    "author": author,
                    "rejection_reason": auto_intent_signal,
                    "observation": f"Disqualified lead candidate '{author}'. Reason: {auto_intent_signal}. For sales, the candidate post MUST express an active development need, MVP build, technical problem, or hiring for builders/engineers."
                }
            intent_signal = auto_intent_signal

        # Resolve authentic post URL using our 3-tier resolver
        post_url = resolve_post_url(
            driver=self.driver,
            card_id=card_id,
            author_url=clean_profile_url,
            post_content_snippet=card_content,
            direct_post_url=card.get("direct_post_url", ""),
            logger=self.logger
        )

        # Synthesize tailored BDE outreach kit
        pitch_kit = self.evaluator.synthesize_pitch_kit(
            author=author,
            headline=headline,
            company=company,
            location=location,
            post_content=card_content,
            mission=self.mission,
            need_type=(judge or {}).get("need_type", ""),
            need_summary=(judge or {}).get("need_summary", "")
        )

        lead_record = {
            "Mission": self.mission.title,
            "Author Name": author,
            "First Name": pitch_kit["first_name"],
            "Title / Headline": headline,
            "Company Name": company,
            "Verified Location": location,
            "Profile URL": clean_profile_url,
            "Post URL": post_url,
            "Post Age": card.get("raw_timestamp", ""),
            "Fit Score": fit_score,
            "Commercial Intent Category": pitch_kit["intent_category"],
            "Identified Pain Point": pitch_kit["pain_point"],
            "Target Tech Stack": pitch_kit["tech_stack"],
            "LinkedIn Connection Note (<300 chars)": pitch_kit["connection_note"],
            "Full BDE InMail / Cold Pitch": pitch_kit["inmail_pitch"],
            "Buying Intent Signal": intent_signal,
            "Custom Outreach Hook": custom_pitch or pitch_kit["connection_note"],
            "Reasoning": reasoning,
            "Judge Category": (judge or {}).get("category", ""),
            "Judge Confidence": (judge or {}).get("confidence", ""),
            "Evidence Quote": (judge or {}).get("evidence_quote", ""),
            "Post Excerpt": " ".join(card_content.split())[:300]
        }

        was_new = self.exporter.append_lead(lead_record) is not False
        self.memory.record_qualified_lead(lead_record)
        self.qualified_on_current_query += 1
        total_leads = len(self.exporter.leads)
        if was_new:
            self.metrics.lead_saved(author, headline, self.current_query, judge, fit_score, location)

        # Mark fingerprint and profile as evaluated to prevent duplicates
        self.evaluated_fingerprints.add((author + "_" + reasoning[:30]).lower())
        if author:
            self.evaluated_fingerprints.add(author.strip().lower())
        if clean_profile_url:
            self.evaluated_fingerprints.add(clean_profile_url.strip().lower().split('?')[0].rstrip('/'))

        log_qualified(f"[{total_leads}] {author} | {role} @ {company} | Score: {fit_score}/100")
        print(f"      🔗 Profile URL: {clean_profile_url}")
        print(f"      📌 Authentic Post URL: {post_url}")
        print(f"      📍 Location: {location}")
        print(f"      💼 Tech Stack: {pitch_kit['tech_stack']}")
        print(f"      💡 Connection Note: {Style.BOLD}{pitch_kit['connection_note']}{Style.RESET}")

        return {
            "status": "lead_saved_successfully",
            "author": author,
            "profile_url": clean_profile_url,
            "post_url": post_url,
            "fit_score": fit_score,
            "buying_intent_signal": intent_signal,
            "total_qualified_leads_collected": total_leads,
            "observation": f"Successfully qualified and saved lead #{total_leads} ({author}). Specific post URL captured: {post_url}."
        }

    GENERIC_SKIP_REASONS = ("not an authentic tech decision maker", "disqualified")

    def skip_card(self, card_index: int, author: str, rejection_reason: str):
        self.skipped_count += 1
        self.metrics.inc("llm_skips")
        author_url = ""
        if 0 <= card_index < len(self.last_scanned_cards) and self.last_scanned_cards[card_index].get("author") == author:
            author_url = self.last_scanned_cards[card_index].get("author_url", "")
        else:
            for c in self.last_scanned_cards:
                if c.get("author") == author:
                    author_url = c.get("author_url", "")
                    break
        self._register_skip(author, author_url)
        for c in self.last_scanned_cards:
            if c.get("author") == author:
                self.logger.info(
                    f"SKIPPED POST TEXT [llm] {author} | headline='{c.get('headline', '')[:100]}' | intent_check={c.get('sales_intent_check', '')[:120]} | {self._excerpt(c.get('content', ''))}"
                )
                break
        log_skipped(f"Card #{card_index} ({author}) — Reason: {rejection_reason}")

        reason = rejection_reason.strip().rstrip(".")
        obs = f"Skipped card #{card_index} ({author}). Reason: {reason}."
        if len(reason) < 20 or reason.lower().startswith(self.GENERIC_SKIP_REASONS):
            obs += " Reason too generic: next time cite the concrete evidence (headline text, post excerpt, location)."
        return {
            "status": "card_skipped",
            "author": author,
            "reason": rejection_reason,
            "observation": obs
        }

    # LinkedIn's search page often scrolls an inner container, so window.scrollBy does nothing.
    # Click a "show more" button if one exists, else bring the last card into view and
    # push every scrollable ancestor (and the window) to the bottom to fire the lazy loader.
    LAZY_LOAD_SCRIPT = """
        const more = Array.from(document.querySelectorAll('button')).find(b =>
            /show more results|see more results|load more/i.test((b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '')));
        if (more) { more.click(); return 'clicked_more'; }
        const items = document.querySelectorAll('[data-bde-card-id], div[role="listitem"]');
        let last = items.length ? items[items.length - 1] : null;
        if (!last) {
            const btns = document.querySelectorAll("button[aria-label*='Comment' i]");
            last = btns.length ? btns[btns.length - 1] : null;
        }
        if (last) {
            last.scrollIntoView({block: 'end', behavior: 'instant'});
            let el = last.parentElement;
            while (el) {
                if (el.scrollHeight > el.clientHeight + 50 && /(auto|scroll)/.test(getComputedStyle(el).overflowY)) {
                    el.scrollTop = el.scrollHeight;
                }
                el = el.parentElement;
            }
        }
        window.scrollTo(0, document.body.scrollHeight);
        return 'scrolled';
    """

    def scroll_feed(self, steps: int = 1, rationale: str = ""):
        self.scroll_count_on_query += steps
        self.metrics.inc("scrolls", steps)
        self.logger.info(f"Agent scrolling down feed: {steps} steps | Rationale: {rationale}")

        for _ in range(steps):
            before = len(self.driver.find_elements(By.CSS_SELECTOR, "button[aria-label*='Comment' i]"))
            self.driver.execute_script(self.LAZY_LOAD_SCRIPT)
            # Poll up to ~6s for LinkedIn to append new cards after the trigger
            for _ in range(12):
                time.sleep(0.5)
                now = len(self.driver.find_elements(By.CSS_SELECTOR, "button[aria-label*='Comment' i]"))
                if now > before:
                    break
            time.sleep(random.uniform(0.8, 1.5))

        comment_btns = self.driver.find_elements(By.CSS_SELECTOR, "button[aria-label*='Comment' i], button[aria-label*='comment']")
        total_cards = len(comment_btns)
        new_cards_loaded = total_cards - self.last_dom_card_count
        self.cards_on_current_query = total_cards
        self.last_dom_card_count = total_cards

        if new_cards_loaded <= 0:
            self.consecutive_empty_scrolls += 1
        else:
            self.consecutive_empty_scrolls = 0

        body_text = self.driver.find_element(By.TAG_NAME, "body").text
        at_end = "No more results" in body_text or "You've viewed all" in body_text or self.consecutive_empty_scrolls >= 2

        if self.consecutive_non_usa_count >= 2:
            return {
                "total_cards_in_dom": total_cards,
                "scroll_count": self.scroll_count_on_query,
                "at_end_of_feed": at_end,
                "observation": f"🚨 FEED BAILOUT TRIGGERED: Feed has {self.consecutive_non_usa_count} consecutive international non-US cards! Scrolling further on this query is unproductive. Immediately execute a new search query anchored with a US Tech Hub (e.g. 'San Francisco', 'Austin', 'NYC') or US Accelerator ('YC')."
            }

        if at_end or self.consecutive_empty_scrolls >= 2:
            next_q = self.get_next_recommended_query()
            return {
                "total_cards_in_dom": total_cards,
                "scroll_count": self.scroll_count_on_query,
                "at_end_of_feed": True,
                "observation": (
                    f"🛑 FEED EXHAUSTED: Scrolling did not load any new cards (DOM stopped at {total_cards} cards). "
                    f"The LinkedIn feed for '{self.current_query}' is exhausted. Do NOT call scroll_feed again! "
                    f"Recommended next proven US query: '{next_q}'. Execute search with this query now."
                )
            }

        return {
            "total_cards_in_dom": total_cards,
            "scroll_count": self.scroll_count_on_query,
            "at_end_of_feed": at_end,
            "observation": f"Scrolled {steps} step(s). Total cards in DOM: {total_cards} (+{new_cards_loaded} new). Call scan_and_read_cards to inspect the newly loaded cards."
        }

    def search_web(self, query: str, rationale: str = ""):
        self.logger.info(f"Agent web search: '{query}' | Rationale: {rationale}")
        results = search_web_api(query)
        return {
            "query": query,
            "rationale": rationale,
            "results": results,
            "observation": f"Web search for '{query}' returned {len(results)} snippets."
        }

    def propose_code_improvement(self, file_path: str, target_code: str, replacement_code: str, explanation: str, expected_benefit: str):
        # Automated non-interactive safety fallback
        return {
            "status": "declined",
            "observation": "System is operating in autonomous production mode. Code updates must be deployed through repository pull requests."
        }

    def ask_developer(self, question: str, context: str = ""):
        return {
            "status": "autonomous_fallback",
            "developer_guidance": "Proceed autonomously using verified US founder criteria and high commercial intent.",
            "observation": "Proceed autonomously using verified US founder criteria and high commercial intent."
        }
