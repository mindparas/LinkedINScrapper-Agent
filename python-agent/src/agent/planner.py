"""
Strategic Query Discovery & Market Planner for Autonomous BDE Lead Generation.
Formulates high-yield unquoted US search angles, rotates hubs, and diagnoses feed fatigue.
"""

from typing import List, Dict, Any, Optional

class StrategicQueryPlanner:
    """
    Intelligent planner that synthesizes and rotates search queries targeting
    active US tech founders, startup executives, and MVP builders.
    """
    
    HIGH_YIELD_US_TECH_HUBS = [
        "San Francisco",
        "Bay Area",
        "Austin",
        "Seattle",
        "NYC",
        "New York",
        "Boston",
        "Denver",
        "Los Angeles",
        "Chicago"
    ]
    
    TOP_US_ACCELERATORS = [
        "YC",
        "Techstars",
        "South Park Commons",
        "Pear VC",
        "AI Grant"
    ]
    
    CORE_BUYING_ANGLES = [
        "founding engineer",
        "hiring first engineer",
        "building our MVP",
        "building MVP custom software",
        "looking for dev shop",
        "need software agency",
        "fractional CTO",
        "building in stealth",
        "hiring full stack engineer",
        "hiring AI engineer"
    ]

    BUYER_INTENT_TERMS = [
        "mvp", "dev shop", "software agency", "development partner", "fractional cto",
        "technical co-founder", "technical cofounder", "outsourc", "need an engineer",
        "need a developer", "need developers", "looking for developer", "build our app",
        "build my app", "hiring first engineer",
    ]

    # Ladder: L1 simple intent phrase -> L2 + US hub/accelerator -> L3 + industry/stack modifier
    INTENTS = [
        "need an MVP built", "looking for dev shop", "need software agency", "looking for developers",
        "need a technical co-founder", "outsourcing development", "fractional CTO needed",
    ]
    MODIFIERS = ["AI startup", "fintech", "healthtech", "SaaS", "mobile app", "marketplace"]
    RECENT_DAYS = 3          # a query run within this window is not repeated
    MAX_L1_PER_WINDOW = 3    # simple unanchored queries return worldwide authors, so use few
    L2_RUNS_BEFORE_L3 = 4    # escalate to L3 once L2 has had a fair try with no buyers

    def __init__(self, niche: str = "custom software & AI MVP engineering", memory=None):
        self.niche = niche
        self.memory = memory
        self.executed_queries: List[Dict[str, Any]] = []

    # ── helpers ─────────────────────────────────────────────────────────
    @property
    def _anchors(self) -> List[str]:
        return self.HIGH_YIELD_US_TECH_HUBS + self.TOP_US_ACCELERATORS

    def level_of(self, query: str) -> int:
        q = (query or "").lower()
        if not any(a.lower() in q for a in self._anchors):
            return 1
        return 3 if any(m.lower() in q for m in self.MODIFIERS) else 2

    def _stats(self) -> Dict[str, Any]:
        return self.memory.query_stats() if self.memory else {}

    def _recent(self, st) -> bool:
        from datetime import datetime, timedelta
        try:
            return datetime.fromisoformat(st["last_run"]) >= datetime.now() - timedelta(days=self.RECENT_DAYS)
        except (KeyError, TypeError, ValueError):
            return False

    def _component_scores(self) -> Dict[str, float]:
        """(buyers+1)/(posts+4) per component (intent/hub/modifier) across all past queries."""
        agg: Dict[str, List[int]] = {}
        comps = self.INTENTS + self._anchors + self.MODIFIERS
        for q, st in self._stats().items():
            for c in comps:
                if c.lower() in q:
                    a = agg.setdefault(c.lower(), [0, 0])
                    a[0] += st.get("buyers", 0)
                    a[1] += st.get("posts", 0)
        return {c: (b + 1) / (p + 4) for c, (b, p) in agg.items()}

    def _score(self, query: str, comp: Dict[str, float]) -> float:
        q = query.lower()
        prior = 0.25
        return sum(comp.get(c.lower(), prior) for c in self.INTENTS + self._anchors + self.MODIFIERS if c.lower() in q)

    def _candidates(self, level: int) -> List[str]:
        if level == 1:
            return list(self.INTENTS)
        if level == 2:
            return [f"{h} {i}" for h in self._anchors for i in self.INTENTS]
        return [f"{h} {m} {i}" for h in self._anchors for m in self.MODIFIERS for i in self.INTENTS]

    def is_acceptable_query(self, query: str) -> bool:
        """A query must carry a US anchor (hub/accelerator) or a buyer-intent phrase; bare job-title queries are recruiter bait."""
        q = (query or "").lower()
        return any(a.lower() in q for a in self._anchors) or any(t in q for t in self.BUYER_INTENT_TERMS)

    def choose_level(self) -> int:
        stats = self._stats()
        recent = {q: st for q, st in stats.items() if self._recent(st)}
        l1_recent = sum(1 for q in recent if self.level_of(q) == 1)
        if l1_recent < self.MAX_L1_PER_WINDOW:
            return 1
        l2 = [st for q, st in recent.items() if self.level_of(q) == 2]
        if len(l2) >= self.L2_RUNS_BEFORE_L3 and sum(st.get("buyers", 0) for st in l2) == 0:
            return 3
        return 2

    def get_next_recommended_query(self, already_executed: Optional[set] = None) -> str:
        done = set(already_executed or set()) | {q["query"] for q in self.executed_queries}
        stats = self._stats()
        skip = done | {q for q, st in stats.items() if self._recent(st)}
        comp = self._component_scores()
        start = self.choose_level()
        for level in (start, 2, 3, 1):
            fresh = [c for c in self._candidates(level) if c.lower() not in skip]
            if fresh:
                return max(fresh, key=lambda c: (self._score(c, comp), -len(c)))
        return self.INTENTS[0]

    def record_query_execution(self, query: str, freshness: str, cards_found: int, qualified_count: int):
        self.executed_queries.append({
            "query": query.lower().strip(),
            "freshness": freshness,
            "cards_found": cards_found,
            "qualified_count": qualified_count
        })

    def diagnose_feed_outcome(self, cards_count: int, consecutive_empty_scrolls: int, consecutive_non_usa: int) -> Dict[str, Any]:
        """
        Diagnoses feed health and provides actionable strategic next moves.
        """
        if cards_count == 0:
            return {
                "action": "switch_query_or_freshness",
                "diagnosis": "0 cards found on LinkedIn. The query syntax may be too restrictive or has no matches in this timeframe.",
                "recommendation": "Switch freshness from past-24h to past-week, or switch to a high-yield US Tech Hub (e.g. 'Austin looking for dev shop')."
            }
            
        if consecutive_non_usa >= 2:
            return {
                "action": "bailout_feed",
                "diagnosis": f"Feed contaminated with {consecutive_non_usa} consecutive international non-US profiles.",
                "recommendation": "Stop scrolling this feed immediately. Execute a search anchored strictly to a US city (e.g., 'Seattle need software agency')."
            }
            
        if consecutive_empty_scrolls >= 2:
            return {
                "action": "feed_exhausted",
                "diagnosis": "Feed reached end of results (scrolling loaded 0 new cards twice).",
                "recommendation": "Switch to next un-exhausted query angle."
            }
            
        return {
            "action": "continue_feed",
            "diagnosis": "Feed is healthy with active post cards.",
            "recommendation": "Scan cards, evaluate decision-makers, and qualify genuine leads."
        }

