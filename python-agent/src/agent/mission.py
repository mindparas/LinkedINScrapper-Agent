"""
Mission: the user's description of the posts they want, turned into a structured spec the whole
agent follows (query planning, the lead judge, location checks, outreach text, system prompt).

The default mission reproduces the original behaviour (US founders who need outsourced engineering)
without any LLM call. A custom mission is interpreted once at start-up by an LLM and shown to the
user for confirmation before any LinkedIn action happens.
"""

import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from src import llm

MAX_FAMILIES = 4
MAX_QUERIES_PER_FAMILY = 6
MIN_TOTAL_QUERIES = 3


@dataclass
class Mission:
    raw_intent: str = ""
    title: str = "US founders needing outsourced engineering"
    summary: str = ("Founders / CTOs / VPs in the US who posted a CURRENT need for outside engineering help "
                    "(MVP build, dev shop/agency, contractors, technical co-founder, engineering hires).")
    post_types: List[str] = field(default_factory=list)
    author_profile: str = "Founder, co-founder, CEO, CTO, or VP/Head of Engineering/Product at a non-agency company"
    require_decision_maker: bool = True
    location_scope: str = "US"            # "US" (profile top-card must confirm US) or "ANY"
    location_note: str = ""
    must_have: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)
    query_families: Dict[str, List[str]] = field(default_factory=dict)
    outreach_angle: str = ""
    assumptions: List[str] = field(default_factory=list)
    is_default: bool = True

    # ── presentation ────────────────────────────────────────────────────────
    def describe(self):
        lines = [f"Mission: {self.title}", f"  Looking for : {self.summary}"]
        if self.post_types:
            lines.append("  Post types  : " + "; ".join(self.post_types))
        lines.append(f"  Author      : {self.author_profile}"
                     + ("" if self.require_decision_maker else " (decision-maker NOT required)"))
        loc = "United States only (verified on the author's profile)" if self.location_scope == "US" \
            else "Any location"
        lines.append(f"  Location    : {loc}" + (f" — {self.location_note}" if self.location_note else ""))
        if self.must_have:
            lines.append("  Must have   : " + "; ".join(self.must_have))
        if self.exclude:
            lines.append("  Exclude     : " + "; ".join(self.exclude))
        if self.query_families:
            lines.append("  Search plan :")
            for name, qs in self.query_families.items():
                lines.append(f"    - {name}: " + " | ".join(qs))
        for a in self.assumptions:
            lines.append(f"  Assumption  : {a}")
        return "\n".join(lines)

    def to_dict(self):
        return asdict(self)

    @property
    def key(self):
        """Namespace for per-mission memory (skip list, query stats); empty for the default mission so
        existing memory keeps working. Posts rejected for one mission must not hide from another."""
        if self.is_default:
            return ""
        import hashlib
        blob = f"{self.summary}|{self.location_scope}|{self.require_decision_maker}|{'|'.join(self.must_have)}|{'|'.join(self.exclude)}"
        return "m" + hashlib.sha1(blob.encode("utf-8")).hexdigest()[:8]

    @property
    def needs_us(self):
        return self.location_scope == "US"

    @classmethod
    def default(cls):
        return cls()


DEFAULT_MISSION = Mission.default()

INTERPRETER_PROMPT = """You configure an autonomous LinkedIn lead-finding agent. The user describes, in their own words, the kind of LinkedIn POSTS they want to find. Work out exactly what they mean and return a precise specification.

Return JSON only with these keys:
- actionable: true if the request is specific enough to search for; false if it is too vague to act on (e.g. "good leads").
- clarifying_question: if not actionable, ONE short question that would make it actionable, else "".
- title: 3-8 word name for this mission.
- summary: 1-2 sentences restating precisely which posts qualify, as a judge would apply them.
- post_types: 2-5 short phrases describing qualifying posts (what the author is saying/asking).
- author_profile: who should be posting (role/type of person). Do not add restrictions the user did not ask for.
- require_decision_maker: true only if the user wants founders/executives/owners; false if any author type is fine.
- location_scope: "US" if the user wants US authors (or says nothing about location AND the request is about the US market); "ANY" if the user wants no location restriction or names a non-US region (put that region in location_note).
- location_note: short note on any location detail, else "".
- must_have: concrete conditions the post must satisfy (e.g. "states a current need", "mentions a budget").
- exclude: kinds of posts/authors that must NOT match (e.g. recruiters, agencies selling services, job seekers) - include the ones that clearly contradict the request.
- query_families: object of 2-4 families (short snake_case names) each with 3-6 LinkedIn content-search queries. Queries must be natural phrases people actually WRITE in such posts, 2-4 words, no quotes, no AND/OR/NOT, no city or country names. Cover different phrasings of the same need, ordered from most to least likely to hit. Write in the first-person voice of the buyer; avoid words that sellers and recruiters use (agency, services, solutions, expert, hiring) unless the post type truly needs them.
- outreach_angle: one sentence on how the sender's team can help a person who wrote such a post (use the agency description given).
- assumptions: any interpretation choices you had to make that the user should double-check (empty list if none).

Never invent requirements. If the user's text is ambiguous, pick the most literal reading and record it in assumptions."""


def _clean_query(q):
    q = re.sub(r"(?<=\w)['’](?=\w)", "", str(q))   # don't -> dont (keeps one token)
    q = re.sub(r'["“”\']', ' ', str(q))
    q = re.sub(r'\b(?:AND|OR|NOT)\b|[()]', ' ', q)
    q = re.sub(r'\s+', ' ', q).strip()
    words = q.split()
    if not (2 <= len(words) <= 6):
        return ""
    return q


def _str_list(v, limit=8, width=160):
    if not isinstance(v, list):
        return []
    return [str(x).strip()[:width] for x in v if str(x).strip()][:limit]


def _build(raw_intent, data):
    fams, seen = {}, set()
    raw_fams = data.get("query_families")
    if isinstance(raw_fams, dict):
        for name, qs in list(raw_fams.items())[:MAX_FAMILIES]:
            clean = []
            for q in (qs if isinstance(qs, list) else []):
                cq = _clean_query(q)
                if cq and cq.lower() not in seen:
                    seen.add(cq.lower())
                    clean.append(cq)
            if clean:
                fams[re.sub(r'\W+', '_', str(name).strip().lower()) or "queries"] = clean[:MAX_QUERIES_PER_FAMILY]
    if sum(len(v) for v in fams.values()) < MIN_TOTAL_QUERIES:
        raise ValueError("interpreter returned too few usable search queries")

    scope = str(data.get("location_scope", "US")).upper()
    return Mission(
        raw_intent=raw_intent,
        title=str(data.get("title") or "Custom mission")[:80],
        summary=str(data.get("summary") or raw_intent)[:500],
        post_types=_str_list(data.get("post_types"), 5),
        author_profile=str(data.get("author_profile") or "Any author")[:200],
        require_decision_maker=bool(data.get("require_decision_maker", False)),
        location_scope="US" if scope == "US" else "ANY",
        location_note=str(data.get("location_note") or "")[:160],
        must_have=_str_list(data.get("must_have")),
        exclude=_str_list(data.get("exclude")),
        query_families=fams,
        outreach_angle=str(data.get("outreach_angle") or "")[:300],
        assumptions=_str_list(data.get("assumptions"), 5, 220),
        is_default=False,
    )


def interpret_intent(raw_intent: str, niche: str = "", model: Optional[str] = None, logger=None):
    """
    Returns (Mission | None, clarifying_question). Exactly one is meaningful:
      (mission, "")  -> understood
      (None, "...")  -> too vague; ask the user this question
    Raises RuntimeError when the model cannot be reached or returns an unusable spec.
    """
    raw_intent = (raw_intent or "").strip()
    if not raw_intent:
        return DEFAULT_MISSION, ""
    user_msg = f"Sender's agency/service: {niche or 'not specified'}\n\nUser's description of the posts they want:\n{raw_intent}"
    last = None
    for _ in range(2):
        try:
            data, _usage, _model = llm.complete_json(INTERPRETER_PROMPT, user_msg, "interpreter", max_tokens=2500, timeout=60)
            if data.get("actionable") is False:
                return None, str(data.get("clarifying_question") or "Can you describe the posts you want in more detail?")
            return _build(raw_intent, data), ""
        except Exception as e:
            last = llm.describe_error(e)
        if logger:
            logger.error(f"Intent interpretation attempt failed: {last}")
    raise RuntimeError(f"Could not interpret the intent ({last})")


DEFAULT_INTENT_HINT = "US founders/CTOs who need outsourced engineering (MVP build, dev shop, contractors, technical co-founder)"
MAX_CLARIFY_ROUNDS = 4


def resolve_mission(intent=None, niche="", interactive=True, confirm=True, logger=None):
    """
    Turn the user's intent text into a confirmed Mission.

    intent=None and interactive  -> ask for it (ENTER keeps the default mission)
    confirm=True and interactive -> show the interpretation; ENTER accepts, any text refines it, 'q' cancels
    Non-interactive with a vague intent raises ValueError (nobody to ask).
    """
    typed = False
    if intent is None:
        if not interactive:
            return DEFAULT_MISSION
        try:
            intent = input(f"\n👉 Describe the posts you want (ENTER = default: {DEFAULT_INTENT_HINT}):\n   > ").strip()
        except (EOFError, KeyboardInterrupt):
            intent = ""
        typed = True
    text = (intent or "").strip()
    if not text:
        return DEFAULT_MISSION

    mission = None
    for _ in range(MAX_CLARIFY_ROUNDS):
        print("\n🧠 Understanding your request…")
        mission, question = interpret_intent(text, niche=niche, logger=logger)
        if mission is None:
            if not interactive:
                raise ValueError(f"The intent is too vague to act on. {question}")
            try:
                answer = input(f"   ❓ {question}\n   > ").strip()
            except (EOFError, KeyboardInterrupt):
                raise ValueError(f"The intent is too vague to act on. {question}")
            text += "\nUser clarification: " + answer
            continue
        print("\n" + mission.describe())
        if not (interactive and confirm and typed):
            return mission
        try:
            reply = input("\n   Press ENTER to start with this, type a correction/addition to refine it, or q to cancel: ").strip()
        except (EOFError, KeyboardInterrupt):
            return mission
        if not reply:
            return mission
        if reply.lower() in ("q", "quit", "cancel", "exit"):
            raise SystemExit("Cancelled by user.")
        text += "\nUser refinement: " + reply
    if mission is None:
        raise ValueError("Could not get enough detail to define the mission.")
    return mission
