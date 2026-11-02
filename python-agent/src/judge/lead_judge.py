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

from src.config import BASE_DIR, OPENAI_API_KEY

JUDGE_CATEGORIES = [
    "BUYER", "SELLER", "RECRUITER", "JOB_SEEKER", "INVESTOR_MEDIA", "CLOSED", "NO_NEED", "NON_US",
]

JUDGE_PROMPT = """You qualify LinkedIn posts for an Indian software/AI development agency that sells outsourced engineering to US companies.

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

Rules:
- Judge only from the text given. Never invent facts.
- evidence_quote must be an exact short quote (max 200 chars) copied from the post that justifies the category. Use "" only if the post is empty.
- confidence is 0.0-1.0. Use below 0.6 when the post is ambiguous.
- author_is_decision_maker is true only if the headline/post indicates founder, co-founder, CEO, CTO, owner, president, or VP/Head/Director of engineering/product/technology.
- us_signal is "US", "NON_US" or "UNKNOWN" based only on the text. Use "NON_US" whenever the headline or post names a non-US country, state/province or city (e.g. India, Pakistan, Punjab, Bengaluru, Lagos, London, Dubai, Berlin) or targets a non-US market ("India's", "UK-based", "for the Indian market"). Use "US" only for explicit US places (US cities/states, "US-based"). Otherwise "UNKNOWN".
- need_summary is one short sentence describing what they need (empty if not a BUYER).

Return JSON only with keys: category, is_buyer, confidence, author_is_decision_maker, us_signal, need_type, need_summary, evidence_quote, reasoning.
need_type is one of: AGENCY, MVP_BUILD, CONTRACTOR, HIRE_ENGINEER, TECH_COFOUNDER, FRACTIONAL_CTO, OTHER, NONE."""


class LeadJudge:
    def __init__(self, model=None, cache_path=None, logger=None):
        self.model = model or os.environ.get("LEAD_JUDGE_MODEL", "gpt-4o-mini")
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
        return hashlib.sha1(f"{self.model}|{JUDGE_PROMPT}|{text}".encode("utf-8")).hexdigest()

    def _save_cache(self):
        try:
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False)
        except Exception:
            pass

    def _call_llm(self, text):
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": JUDGE_PROMPT},
                {"role": "user", "content": text},
            ],
        }
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {OPENAI_API_KEY}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=40) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return json.loads(body["choices"][0]["message"]["content"])

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
            except urllib.error.HTTPError as e:
                last_err = f"HTTP {e.code}"
                time.sleep(2 * (attempt + 1) if e.code in (429, 500, 502, 503) else 0)
                if e.code not in (429, 500, 502, 503):
                    break
            except Exception as e:
                last_err = str(e)
                time.sleep(1)
        if self.logger:
            self.logger.error(f"Lead judge failed for '{author}': {last_err}")
        return {"category": "ERROR", "is_buyer": False, "confidence": 0.0, "author_is_decision_maker": False,
                "us_signal": "UNKNOWN", "need_type": "NONE", "need_summary": "", "evidence_quote": "",
                "reasoning": f"judge unavailable: {last_err}"}

    @staticmethod
    def is_qualified(v, min_conf=0.7, us_verified=False):
        """The single rule that decides whether a verdict can become a saved lead.
        A text-only NON_US guess blocks a lead unless the profile top-card confirmed a US location."""
        return bool(v.get("is_buyer") and v.get("confidence", 0) >= min_conf
                    and v.get("author_is_decision_maker")
                    and (v.get("us_signal") != "NON_US" or us_verified))
