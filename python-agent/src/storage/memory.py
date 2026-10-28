import os
import json
from datetime import datetime
from src.config import BASE_DIR

class AgentMemory:
    """
    Pure empirical action & outcome log.
    ZERO predefined queries.
    Stores only what the AI has actually executed, the real results obtained,
    and developer feedback.
    """
    def __init__(self, filepath=None):
        if filepath is None:
            filepath = os.path.join(BASE_DIR, "agent_memory.json")
        self.filepath = os.path.abspath(filepath)
        self.data = {
            "created_at": datetime.now().isoformat(),
            "execution_history": [],
            "user_feedback_history": [],
            "qualified_leads": [],
            "last_updated": datetime.now().isoformat()
        }
        self.load()

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        # Migrate old structure cleanly if present
                        if "execution_history" not in loaded and "query_history" in loaded:
                            loaded["execution_history"] = loaded.pop("query_history")
                        # Strip any obsolete predefined query lists to eliminate hallucination
                        loaded.pop("successful_queries", None)
                        loaded.pop("failed_queries", None)
                        loaded.pop("learned_rules", None)
                        loaded.pop("previously_qualified_leads", None)
                        self.data.update(loaded)
            except Exception:
                pass

    def save(self):
        self.data["last_updated"] = datetime.now().isoformat()
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def record_query_execution(self, query: str, freshness: str, target_objective: str, cards_count: int, qualified_count: int, developer_guidance: str = "", outcome_note: str = ""):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "freshness": freshness,
            "target_objective": target_objective,
            "cards_found": cards_count,
            "qualified_count": qualified_count,
            "developer_guidance": developer_guidance,
            "outcome": outcome_note or (
                f"{qualified_count} genuine lead(s) qualified" if qualified_count > 0 
                else ("0 cards returned on LinkedIn (Zero results)" if cards_count == 0 
                else f"{cards_count} cards inspected, 0 passed full USA founder qualification")
            )
        }
        if "execution_history" not in self.data:
            self.data["execution_history"] = []
        self.data["execution_history"].append(entry)
        self.save()

    def record_query(self, query, freshness, rationale, expected_output, cards_count, qualified_count, developer_guidance="", outcome_note=""):
        self.record_query_execution(
            query=query,
            freshness=freshness,
            target_objective=expected_output or rationale,
            cards_count=cards_count,
            qualified_count=qualified_count,
            developer_guidance=developer_guidance,
            outcome_note=outcome_note
        )

    def record_user_feedback(self, lead_author: str, feedback: str):
        if not feedback or not feedback.strip():
            return
        clean = feedback.strip()
        if "user_feedback_history" not in self.data:
            self.data["user_feedback_history"] = []
        self.data["user_feedback_history"].append({
            "timestamp": datetime.now().isoformat(),
            "context": lead_author,
            "feedback": clean
        })
        self.save()

    def record_qualified_lead(self, lead_dict: dict):
        if "qualified_leads" not in self.data:
            self.data["qualified_leads"] = []
        p_url = (lead_dict.get("Profile URL") or "").strip().lower()
        if p_url and any((l.get("profile_url") or "").strip().lower() == p_url for l in self.data["qualified_leads"]):
            return
        self.data["qualified_leads"].append({
            "timestamp": datetime.now().isoformat(),
            "author": lead_dict.get("Author Name"),
            "profile_url": lead_dict.get("Profile URL"),
            "post_url": lead_dict.get("Post URL"),
            "company": lead_dict.get("Company Name"),
            "location": lead_dict.get("Verified Location"),
            "fit_score": lead_dict.get("Fit Score")
        })
        self.save()

    def get_memory_summary(self):
        history = self.data.get("execution_history", [])
        feedback = self.data.get("user_feedback_history", [])
        return {
            "recent_executions": history[-8:],
            "user_feedback_guidance": feedback[-5:],
            "total_queries_tested": len(history)
        }

