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

    def __init__(self, niche: str = "custom software & AI MVP engineering"):
        self.niche = niche
        self.executed_queries: List[Dict[str, Any]] = []

    def get_proven_initial_queries(self) -> List[str]:
        """
        Returns a curated sequence of top-performing natural unquoted queries.
        """
        return [
            "San Francisco founding engineer",
            "Austin founding engineer",
            "Seattle founding engineer",
            "NYC founding engineer",
            "YC founding engineer",
            "South Park Commons founding engineer",
            "Bay Area founding engineer",
            "Boston founding engineer",
            "building MVP custom software",
            "Denver founding engineer",
            "looking for dev shop",
            "Los Angeles founding engineer",
            "Techstars founding engineer",
            "hiring first engineer startup"
        ]

    def record_query_execution(self, query: str, freshness: str, cards_found: int, qualified_count: int):
        self.executed_queries.append({
            "query": query.lower().strip(),
            "freshness": freshness,
            "cards_found": cards_found,
            "qualified_count": qualified_count
        })

    def get_next_recommended_query(self, already_executed: Optional[set] = None) -> str:
        executed_set = already_executed or {q["query"] for q in self.executed_queries}
        proven = self.get_proven_initial_queries()
        
        for q in proven:
            if q.lower().strip() not in executed_set:
                return q
                
        # Generate dynamic combinations if base list exhausted
        for hub in self.HIGH_YIELD_US_TECH_HUBS:
            for angle in ["hiring founding engineer", "building MVP", "seeking engineer"]:
                candidate = f"{hub} {angle}"
                if candidate.lower().strip() not in executed_set:
                    return candidate

        return "San Francisco founding engineer"

    def diagnose_feed_outcome(self, cards_count: int, consecutive_empty_scrolls: int, consecutive_non_usa: int) -> Dict[str, Any]:
        """
        Diagnoses feed health and provides actionable strategic next moves.
        """
        if cards_count == 0:
            return {
                "action": "switch_query_or_freshness",
                "diagnosis": "0 cards found on LinkedIn. The query syntax may be too restrictive or has no matches in this timeframe.",
                "recommendation": "Switch freshness from past-24h to past-week, or switch to a high-yield US Tech Hub (e.g. 'Austin founding engineer')."
            }
            
        if consecutive_non_usa >= 2:
            return {
                "action": "bailout_feed",
                "diagnosis": f"Feed contaminated with {consecutive_non_usa} consecutive international non-US profiles.",
                "recommendation": "Stop scrolling this feed immediately. Execute a search anchored strictly to a US city (e.g., 'Seattle founding engineer')."
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

