"""
LLM lead judge: reads the full post + author headline and returns a structured,
evidence-backed verdict. Replaces brittle keyword rules as the primary gate.
Results are cached on disk so repeated cards (and eval runs) cost nothing.
"""

import os
import json
import time
import hashlib
import urllib.request
import urllib.error

from src.config import BASE_DIR
from src import llm

JUDGE_CATEGORIES = [
    "BUYER", "SELLER", "RECRUITER", "JOB_SEEKER", "INVESTOR_MEDIA", "CLOSED", "NO_NEED", "NON_US",
]

_DEFAULT_HEAD = """You qualify LinkedIn posts for an Indian software/AI development agency that sells outsourced engineering to US companies.

A BUYER is a founder / co-founder / CEO / CTO / VP or Head of Engineering or Product at a company that is NOT a dev agency, who in THIS post shows a current need for outside engineering help: building an MVP/app/platform, looking for a dev shop/agency/contractors/technical partner, or hiring engineers or a fractional CTO.

Classify the post into exactly one category:
- BUYER: meets the definition above.
- SELLER: agency, freelancer, consultant or founder promoting their own dev/AI/automation services.
- RECRUITER: recruiter, staffing, headhunter, or hiring on behalf of a client.
- JOB_SEEKER: looking for a job, student, "open to work", or an engineer announcing availability.
- INVESTOR_MEDIA: VC, accelerator, newsletter, podcast, event or community promotion.
- CLOSED: role filled, new job announcement, "welcome to the team".
- NO_NEED: thought leadership, non-engineering hiring, funding news or anything with no engineering ask.
- NON_US: the author is clearly outside the United States (only use if the text shows it).

"""

_RULES = """- Judge only from the text given. Never invent facts.
- evidence_quote must be an exact short quote (max 200 chars) copied from the post that justifies the category. Use "" only if the post is empty.
- confidence is 0.0-1.0. Use below 0.6 when the post is ambiguous.
- author_is_decision_maker is true only if the headline/post indicates founder, co-founder, CEO, CTO, owner, president, or VP/Head/Director of engineering/product/technology.
- us_signal is "US", "NON_US" or "UNKNOWN" based only on the text. Use "NON_US" whenever the headline or post names a non-US country, state/province or city (e.g. India, Pakistan, Punjab, Bengaluru, Lagos, London, Dubai, Berlin) or targets a non-US market ("India's", "UK-based", "for the Indian market"). Use "US" only for explicit US places (US cities/states, "US-based"). Otherwise "UNKNOWN".
- need_summary is one short sentence describing what they need (empty if not a BUYER).

Return JSON only with keys: category, is_buyer, confidence, author_is_decision_maker, us_signal, need_type, need_summary, evidence_quote, reasoning."""

_DEFAULT_NEED_TYPES = """need_type is one of: AGENCY, MVP_BUILD, CONTRACTOR, HIRE_ENGINEER, TECH_COFOUNDER, FRACTIONAL_CTO, OTHER, NONE."""

_CUSTOM_HEAD = """You qualify LinkedIn posts against a user-defined MISSION for a lead-generation team.

MISSION: {summary}
USER'S ORIGINAL REQUEST: "{raw}"
QUALIFYING POSTS: {post_types}
AUTHOR SHOULD BE: {author}
LOCATION: {location}
MUST HAVE: {must_have}
MUST NOT MATCH: {exclude}

Classify the post into exactly one category:
- BUYER: the post satisfies the MISSION. "BUYER" is simply the label for a match, whatever the mission is. If the MISSION explicitly targets a group that another category below would normally cover (e.g. recruiters, investors), that group is BUYER here.
- SELLER: promoting their own services, products or agency (unless the MISSION targets this).
- RECRUITER: recruiter, staffing, headhunter, or hiring on behalf of a client (unless the MISSION targets this).
- JOB_SEEKER: looking for a job, student, "open to work", or announcing availability (unless the MISSION targets this).
- INVESTOR_MEDIA: VC, accelerator, newsletter, podcast, event or community promotion (unless the MISSION targets this).
- CLOSED: need already met, role filled, new job announcement.
- NO_NEED: thought leadership or anything that does not meet the MISSION.
- NON_US: the author is clearly outside the United States (only use if the text shows it AND the MISSION requires the US).

"""

_CUSTOM_NEED_TYPE = """need_type is a short UPPER_SNAKE_CASE label for the kind of match (e.g. HIRING_ML_ENGINEER), or NONE when not a BUYER."""


def build_judge_prompt(mission=None):
    """Default mission -> the original prompt (unchanged so the disk cache stays valid)."""
    if mission is None or getattr(mission, "is_default", True):
        return JUDGE_PROMPT
    head = _CUSTOM_HEAD.format(
        summary=mission.summary,
        raw=mission.raw_intent.replace('"', "'")[:600],
        post_types="; ".join(mission.post_types) or "see MISSION",
        author=mission.author_profile + ("" if mission.require_decision_maker else " (any author type is acceptable)"),
        location=("United States" if mission.needs_us else "no restriction") + (f" ({mission.location_note})" if mission.location_note else ""),
        must_have="; ".join(mission.must_have) or "none",
        exclude="; ".join(mission.exclude) or "none",
    )
    return head + "Rules:\n" + _RULES + "\n" + _CUSTOM_NEED_TYPE


JUDGE_PROMPT = _DEFAULT_HEAD + "Rules:\n" + _RULES + "\n" + _DEFAULT_NEED_TYPES



class LeadJudge:
    def __init__(self, model=None, cache_path=None, logger=None, mission=None):
        self.mission = mission
        self.prompt = build_judge_prompt(mission)
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.errors = 0
        self.model = model or llm.model_for("judge")
        self.cache_path = cache_path or os.path.join(BASE_DIR, "dataset", "judge_cache.json")
        self.logger = logger
        self.calls = 0
        self.cache_hits = 0
        self._cache = {}
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                self._cache = json.load(f)
        except Exception:
            self._cache = {}

    @staticmethod
    def _text(author, headline, content):
        return f"AUTHOR: {author}\nHEADLINE: {headline}\nPOST:\n{(content or '')[:1800]}"

    def _key(self, text):
        return hashlib.sha1(f"{self.model}|{self.prompt}|{text}".encode("utf-8")).hexdigest()

    def _save_cache(self):
        try:
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False)
        except Exception:
            pass

    def _call_llm(self, text):
        data, usage, _ = llm.complete_json(self.prompt, text, "judge", max_tokens=1200, timeout=60)
        self.prompt_tokens += int(usage.get("prompt_tokens", 0) or 0)
        self.completion_tokens += int(usage.get("completion_tokens", 0) or 0)
        return data

    @staticmethod
    def _normalize(raw):
        cat = str(raw.get("category", "NO_NEED")).upper()
        if cat not in JUDGE_CATEGORIES:
            cat = "NO_NEED"
        try:
            conf = max(0.0, min(1.0, float(raw.get("confidence", 0))))
        except (TypeError, ValueError):
            conf = 0.0
        return {
            "category": cat,
            "is_buyer": cat == "BUYER",
            "confidence": conf,
            "author_is_decision_maker": bool(raw.get("author_is_decision_maker")),
            "us_signal": str(raw.get("us_signal", "UNKNOWN")).upper(),
            "need_type": str(raw.get("need_type", "NONE")).upper(),
            "need_summary": str(raw.get("need_summary", ""))[:200],
            "evidence_quote": str(raw.get("evidence_quote", ""))[:300],
            "reasoning": str(raw.get("reasoning", ""))[:400],
        }

    def judge(self, author, headline, content):
        """Returns a verdict dict. On API failure returns category 'ERROR' (callers fall back to rules)."""
        text = self._text(author, headline, content)
        key = self._key(text)
        if key in self._cache:
            self.cache_hits += 1
            return self._cache[key]

        last_err = None
        for attempt in range(3):
            try:
                verdict = self._normalize(self._call_llm(text))
                self.calls += 1
                self._cache[key] = verdict
                self._save_cache()
                return verdict
            except Exception as e:
                last_err = llm.describe_error(e)
                if llm.is_retryable(e):
                    time.sleep(2 * (attempt + 1))
                elif isinstance(e, (ValueError, KeyError)):   # unparseable reply: retry quickly
                    time.sleep(1)
                else:
                    break
        self.errors += 1
        if self.logger:
            self.logger.error(f"Lead judge failed for '{author}': {last_err}")
        return {"category": "ERROR", "is_buyer": False, "confidence": 0.0, "author_is_decision_maker": False,
                "us_signal": "UNKNOWN", "need_type": "NONE", "need_summary": "", "evidence_quote": "",
                "reasoning": f"judge unavailable: {last_err}"}

    @staticmethod
    def is_qualified(v, min_conf=0.7, us_verified=False, require_dm=True):
        """The single rule that decides whether a verdict can become a saved lead.
        A text-only NON_US guess blocks a lead unless the profile top-card confirmed a US location
        (callers pass us_verified=True when the mission has no location restriction).
        require_dm=False is for missions that accept any author type."""
        return bool(v.get("is_buyer") and v.get("confidence", 0) >= min_conf
                    and (v.get("author_is_decision_maker") or not require_dm)
                    and (v.get("us_signal") != "NON_US" or us_verified))
