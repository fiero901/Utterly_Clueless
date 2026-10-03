"""JeevanRoute — Triage Agent (full working version).

A public emergency triage agent for Nepal. It has NO patient database —
the caller is the data source. The model interviews the user (in their
language), and when it has enough it calls the `finish_triage` tool,
whose arguments ARE the structured emergency state for the next agent.

Run interactively:
    python triage_agent.py
Run a scripted demo (no input needed):
    python triage_agent.py --demo
"""
import os

from openai import OpenAI
from dotenv import load_dotenv
import json

load_dotenv()  # load .env if present (also safe when app.py already loaded it)

_API_KEY = os.environ.get("SIMULACHAT_API_KEY")
if not _API_KEY:
    raise RuntimeError(
        "SIMULACHAT_API_KEY is not set. Copy .env.example to .env and add your key."
    )

client = OpenAI(
    base_url="https://simulachat.sushant.info.np/api/v1",
    api_key=_API_KEY,
)

SYSTEM = (
    "You are the TRIAGE AGENT of an emergency dispatch system for Nepal. "
    "You are a PUBLIC chat agent: you have NO patient database, so the caller "
    "is your only source of information. Ask only the 2-3 most critical "
    "questions, in the user's language (Nepali if they write in Nepali). "
    "Never invent details. Give safe immediate guidance while you ask. "
    "Once you have enough to triage, call the finish_triage tool exactly once."
)

FINISH_TOOL = {
    "type": "function",
    "function": {
        "name": "finish_triage",
        "description": "Call when you have enough information to produce the triage.",
        "parameters": {
            "type": "object",
            "properties": {
                "urgency": {"type": "string", "enum": ["critical", "urgent", "stable"]},
                "suspected_pathway": {"type": "string",
                                      "description": "e.g. stroke, cardiac, trauma, respiratory"},
                "symptoms": {"type": "array", "items": {"type": "string"}},
                "requirements": {"type": "array", "items": {"type": "string"},
                                 "description": "facility needs: CT, ICU, stroke_capability, trauma, oxygen, blood"},
                "immediate_actions": {"type": "array", "items": {"type": "string"}},
                "do_not": {"type": "array", "items": {"type": "string"}},
                "needs_ambulance": {"type": "boolean"},
            },
            "required": ["urgency", "suspected_pathway", "symptoms",
                         "requirements", "immediate_actions", "do_not", "needs_ambulance"],
        },
    },
}


def triage_turn(history, memory_context=""):
    """Send the chat history to the model.

    Args:
      history: list of {"role", "content"} messages (OpenAI format).
      memory_context: optional string of recalled local memories (from the
        browser-side memory layer). When non-empty it is prepended to the
        system prompt so the agent can use prior context.

    Returns (reply_text, triage_dict):
      - reply_text: the model's message to show the user (question or guidance)
      - triage_dict: the structured state if finish_triage was called, else None
    """
    system = SYSTEM
    if memory_context and memory_context.strip():
        system += (
            "\n\nRelevant local memories (from this device, provided by the user's "
            "browser — treat as prior context, not new input):\n" + memory_context.strip()
        )
    messages = [{"role": "system", "content": system}] + history
    resp = client.chat.completions.create(
        model="default",
        tools=[FINISH_TOOL],
        messages=messages,
    )
    msg = resp.choices[0].message

    if msg.tool_calls:
        tc = msg.tool_calls[0]
        return msg.content, json.loads(tc.function.arguments)

    # No tool call yet -> append the assistant turn and return its text.
    history.append({"role": "assistant", "content": msg.content})
    return msg.content, None


def run_demo():
    """Scripted end-to-end run: no keyboard input needed."""
    history = [
        {"role": "user", "content": "Mero baba achanak ladnu bhayo, bolna sakirakhnu bhako chaina."},
        {"role": "assistant", "content": "Kripaya turant 102 ma call garnu hos. K k prashna?"},
        {"role": "user", "content": "Mukh ek side bango cha. U 62 varsha ko, hypertension cha. Onset 18 minute aagadi."},
    ]
    text, triage = triage_turn(history)
    print("AGENT:", text)
    if triage:
        print("\nSTRUCTURED TRIAGE:")
        print(json.dumps(triage, indent=2, ensure_ascii=False))
    return triage


def run_interactive():
    """Live chat: keeps asking until the model calls finish_triage."""
    print("JeevanRoute triage agent. Type 'quit' to exit.\n")
    history = []
    while True:
        user = input("You: ").strip()
        if not user or user.lower() == "quit":
            break
        history.append({"role": "user", "content": user})
        text, triage = triage_turn(history)
        if text:
            print("Agent:", text)
        if triage:
            print("\n=== TRIAGE COMPLETE ===")
            print(json.dumps(triage, indent=2, ensure_ascii=False))
            break


if __name__ == "__main__":
    import sys
    if "--demo" in sys.argv:
        run_demo()
    else:
        run_interactive()
