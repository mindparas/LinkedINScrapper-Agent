"""
LinkedIn account safety: persistent daily action budgets and checkpoint/captcha detection.
The agent stops cleanly (and says why) instead of pushing through a warning.
"""

import os
import json
from datetime import date

from src.config import BASE_DIR

DAILY_LIMITS = {
    "searches": int(os.environ.get("BDE_MAX_SEARCHES_PER_DAY", "40")),
    "profile_visits": int(os.environ.get("BDE_MAX_PROFILE_VISITS_PER_DAY", "60")),
}

CHECKPOINT_URL_MARKERS = ("checkpoint", "authwall", "/uas/login", "challenge", "/login")
CHECKPOINT_TEXT_MARKERS = (
    "unusual activity", "verify you're a human", "security verification",
    "let's do a quick security check", "your account has been restricted",
    "temporarily restricted", "confirm you're not a robot",
)


class UsageBudget:
    def __init__(self, path=None):
        self.path = path or os.path.join(BASE_DIR, "dataset", "usage.json")
        self.day = date.today().isoformat()
        self.counts = {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("day") == self.day:
                self.counts = data.get("counts", {})
        except Exception:
            pass

    def used(self, kind):
        return self.counts.get(kind, 0)

    def remaining(self, kind):
        return max(0, DAILY_LIMITS[kind] - self.used(kind))

    def allow(self, kind):
        return self.used(kind) < DAILY_LIMITS[kind]

    def record(self, kind):
        self.counts[kind] = self.used(kind) + 1
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"day": self.day, "counts": self.counts}, f)
        except Exception:
            pass


def detect_checkpoint(driver):
    """Returns a reason string if LinkedIn is challenging the session, else ''."""
    try:
        url = (driver.current_url or "").lower()
        if any(m in url for m in CHECKPOINT_URL_MARKERS):
            return f"LinkedIn redirected to a checkpoint/login page ({url[:80]})"
        body = driver.execute_script("return (document.body && document.body.innerText || '').slice(0, 3000)") or ""
        low = body.lower()
        for m in CHECKPOINT_TEXT_MARKERS:
            if m in low:
                return f"LinkedIn showed a verification warning ('{m}')"
    except Exception:
        pass
    return ""
