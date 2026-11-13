"""
LLM agent: understands the request, calls tools, returns a short spoken-style reply.
Uses the Anthropic Messages API with tool use. Swap this one file to use another LLM.
"""
import threading
from datetime import datetime

from . import config
from .tools import TOOL_SCHEMAS, execute_tool

MAX_TOOL_ROUNDS = 6
MAX_HISTORY = 30  # messages kept per session

SYSTEM_PROMPT = """You are the voice assistant for a restaurant discovery and table-booking service in India.
Your replies are converted to speech, so:
- Speak in short, natural sentences (usually 1-3). No markdown, bullet points, emojis or symbols.
- Say prices as "rupees" (e.g. "around four hundred rupees per person"). Never read out restaurant IDs.
- Mention at most 3 restaurant options at a time, then ask which one they like.
- Read confirmation codes slowly, letter by letter, e.g. "K, 7, M, 2, Q, X".
- Ask only ONE question at a time.

Rules:
- Only state facts that came from a tool. Never invent restaurants, ratings, prices or availability.
- If a rating is missing, say the restaurant is not rated yet. If a value is null, do not mention it.
- To book you need: restaurant, date, time, party size, the customer's name and phone number.
  Collect what is missing, then repeat the details back and get a clear "yes" BEFORE calling create_reservation.
  Always call check_availability first. If the slot is full, offer the alternative times returned.
- To look up or cancel a booking you need the confirmation code and the last 4 digits of the phone number.
  Confirm before cancelling.
- Convert relative dates ("tomorrow", "this Saturday") using today's date below. Tools use YYYY-MM-DD and 24-hour HH:MM.
  Restaurants take reservations 11:00 to 23:00 only.
- If a tool returns an error, explain it simply and suggest the next step.
- You cannot do anything outside restaurant search and bookings; politely say so.

Today is {today}, {weekday}. Local time is {now}."""

_sessions: dict[str, list] = {}
_lock = threading.Lock()
_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic  # imported lazily so tools/tests work without the SDK
        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    return _client


def _system_prompt() -> str:
    n = datetime.now()
    return SYSTEM_PROMPT.format(today=n.strftime("%Y-%m-%d"), weekday=n.strftime("%A"), now=n.strftime("%H:%M"))


def _trim(history: list) -> None:
    """Keep history bounded, always starting on a plain user message (never mid tool-call)."""
    if len(history) > MAX_HISTORY:
        del history[: len(history) - MAX_HISTORY]
    while history and not (history[0]["role"] == "user" and isinstance(history[0]["content"], str)):
        history.pop(0)


def reset_session(session_id: str) -> None:
    with _lock:
        _sessions.pop(session_id, None)


def chat(session_id: str, user_text: str) -> dict:
    """Run one customer turn. Returns {"reply": str, "tool_calls": [...]}."""
    with _lock:
        history = _sessions.setdefault(session_id, [])
    client = _get_client()
    start_len = len(history)
    history.append({"role": "user", "content": user_text})
    tool_log = []

    for _ in range(MAX_TOOL_ROUNDS):
        try:
            resp = client.messages.create(
                model=config.ANTHROPIC_MODEL,
                max_tokens=600,
                system=_system_prompt(),
                tools=TOOL_SCHEMAS,
                messages=history,
            )
        except Exception:
            del history[start_len:]  # don't leave a half-finished turn that would break the next call
            raise
        history.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            reply = "".join(b.text for b in resp.content if b.type == "text").strip()
            _trim(history)
            return {"reply": reply or "Sorry, could you say that again?", "tool_calls": tool_log}

        results = []
        for block in resp.content:
            if block.type == "tool_use":
                out = execute_tool(block.name, block.input)
                tool_log.append({"tool": block.name, "input": block.input, "output": out})
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": _to_json(out),
                                **({"is_error": True} if out.get("success") is False else {})})
        history.append({"role": "user", "content": results})

    _trim(history)
    return {"reply": "Sorry, I'm having trouble completing that right now. Could we try again?", "tool_calls": tool_log}


def _to_json(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False, default=str)
