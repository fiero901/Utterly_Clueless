from triage_state import (
    TriageState,
    assess_urgency,
    candidate_pool,
    coerce_triage,
    rank_hospitals,
)


def test_schema_defaults():
    t = TriageState(symptoms=["chest pain"])
    assert t.urgency == "stable"
    assert t.needs_ambulance is False
    assert t.call_now is False
    assert t.red_flags == []
    assert t.suspected_pathway is None


def test_coerce_normal_enums():
    assert coerce_triage({"urgency": "critical"}).urgency == "critical"
    assert coerce_triage({"urgency": "urgent"}).urgency == "urgent"
    assert coerce_triage({"urgency": "stable"}).urgency == "stable"


def test_coerce_handles_the_documented_quirk():
    # Qwen actually returned this freeform string in a live test.
    assert coerce_triage({"urgency": "Immediate — call EMS/911 now"}).urgency == "critical"


def test_coerce_nepali_and_casing():
    assert coerce_triage({"urgency": "CRITICAL"}).urgency == "critical"
    assert coerce_triage({"urgency": "गंभिर"}).urgency == "critical"


def test_coerce_none_or_garbage_defaults_stable():
    assert coerce_triage(None).urgency == "stable"
    assert coerce_triage({}).urgency == "stable"
    assert coerce_triage({"urgency": 42}).urgency == "stable"


def test_coerce_clamps_bools_and_strings():
    t = coerce_triage({"needs_ambulance": "yes", "call_now": "1", "symptoms": "chest pain"})
    assert t.needs_ambulance is True
    assert t.call_now is True
    assert t.symptoms == ["chest pain"]


def test_coerce_never_crashes_on_garbage():
    # An emergency system must NEVER raise on model garbage — fall back to a
    # safe default (stable, no ambulance). Non-dict top-level is treated as {}.
    for garbage in ([1, 2, 3], None, "chest pain", 42, ["not", "a", "dict"]):
        t = coerce_triage(garbage)
        assert isinstance(t, TriageState)
        assert t.urgency in ("urgent", "critical", "stable")


def test_red_flag_chest_pain_critical():
    t = coerce_triage({"urgency": "stable", "symptoms": ["chest pain", "sweating"]})
    a = assess_urgency(t)
    assert a.urgency == "critical"
    assert a.call_now is True
    assert a.needs_ambulance is True
    assert any("chest" in f.lower() for f in a.red_flags)


def test_unresponsive_is_critical():
    t = coerce_triage({"urgency": "stable", "symptoms": ["unresponsive"]})
    a = assess_urgency(t)
    assert a.urgency == "critical"
    assert a.call_now is True


def test_severe_breathing_is_critical_and_call_now():
    # Acute severe dyspnea is a red flag => critical + call-now (conservative,
    # medically safe default). The model's own "urgent" is overridden.
    t = coerce_triage({"urgency": "urgent", "symptoms": ["severe breathing difficulty"]})
    a = assess_urgency(t)
    assert a.urgency == "critical"
    assert a.needs_ambulance is True
    assert a.call_now is True
    assert any("breathing" in f.lower() for f in a.red_flags)


def test_minor_cut_stays_stable():
    t = coerce_triage({"urgency": "stable", "symptoms": ["small cut on hand"]})
    a = assess_urgency(t)
    assert a.urgency == "stable"
    assert a.needs_ambulance is False
    assert a.call_now is False
    assert a.red_flags == []


def test_assess_respects_existing_critical():
    t = coerce_triage({"urgency": "critical", "symptoms": ["bleeding"]})
    a = assess_urgency(t)
    assert a.urgency == "critical"
    assert a.call_now is True


def _tri(urgency="urgent"):
    return TriageState(urgency=urgency, symptoms=["chest pain"])


def test_candidate_pool_prefers_same_district_with_beds(canned_beds):
    pool = candidate_pool(canned_beds, "Kathmandu", _tri())
    names = {h["health_facility_name"] for h in pool}
    assert "Prime Teaching Hospital" not in names  # Jhapa excluded
    assert all(int(h["free_beds"]) > 0 for h in pool)


def test_candidate_pool_falls_back_when_district_empty(canned_beds):
    pool = candidate_pool(canned_beds, "Nowhere", _tri())
    assert pool  # non-empty fallback (all free-bed hospitals)


def test_rank_boosts_more_free_beds(canned_beds):
    pool = candidate_pool(canned_beds, "Kathmandu", _tri())
    ranked = rank_hospitals(pool, _tri(), "Kathmandu")
    top = ranked[0]["hospital"]["health_facility_name"]
    assert top == "Tribhuvan University Teaching Hospital"


def test_rank_returns_score_and_reason(canned_beds):
    pool = candidate_pool(canned_beds, "Kathmandu", _tri())
    ranked = rank_hospitals(pool, _tri(), "Kathmandu")
    assert ranked[0]["score"] >= ranked[-1]["score"]
    assert "reason" in ranked[0]


def test_rank_empty_pool_returns_empty():
    assert rank_hospitals([], TriageState(), "Kathmandu") == []

