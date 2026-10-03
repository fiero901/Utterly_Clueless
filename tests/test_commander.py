from commander import TurnResult, run_turn


class _FakeToolExecution:
    def __init__(self, name, args):
        self.tool_name = name
        self.tool_args = args


class _FakeRunOutput:
    def __init__(self, content, tools):
        self._content = content
        self._tools = tools

    def get_content_as_string(self):
        return self._content

    @property
    def tools(self):
        return self._tools


class _StubAgent:
    """Mimics agno Agent.run(): returns a canned RunOutput, records session_id."""
    def __init__(self, content, tools):
        self._content = content
        self._tools = tools
        self.last_session_id = None

    def run(self, message, session_id=None, **kwargs):
        self.last_session_id = session_id
        return _FakeRunOutput(self._content, self._tools)


def test_run_turn_extracts_and_coerces_triage():
    agent = _StubAgent(
        "कृपय 102 डायल गरनुहोस्।",
        [_FakeToolExecution("finish_triage",
                            {"urgency": "Immediate — call EMS/911 now",
                             "suspected_pathway": "cardiac",
                             "symptoms": ["chest pain"],
                             "needs_ambulance": True})],
    )
    res = run_turn("chest pain", emergency_id="e42", district="Kathmandu", agent=agent)
    assert isinstance(res, TurnResult)
    assert res.text.startswith("कृपय")
    assert res.triage is not None
    assert res.triage.urgency == "critical"  # coerced from the freeform string
    assert res.triage.needs_ambulance is True
    assert agent.last_session_id == "emergency:e42"


def test_run_turn_no_triage_when_tool_not_called():
    agent = _StubAgent("कुनै लक्षण? कतै खाना खाएर आउनुभयो?", [])
    res = run_turn("मलाई अरुखाले छ", agent=agent)
    assert res.triage is None
    assert res.text.startswith("कुनै")


def test_run_turn_coerces_bad_garbage_args_to_stable():
    agent = _StubAgent(
        "ok",
        [_FakeToolExecution("finish_triage", {"urgency": 123, "symptoms": "headache"})],
    )
    res = run_turn("headache", agent=agent)
    assert res.triage is not None
    assert res.triage.urgency == "stable"


class _RaisingAgent:
    """Mimics an API failure (e.g. SimulaChat Cloudflare 530)."""
    def run(self, message, session_id=None, **kwargs):
        raise RuntimeError("Error code: 530 — Cloudflare tunnel error")


def test_run_turn_surfaces_error_instead_of_raising():
    # An emergency UI must degrade gracefully: a backend failure becomes a
    # TurnResult.error the UI can show as "try again", never a stack trace.
    res = run_turn("chest pain", agent=_RaisingAgent())
    assert res.text == ""
    assert res.triage is None
    assert res.error is not None
    assert "530" in res.error

