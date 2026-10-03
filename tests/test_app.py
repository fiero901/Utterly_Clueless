"""Integration-level regression tests for the app handler seam (offline).

The critical bug guarded here: `MultimodalTextbox` always posts the user
message as a dict `{"text": ..., "files": [...]}`. If that dict reaches
`commander.run_turn`, the string concat `ctx + message` raises
`TypeError: can only concatenate str (not "dict")`. `_respond` must extract
the text string first.
"""
import pytest

import app
from commander import TurnResult


@pytest.fixture(autouse=True)
def _no_real_agent(monkeypatch):
    # Keep these tests offline: _respond calls _agent() (lazy build_agent),
    # which needs SIMULACHAT_API_KEY. The fake run_turn ignores it anyway.
    monkeypatch.setattr(app, "_agent", lambda: None)


def test_respond_passes_string_to_run_turn_for_dict_message(monkeypatch):
    seen = {}

    def fake_run_turn(message, emergency_id=None, district=None, agent=None):
        seen["message"] = message
        return TurnResult(text="कृपय थप विवरण दिनुहोस्", triage=None)

    monkeypatch.setattr(app, "run_turn", fake_run_turn)
    hist, msg, status, progress = app._respond(
        [], {"text": "chest pain, sweating", "files": []}, "e1", "Kathmandu", {})
    # The agent must see a plain string, never the raw dict.
    assert seen["message"] == "chest pain, sweating"
    assert isinstance(seen["message"], str)
    # The chat shows the user's text part.
    assert hist[0]["role"] == "user" and hist[0]["content"] == "chest pain, sweating"
    # Still interviewing -> step 2 active.
    assert "⏳" in progress


def test_respond_still_accepts_plain_string_message(monkeypatch):
    seen = {}

    def fake_run_turn(message, emergency_id=None, district=None, agent=None):
        seen["message"] = message
        return TurnResult(text="ok", triage=None)

    monkeypatch.setattr(app, "run_turn", fake_run_turn)
    hist, msg, status, progress = app._respond([], "chest pain", "e2", "Kathmandu", {})
    assert seen["message"] == "chest pain"
    assert hist[0]["content"] == "chest pain"


def test_respond_surfaces_api_error_cleanly(monkeypatch):
    monkeypatch.setattr(
        app, "run_turn",
        lambda *a, **k: TurnResult(text="", triage=None, error="Error code: 530"))
    hist, msg, status, progress = app._respond(
        [], {"text": "chest pain", "files": []}, "e3", "Kathmandu", {})
    # Chat shows a retry prompt; status says unavailable; no crash.
    assert "couldn't reach" in hist[-1]["content"].lower() or "102" in hist[-1]["content"]
    assert "unavailable" in status.lower()
