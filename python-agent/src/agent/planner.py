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
    
    # High-intent US tech hubs and premier accelerators
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
        "Techstars"
    ]

    # Strategic Founder Archetypes: Real vernacular used by US startup founders
    ARCHETYPES = {
        "mvp_build": [
            "building our MVP",
            "building an MVP",
            "building our v1",
            "stealth startup building",
            "building in stealth",
            "building our mobile app"
        ],
        "founding_engineer": [
            "hiring founding engineer",
            "hiring our first engineer",
            "looking for technical cofounder",
            "seeking technical co-founder",
            "fractional CTO needed"
        ],
        "agency_search": [
            "looking for dev shop",
            "recommend a dev shop",
            "recommend software agency",
            "need software agency",
            "dev shop recommendations"
        ],
        "contract_dev": [
            "looking for contract developers",
            "contract engineer needed",
            "looking for contract software engineer"
        ]
    }

    BUYER_INTENT_TERMS = [
        "mvp", "dev shop", "software agency", "development partner", "fractional cto",
        "technical co-founder", "technical cofounder", "founding engineer", "first engineer",
        "building our", "building an", "stealth startup", "contract developers", "contract engineer"
    ]

    RECENT_DAYS = 3          # a query run within this window is not repeated

    def __init__(self, niche: str = "custom software & AI MVP engineering", memory=None):
        self.niche = niche
        self.memory = memory
        self.executed_queries: List[Dict[str, Any]] = []
        self.archetype_order = ["mvp_build", "founding_engineer", "agency_search", "contract_dev"]
        self.current_archetype_idx = 0
        self.consecutive_zero_yield_count = 0
        self.last_learned_lesson = "Start with high-intent founder vernacular ('building our MVP', 'hiring founding engineer')."

    @property
    def _anchors(self) -> List[str]:
        return self.HIGH_YIELD_US_TECH_HUBS + self.TOP_US_ACCELERATORS

    @property
    def current_archetype(self) -> str:
        return self.archetype_order[self.current_archetype_idx % len(self.archetype_order)]

    def shift_pattern(self, reason: str = "") -> str:
        """Actively pivots the search brain to the next distinct archetype when results are dry."""
        self.current_archetype_idx = (self.current_archetype_idx + 1) % len(self.archetype_order)
        self.consecutive_zero_yield_count = 0
        new_pattern = self.current_archetype
        return new_pattern

    def record_zero_yield(self, query: str):
        """Called when a query yields 0 results across both 24h and past-week."""
        self.consecutive_zero_yield_count += 1
        # Shift pattern immediately if 2 consecutive queries return 0
        if self.consecutive_zero_yield_count >= 2:
            self.shift_pattern(f"Consecutive zero results on query '{query}'")

    def record_positive_yield(self, query: str):
        """Reset zero-yield counter when a query succeeds."""
        self.consecutive_zero_yield_count = 0

    def record_feed_feedback(self, query: str, total_cards: int, categories: Dict[str, int]) -> str:
        """
        Synthesizes an empirical lesson from the query's feed results to teach the agent
        how to adapt its next query.
        """
        if total_cards == 0:
            lesson = f"Query '{query}' produced 0 results across 24h & week. Reason: phrasing was too narrow on LinkedIn. Action: Shift to a broader core intent."
            self.record_zero_yield(query)
        elif categories.get("RECRUITER", 0) >= max(2, int(total_cards * 0.4)):
            lesson = f"Query '{query}' was contaminated by recruiters/staffing agencies ({categories.get('RECRUITER', 0)} cards). Action: Avoid generic hiring terms; use founder-first vernacular like 'building our MVP' or 'recommend a dev shop'."
            self.shift_pattern("Recruiter contamination")
        elif categories.get("SELLER", 0) >= max(2, int(total_cards * 0.4)):
            lesson = f"Query '{query}' attracted competitor dev shops/sellers ({categories.get('SELLER', 0)} cards). Action: Switch to buyer-side phrasing like 'recommend a dev shop' or 'looking for technical cofounder'."
            self.shift_pattern("Seller contamination")
        elif categories.get("BUYER", 0) > 0:
            lesson = f"Query '{query}' successfully identified genuine buyers! Action: Exploit this winning semantic pattern across other US tech hubs."
            self.record_positive_yield(query)
        else:
            lesson = f"Query '{query}' produced cards with low commercial buying intent. Action: Rotate to an adjacent founder archetype."

        self.last_learned_lesson = lesson
        return lesson

    def level_of(self, query: str) -> int:
        q = (query or "").lower()
        if not any(a.lower() in q for a in self._anchors):
            return 1
        return 2  # Max constraint depth is strictly Level 2 (Hub + Intent). Level 3 is banned.

    def _stats(self) -> Dict[str, Any]:
        return self.memory.query_stats() if self.memory else {}

    def _recent(self, st) -> bool:
        from datetime import datetime, timedelta
        try:
            return datetime.fromisoformat(st["last_run"]) >= datetime.now() - timedelta(days=self.RECENT_DAYS)
        except (KeyError, TypeError, ValueError):
            return False

    def is_acceptable_query(self, query: str) -> bool:
        """
        Validates query sanity:
        Ensures query is non-empty and has meaningful substance.
        Allows the autonomous agent full freedom to explore natural founder expressions.
        """
        if not query or not isinstance(query, str):
            return False
        return len(query.strip()) >= 2

    def _generate_candidate_queries(self) -> List[str]:
        """Generates candidates prioritizing the active archetype and rotating hubs."""
        active_terms = self.ARCHETYPES[self.current_archetype]
        candidates = []
        
        # 1. Unanchored core intent phrases (Level 1)
        candidates.extend(active_terms)

        # 2. Tech-hub / Accelerator anchored phrases (Level 2)
        for anchor in self._anchors:
            for term in active_terms[:3]:
                candidates.append(f"{anchor} {term}")

        # 3. Secondary fallback: include top terms from other archetypes as alternative options
        for arch_name, terms in self.ARCHETYPES.items():
            if arch_name != self.current_archetype:
                candidates.extend(terms[:2])
                for anchor in self.HIGH_YIELD_US_TECH_HUBS[:3]:
                    candidates.append(f"{anchor} {terms[0]}")

        return candidates

    def get_next_recommended_query(self, already_executed: Optional[set] = None) -> str:
        done = {q.lower().strip() for q in (already_executed or set())} | {q["query"].lower().strip() for q in self.executed_queries}
        stats = self._stats()
        skip = done | {q.lower().strip() for q, st in stats.items() if self._recent(st)}
        
        candidates = self._generate_candidate_queries()
        fresh = [c for c in candidates if c.lower().strip() not in skip and c.lower().strip() not in done]
        
        if fresh:
            return fresh[0]
            
        # Cycle through all archetypes looking for unexecuted candidates
        for arch_name in self.archetype_order:
            for term in self.ARCHETYPES[arch_name]:
                if term.lower().strip() not in done:
                    return term
                for anchor in self.HIGH_YIELD_US_TECH_HUBS:
                    combo = f"{anchor} {term}"
                    if combo.lower().strip() not in done:
                        return combo

        # Last resort fallback: dynamic hub combos guaranteed to never collide
        for hub in ["San Francisco", "Austin", "New York", "Seattle", "Chicago", "Denver", "Boston", "Silicon Valley"]:
            for action in ["building MVP", "seeking technical co-founder", "hiring founding engineer", "looking for dev shop"]:
                combo = f"{hub} {action}"
                if combo.lower().strip() not in done:
                    return combo

        return "San Francisco building our MVP"

    def record_query_execution(self, query: str, freshness: str, cards_found: int, qualified_count: int):
        self.executed_queries.append({
            "query": query.lower().strip(),
            "freshness": freshness,
            "cards_found": cards_found,
            "qualified_count": qualified_count
        })
        if cards_found > 0:
            self.record_positive_yield(query)
        else:
            self.record_zero_yield(query)

    def diagnose_feed_outcome(self, cards_count: int, consecutive_empty_scrolls: int, consecutive_non_usa: int) -> Dict[str, Any]:
        """
        Diagnoses feed health and provides actionable strategic next moves.
        """
        if cards_count == 0:
            next_pattern = self.shift_pattern("0 cards found on feed")
            return {
                "action": "switch_query_or_freshness",
                "diagnosis": "0 cards found across both 24h and weekly timeframes. The query syntax may be too restrictive or has no matches in this timeframe.",
                "recommendation": f"Pivoting strategy: switched archetype to '{next_pattern}'. Recommended query: '{self.get_next_recommended_query()}'."
            }
            
        if consecutive_non_usa >= 2:
            return {
                "action": "bailout_feed",
                "diagnosis": f"Feed contaminated with {consecutive_non_usa} consecutive international non-US profiles.",
                "recommendation": "Stop scrolling this feed immediately. Execute a search anchored strictly to a US city (e.g., 'San Francisco building our MVP')."
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


