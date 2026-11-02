"""
Context control for the agent loop: the model sees a short fixed prompt, a compact state summary
and only the last few turns. Everything else lives in code (judge, planner, memory, safety).
"""

import json

KEEP_TURNS = 2            # assistant turns (with their tool results) kept verbatim
SNIPPET_CHARS = 280       # post text per card handed to the model
MAX_TOOL_CHARS = 6000     # hard cap on any single tool message


def _compact_card(c):
    j = c.get("judge") or {}
    out = {
        "card_index": c.get("card_index"),
        "author": c.get("author"),
        "headline": (c.get("headline") or "")[:110],
        "snippet": " ".join((c.get("content") or "").split())[:SNIPPET_CHARS],
        "age": c.get("raw_timestamp", ""),
    }
    if j:
        out["judge"] = {
            "category": j.get("category"),
            "confidence": j.get("confidence"),
            "us_signal": j.get("us_signal"),
            "decision_maker": j.get("author_is_decision_maker"),
            "evidence": (j.get("evidence_quote") or "")[:140],
        }
    if "verified_location" in c:
        out["verified_location"] = c["verified_location"]
        out["is_usa_verified"] = c.get("is_usa_verified")
    return out


def compact_tool_result(name, result):
    """Shrink a tool result before it enters the conversation."""
    r = dict(result)
    if name == "scan_and_read_cards":
        r["cards"] = [_compact_card(c) for c in r.get("cards", [])]
    elif name == "search_web":
        r["results"] = str(r.get("results", ""))[:1200]
    text = json.dumps(r, ensure_ascii=False)
    return text if len(text) <= MAX_TOOL_CHARS else text[:MAX_TOOL_CHARS] + '..."}'


def window_messages(messages, keep_turns=KEEP_TURNS):
    """Keep [system, task] plus the last `keep_turns` assistant turns and their tool results."""
    head = messages[:2]
    tail = messages[2:]
    starts = [i for i, m in enumerate(tail) if m.get("role") == "assistant"]
    if len(starts) <= keep_turns:
        return head + tail
    return head + tail[starts[-keep_turns]:]
