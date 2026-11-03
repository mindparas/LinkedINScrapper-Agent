"""
Provider-neutral LLM access (Anthropic Claude or OpenAI).

Choose with LLM_PROVIDER=anthropic|openai in the environment or .env. When unset: anthropic if an
ANTHROPIC_API_KEY exists, otherwise openai. Per-role model override: LLM_MODEL_JUDGE, LLM_MODEL_AGENT,
LLM_MODEL_INTERPRETER (LEAD_JUDGE_MODEL is still honoured for the judge).

The rest of the code works in OpenAI's chat format. complete_json() and agent_step() hide the
differences: agent_step() always returns an OpenAI-shaped response, so the ReAct loop is unchanged.
"""

import json
import re
import urllib.error
import urllib.request

from src.config import OPENAI_API_KEY, ANTHROPIC_API_KEY, llm_setting

# Role -> (anthropic default, openai default, anthropic effort)
ROLE_DEFAULTS = {
    "judge":       ("claude-sonnet-5-5", "gpt-4o-mini", "low"),
    "agent":       ("claude-sonnet-5-5", "gpt-4o-mini", "low"),
    "interpreter": ("claude-sonnet-5-5", "gpt-4o-mini", "medium"),
}

# USD per 1M tokens (input, output). Estimates for the metrics report; edit if prices change.
PRICES = {
    "claude-fable-5-1": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "gpt-4o-mini": (0.15, 0.60),
}


def provider():
    p = llm_setting("LLM_PROVIDER").lower()
    if p in ("anthropic", "claude"):
        return "anthropic"
    if p == "openai":
        return "openai"
    return "anthropic" if ANTHROPIC_API_KEY else "openai"


def api_key_present():
    return bool(ANTHROPIC_API_KEY if provider() == "anthropic" else OPENAI_API_KEY)


def key_hint():
    return "ANTHROPIC_API_KEY" if provider() == "anthropic" else "OPENAI_API_KEY (or gpt-apikey)"


def model_for(role):
    a, o, _ = ROLE_DEFAULTS[role]
    default = a if provider() == "anthropic" else o
    override = llm_setting("LLM_MODEL_" + role.upper())
    if not override and role == "judge":
        override = llm_setting("LEAD_JUDGE_MODEL")
    return override or default


def price_for(model):
    return PRICES.get(model, PRICES["claude-sonnet-5-5"] if str(model).startswith("claude") else PRICES["gpt-4o-mini"])


def describe():
    return f"{provider()} (judge={model_for('judge')}, agent={model_for('agent')}, interpreter={model_for('interpreter')})"


# ── Anthropic plumbing ───────────────────────────────────────────────────────
_client = None


def _anthropic():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, max_retries=3, timeout=90.0)
    return _client


def _anthropic_params(model, role):
    """Per-model request knobs. The 5.x models reject temperature/top_p, so none is sent. Thinking is
    kept off for the agent loop where the model allows it: the loop edits older history (windowing),
    which would invalidate replayed thinking blocks."""
    kw = {}
    if "-5-" in model or model.startswith("claude-fable"):
        kw["output_config"] = {"effort": ROLE_DEFAULTS[role][2]}
        if role == "agent":
            if model.startswith("claude-sonnet-5-5"):
                kw["thinking"] = {"type": "between_tools"}
            elif model.startswith("claude-haiku-5-5"):
                kw["thinking"] = {"type": "disabled"}
    return kw


def _extract_json(text):
    text = (text or "").strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("model did not return JSON")
    return json.loads(m.group(0))


def _text_of(resp):
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


def _stop_check(resp):
    if getattr(resp, "stop_reason", "") == "refusal":
        raise RuntimeError("model refused the request")


# ── JSON-in/JSON-out calls (judge, interpreter) ──────────────────────────────
def complete_json(system, user, role, max_tokens=1500, timeout=45):
    """Returns (parsed_json_dict, usage={'prompt_tokens','completion_tokens'}, model)."""
    model = model_for(role)
    if provider() == "anthropic":
        resp = _anthropic().with_options(timeout=float(timeout)).messages.create(
            model=model,
            max_tokens=max(max_tokens, 3000),   # thinking tokens count toward max_tokens
            system=system + "\n\nRespond with a single JSON object and nothing else.",
            messages=[{"role": "user", "content": user}],
            **_anthropic_params(model, role),
        )
        _stop_check(resp)
        usage = {"prompt_tokens": resp.usage.input_tokens, "completion_tokens": resp.usage.output_tokens}
        return _extract_json(_text_of(resp)), usage, model

    payload = {
        "model": model, "temperature": 0, "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {OPENAI_API_KEY}"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return json.loads(body["choices"][0]["message"]["content"]), (body.get("usage") or {}), model


def is_retryable(exc):
    """True for rate-limit / transient server errors (callers back off and retry)."""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in (429, 500, 502, 503)
    code = getattr(exc, "status_code", None)
    return code in (408, 429, 500, 502, 503, 529)


def describe_error(exc):
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    code = getattr(exc, "status_code", None)
    if code:
        return f"HTTP {code}: {str(getattr(exc, 'message', exc))[:160]}"
    return str(exc)[:200]


# ── Agent loop step (tool calling) ───────────────────────────────────────────
def _to_anthropic_tools(tools):
    out = []
    for t in tools:
        f = t.get("function", t)
        out.append({"name": f["name"], "description": f.get("description", ""),
                    "input_schema": f.get("parameters") or {"type": "object", "properties": {}}})
    return out


def _to_anthropic_messages(messages):
    """OpenAI-format messages -> (system, anthropic messages). Consecutive same-role turns are merged,
    tool results go first in their user turn, and results with no matching tool_use are dropped."""
    system_parts, turns, open_ids = [], [], set()

    def push(role, blocks):
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"].extend(blocks)
        else:
            turns.append({"role": role, "content": list(blocks)})

    for m in messages:
        role = m.get("role")
        if role == "system":
            system_parts.append(str(m.get("content") or ""))
        elif role == "user":
            text = str(m.get("content") or "").strip() or "(continue)"
            push("user", [{"type": "text", "text": text}])
        elif role == "assistant":
            blocks = []
            if str(m.get("content") or "").strip():
                blocks.append({"type": "text", "text": str(m["content"]).strip()})
            open_ids = set()
            for tc in m.get("tool_calls") or []:
                try:
                    args = json.loads(tc["function"].get("arguments") or "{}")
                except Exception:
                    args = {}
                blocks.append({"type": "tool_use", "id": tc["id"], "name": tc["function"]["name"],
                               "input": args if isinstance(args, dict) else {}})
                open_ids.add(tc["id"])
            push("assistant", blocks or [{"type": "text", "text": "(no output)"}])
        elif role == "tool":
            if m.get("tool_call_id") in open_ids:
                block = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": str(m.get("content") or "ok")}
                if turns and turns[-1]["role"] == "user":
                    turns[-1]["content"].insert(sum(1 for b in turns[-1]["content"] if b["type"] == "tool_result"), block)
                else:
                    push("user", [block])

    if not turns or turns[0]["role"] != "user":
        turns.insert(0, {"role": "user", "content": [{"type": "text", "text": "(start)"}]})
    return "\n\n".join(system_parts), turns


def agent_step(messages, tools):
    """One agent turn. Returns an OpenAI-shaped dict:
    {'choices': [{'message': {'content', 'tool_calls': [...]}}], 'usage': {...}}"""
    model = model_for("agent")
    if provider() == "anthropic":
        system, turns = _to_anthropic_messages(messages)
        resp = _anthropic().messages.create(
            model=model, max_tokens=4096, system=system, messages=turns,
            tools=_to_anthropic_tools(tools), **_anthropic_params(model, "agent"))
        _stop_check(resp)
        calls = [{"id": b.id, "type": "function",
                  "function": {"name": b.name, "arguments": json.dumps(b.input, ensure_ascii=False)}}
                 for b in resp.content if b.type == "tool_use"]
        msg = {"role": "assistant", "content": _text_of(resp) or None}
        if calls:
            msg["tool_calls"] = calls
        return {"choices": [{"message": msg}],
                "usage": {"prompt_tokens": resp.usage.input_tokens, "completion_tokens": resp.usage.output_tokens}}

    payload = {"model": model, "messages": messages, "tools": tools, "tool_choice": "auto", "temperature": 0.2}
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {OPENAI_API_KEY}"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))
