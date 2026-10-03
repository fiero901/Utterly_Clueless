"""The single Agno "Commander" agent for JeevanRoute.

One agent conducts the emergency interview, calls finish_triage when it has
enough, and emits a raw triage dict. The deterministic layer (triage_state)
coerces and finalizes that dict. Multi-turn memory is Agno's session
(InMemoryDb); the browser keeps prefs/history (BrowserState).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from agno.agent import Agent
from agno.db.in_memory import InMemoryDb
from agno.models.openai import OpenAIChat

from triage_state import TriageState, coerce_triage

SIMULACHAT_BASE = "https://simulachat.sushant.info.np/api/v1"


@dataclass
class TurnResult:
    """One turn: the model's guidance text + an (optional) coerced triage.

    On a backend/API failure, `error` is set (and `text`/`triage` stay empty /
    None) so the UI can surface a clean "try again" instead of crashing.
    """
    text: str
    triage: Optional[TriageState] = None
    error: Optional[str] = None


def finish_triage(urgency: str, suspected_pathway: str, symptoms: list,
                  needs_ambulance: bool, vital_risks: list = None,
                  hospital_requirements: list = None) -> str:
    """Call this ONCE when you have enough to triage the emergency.

    urgency: "critical" (life threat: cardiac, major trauma, stroke, not
    breathing), "urgent" (severe, needs hospital soon), or "stable" (minor).
    suspected_pathway: short tag e.g. "cardiac", "trauma", "stroke", "respiratory".
    symptoms: the caller's reported symptoms as a list of short strings.
    needs_ambulance: True if transport should be arranged.
    """
    return "ok"


_INSTRUCTIONS = (
    "You are the TRIAGE AGENT of JeevanRoute, a Nepal emergency dispatch. "
    "The CALLER'S OWN WORDS are your only source of information. "
    "Conduct a focused interview: ask only the 2-3 most critical questions "
    "(what happened, when it started, key risk factors), in the CALLER'S "
    "LANGUAGE (Nepali if they write Nepali, English otherwise). Never ask for "
    "full name, phone, or address. "
    "A message may begin with a <context> block = caller metadata (district; "
    "may include approximate area). Use it silently for routing and NEVER "
    "reveal precise location back to the caller. "
    "When you have symptoms + onset + at least one risk factor, call "
    "finish_triage exactly once, then in the SAME reply give the caller 1-2 "
    "lines of safe immediate guidance (what to do right now / not to do). "
    "Do not diagnose a final condition; describe the suspected pathway."
)


_db = InMemoryDb()


def build_agent() -> Agent:
    api_key = os.environ.get("SIMULACHAT_API_KEY")
    if not api_key:
        raise RuntimeError("SIMULACHAT_API_KEY is not set (see .env)")
    return Agent(
        model=OpenAIChat(id="default", api_key=api_key, base_url=SIMULACHAT_BASE),
        name="JeevanRoute Commander",
        instructions=_INSTRUCTIONS,
        tools=[finish_triage],
        db=_db,
        add_history_to_context=True,
    )


def run_turn(message: str, emergency_id: str = "default",
             district: Optional[str] = None, agent: Optional[Agent] = None) -> TurnResult:
    """Send one user message to the commander; return text + coerced triage.

    `district` (if set) is injected as a <context> prefix on this turn only.
    `agent` is injectable for tests (pass a stub). Multi-turn history is keyed
    by session_id = "emergency:<emergency_id>".
    """
    if district:
        ctx = f"<context>District: {district}. Location is available for routing.</context>\n"
    else:
        ctx = ""
    full = ctx + message
    ag = agent if agent is not None else build_agent()
    try:
        out = ag.run(full, session_id=f"emergency:{emergency_id}")
    except Exception as exc:  # noqa: BLE001 — degrade gracefully, never crash the UI
        return TurnResult(text="", triage=None, error=str(exc))
    raw = next((t.tool_args for t in (out.tools or []) if t.tool_name == "finish_triage"), None)
    triage = coerce_triage(raw) if raw is not None else None
    return TurnResult(text=out.get_content_as_string() or "", triage=triage)

