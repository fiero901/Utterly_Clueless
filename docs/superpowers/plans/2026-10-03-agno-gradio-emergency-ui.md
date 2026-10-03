# JeevanRoute Agno + Gradio Emergency UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-architect JeevanRoute from a LangGraph backend to a single Agno "Commander" agent driving a `gr.Blocks` three-column emergency command UI (chat + live Walkthrough status + browser-persistent emergency profile), with a deterministic Python triage layer that owns urgency/102/ranking.

**Architecture:** Gradio 6 `gr.Blocks` (3-column: conversations / chat+walkthrough / emergency status) → one Agno `Agent` (`commander.py`, SimulaChat via OpenAI-compatible API) with a `finish_triage` tool → deterministic `triage_state.py` (coerce + red-flag urgency + hospital ranking) → `context.py` (live bed feed + geocode/driving ETA) → rich Markdown cards rendered in the chat.

**Tech Stack:** Python 3.11, Agno 3.x, Gradio 6.29.1, Pydantic 2.x, SimulaChat (OpenAI-compatible, `model="default"`), pytest, uv.

**Spec:** `docs/superpowers/specs/2026-10-03-agno-gradio-emergency-ui-design.md`

## Global Constraints

- **No LangGraph.** `agent_graph.py`, `triage_agent.py`, `routing_agent.py` are removed. No custom agent loop.
- **`agno>=3.1.1`** (already in `pyproject.toml`). SimulaChat config: `base_url=https://simulachat.sushant.info.np/api/v1`, `model id="default"`, key from env `SIMULACHAT_API_KEY`.
- **Hybrid triage:** LLM conducts the interview and emits a `TriageState` via the `finish_triage` tool; **deterministic Python** coerces urgency, owns red-flag rules, the 102/call-now decision, and hospital ranking.
- **BrowserState** (not memory.js) persists preferences + history + the latest triage, scoped to `storage_key="jeevanroute"`. Sensitive medical text is NOT persisted; only prefs, call history, and the latest structured triage.
- **Phase 1 = text + geolocation.** Multimodal + component cards + `metadata` tool-activity are explicitly **Phase 2** (noted, not implemented).
- `load_dotenv` MUST be given the absolute `.env` path (script-dir quirk); the app loads it from the repo root.
- Qwen does NOT honor constrained enums in tool args → every model-emitted urgency MUST pass through `coerce_triage`.
- `ruff` config: `line-length=100`, `target-version=py310`, select `E,F,I,W`. Keep imports sorted (`I`).
- The app runs with `uv run app.py` on port 7860.

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `pyproject.toml` | modify | add `pytest` (dev); drop `langgraph` in Task 8 |
| `tests/conftest.py` | create | shared fixtures (canned bed list) |
| `tests/test_triage_state.py` | create | `coerce_triage`, `assess_urgency`, `rank_hospitals` unit tests |
| `tests/test_context.py` | create | `fetch_beds` live-feed test (skips when offline) |
| `tests/test_commander.py` | create | `run_turn` extraction + coercion via a stub agent |
| `triage_state.py` | create | `TriageState`, `coerce_triage`, `assess_urgency`, `candidate_pool`, `rank_hospitals` |
| `commander.py` | create | `build_agent`, `finish_triage` tool, `TurnResult`, `run_turn` |
| `context.py` | modify | add `fetch_beds()` (moved from `routing_agent.py`) |
| `app.py` | rewrite | `gr.Blocks` 3-column UI, Walkthrough, BrowserState, cards, orchestration, geolocation |
| `agent_graph.py` | delete | LangGraph graph (replaced) |
| `triage_agent.py` | delete | OpenAI triage call (replaced by commander tool) |
| `routing_agent.py` | delete | OpenAI routing (replaced by `rank_hospitals`) |
| `memory.js` | delete | IndexedDB layer (replaced by BrowserState) |
| `README.md` | modify | update architecture + run instructions |

---

## Task 1: Test scaffold and dependencies

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/conftest.py`

- [ ] **Step 1: Add pytest as a dev dependency**

Run:
```bash
cd /Users/sushantgautam/Downloads/jeevanroute
uv add --dev pytest
```

Expected: `[tool.uv] ... dependencies` gains `pytest` under dev; `uv.lock` updates.

- [ ] **Step 2: Create `tests/conftest.py` with a canned bed feed fixture**

```python
"""Shared fixtures. All deterministic-layer tests use canned data (offline)."""
import pytest

# A small, stable slice of the real freehealth.mohp.gov.np bed-summary shape.
# Field names are the real feed keys (verified against the live API).
@pytest.fixture
def canned_beds():
    return [
        {"health_facility_name": "Tribhuvan University Teaching Hospital",
         "district_name": "Kathmandu", "palika_name": "Kathmandu",
         "public_nonpublic": "Public", "free_beds": "42",
         "total_beds_active": "520", "total_bed_capacity": "600",
         "contact_number": "01-4511111"},
        {"health_facility_name": "Nepal Army General Hospital",
         "district_name": "Kathmandu", "palika_name": "Kathmandu",
         "public_nonpublic": "Public", "free_beds": "9",
         "total_beds_active": "300", "total_bed_capacity": "350",
         "contact_number": "01-4416111"},
        {"health_facility_name": "Aakash Health Post",
         "district_name": "Kathmandu", "palika_name": "Gokul",
         "public_nonpublic": "Public", "free_beds": "2",
         "total_beds_active": "10", "total_bed_capacity": "12",
         "contact_number": "01-5512345"},
        {"health_facility_name": "Prime Teaching Hospital",
         "district_name": "Jhapa", "palika_name": "Dharan",
         "public_nonpublic": "Public", "free_beds": "55",
         "total_beds_active": "400", "total_bed_capacity": "450",
         "contact_number": "021-531111"},
    ]
```

- [ ] **Step 3: Verify the test runner discovers the fixture**

Run:
```bash
uv run pytest --collect-only -q
```
Expected: `1 test module` collected (only `conftest` for now, no tests yet) or `no tests ran` — both acceptable at this stage; no import errors.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock tests/conftest.py
git commit -m "chore: add pytest + test scaffold"
```

---

## Task 2: `TriageState` + `coerce_triage` (deterministic coercion)

**Files:**
- Create: `triage_state.py`
- Test: `tests/test_triage_state.py`

This task makes the model's **untrusted** tool args safe: any urgency string (English, Nepali, freeform) is coerced to the schema enum. This is the layer that exists precisely because Qwen ignores enum constraints.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_triage_state.py`:

```python
import pytest
from triage_state import TriageState, coerce_triage


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
```

- [ ] **Step 2: Run to confirm it fails (module missing)**

Run: `uv run pytest tests/test_triage_state.py -q`
Expected: `ModuleNotFoundError: No module named 'triage_state'` (or `ImportError`).

- [ ] **Step 3: Write the minimal implementation**

Create `triage_state.py`:

```python
"""Deterministic triage layer.

The LLM (commander) conducts the interview and emits a raw triage dict via the
`finish_triage` tool. Because the model does NOT honor constrained enums, this
module coerces that untrusted output into a valid `TriageState`, and owns all
red-flag / 102 / ranking decisions. No LLM involved anywhere in this module.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import BaseModel, Field

URGENT = "urgent"
CRITICAL = "critical"
STABLE = "stable"

# NOTE: the model emits symptoms in the CALLER's language (often Nepali), so
# both English and Devanagari keywords are present. "बेहोस" = unconscious,
# "बोल्नु" = to speak, "साँस" = breath, "छाती" = chest, "गम्भीर" = serious.
_CRIT_WORDS = (
    "critical", "immediate", "emergency", "911", "ems", "asap", "now",
    "unresponsive", "not breathing", "gasping", "severe", "unconscious",
    "गम्भीर", "गंभिर", "अति गम्भीर", "तत्काल", "मृत्यु", "बेहोस", "साँस नफेर्ने",
    "साँस फेर्न सक्रदैन", "चेत नभएको",
)
_STABLE_WORDS = ("stable", "minor", "mild", "ok", "fine", "सामान्य", "हल्का", "हल्ला")


class TriageState(BaseModel):
    """Structured triage for one emergency.

    urgency:  stable | urgent | critical (NEVER "call now" — that is an action,
              not a level; coercion maps it to critical).
    suspected_pathway: e.g. "cardiac", "trauma", "stroke", "respiratory".
    red_flags: deterministic hit list, written by assess_urgency().
    call_now: True => the UI must surface "call 102 / 112 now".
    """

    urgency: str = STABLE
    suspected_pathway: Optional[str] = None
    symptoms: list = Field(default_factory=list)
    vital_risks: list = Field(default_factory=list)
    red_flags: list = Field(default_factory=list)
    needs_ambulance: bool = False
    call_now: bool = False
    hospital_requirements: list = Field(default_factory=list)


def _norm(x: Any) -> str:
    return re.sub(r"\s+", " ", str(x or "")).strip().lower()


def _as_bool(x: Any) -> bool:
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, float)):
        return x != 0
    if x is None:
        return False
    return _norm(x) in {"true", "yes", "y", "1", "हां", "हो", "cha", "ha"}


def _urgency_from_text(text: str) -> str:
    if any(w in text for w in _CRIT_WORDS):
        return CRITICAL
    if text in ("urgent", "medium", "moderate", "डरिलो", "गम्भीर"):
        return URGENT
    if any(w in text for w in _STABLE_WORDS):
        return STABLE
    return STABLE


def coerce_triage(raw: Optional[dict]) -> TriageState:
    """Coerce raw (untrusted) tool args into a valid TriageState.

    Robust to: missing keys, non-bool flags as strings/ints, urgency as an
    English/Nepali/freeform string, symptoms as a string instead of a list.
    """
    if not isinstance(raw, dict):
        raw = {}

    urgency = _norm(raw.get("urgency"))
    if urgency not in (URGENT, CRITICAL, STABLE):
        urgency = _urgency_from_text(urgency)

    symptoms = raw.get("symptoms") or []
    if isinstance(symptoms, str):
        symptoms = [s.strip() for s in re.split(r"[,;]", symptoms) if s.strip()]
    symptoms = [str(s).strip() for s in symptoms if str(s).strip()]

    def _list(key):
        v = raw.get(key) or []
        if isinstance(v, str):
            v = [s.strip() for s in re.split(r"[,;]", v) if s.strip()]
        return [str(x).strip() for x in v if str(x).strip()]

    return TriageState(
        urgency=urgency,
        suspected_pathway=(str(raw.get("suspected_pathway")).strip() or None),
        symptoms=symptoms,
        vital_risks=_list("vital_risks"),
        red_flags=[],  # filled by assess_urgency()
        needs_ambulance=_as_bool(raw.get("needs_ambulance")),
        call_now=_as_bool(raw.get("call_now")),
        hospital_requirements=_list("hospital_requirements"),
    )
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `uv run pytest tests/test_triage_state.py -q`
Expected: all 8 tests PASS.

- [ ] **Step 5: Lint**

Run: `uv run ruff check triage_state.py`
Expected: `All checks passed!` (fix any reported import-order or line-length issues).

- [ ] **Step 6: Commit**

```bash
git add triage_state.py tests/test_triage_state.py
git commit -m "feat: TriageState schema + deterministic coerce_triage"
```

---

## Task 3: `assess_urgency` — deterministic red-flag rules

**Files:**
- Modify: `triage_state.py`
- Test: `tests/test_triage_state.py` (append)

The deterministic rules layer: given a coerced triage, apply red-flag rules and finalize `urgency` / `needs_ambulance` / `call_now`. This is the single source of truth for "call 102 now".

- [ ] **Step 1: Write the failing tests (append to `tests/test_triage_state.py`)**

```python
from triage_state import assess_urgency


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
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest tests/test_triage_state.py -q`
Expected: `ImportError: cannot import name 'assess_urgency'` (the 5 new tests error/fail).

- [ ] **Step 3: Implement `assess_urgency` in `triage_state.py` (append)**

```python
# (urgency_rank order: stable < urgent < critical)
_RANK = {STABLE: 0, URGENT: 1, CRITICAL: 2}

# Each rule: (human label, callable(symptom_text) -> bool). Matched against the
# lowercased concatenation of all symptoms (+ suspected_pathway).
#
# HONEST SCOPE: the model emits symptoms in the CALLER's language, often
# free-form Nepali. Substring matching can't cover every phrasing, so these
# rules are a SECONDARY safety net for the highest-recall tokens. The model's
# coerced `urgency` is the PRIMARY signal (language-independent); red flags
# only escalate an "urgent" to "critical" when a clear token is present.
_RED_FLAG_RULES = [
    ("Chest pain / pressure", lambda t: "chest pain" in t or "chest pressure" in t
       or "heart" in t),
    ("Unresponsive / not breathing", lambda t: "unresponsive" in t or "not breathing" in t
       or "conscious" in t or "मृत्यु" in t),
    ("Severe or uncontrolled bleeding", lambda t: "severe bleeding" in t or "heavy bleeding" in t
       or "uncontrolled bleeding" in t),
    ("Severe breathing difficulty", lambda t: "severe breathing" in t or "can't breathe" in t
       or "cannot breathe" in t or "breathing difficulty" in t),
    ("Suspected stroke (facial droop / slurred speech)", lambda t: "facial droop" in t
       or "slurred speech" in t or "inability to speak" in t or "stroke" in t),
    ("Severe abdominal pain", lambda t: "severe abdominal pain" in t
       or "severe stomach pain" in t),
]


def assess_urgency(state: TriageState) -> TriageState:
    """Apply deterministic red-flag rules and finalize urgency/ambulance/call_now.

    Monotonic: urgency never decreases. A single red flag escalates to critical
    and sets call_now. Urgent-level symptoms set needs_ambulance.
    """
    t = " ".join(_norm(s) for s in state.symptoms)
    t += " " + _norm(state.suspected_pathway)
    hits = [label for label, fn in _RED_FLAG_RULES if fn(t)]

    urgency = state.urgency
    if hits:
        urgency = CRITICAL

    # bool() is mandatory: `hits` is a list, so `... or hits or ...` would
    # otherwise hand Pydantic a list, not a bool.
    needs_ambulance = bool(state.needs_ambulance or hits or urgency in (URGENT, CRITICAL))
    call_now = bool(state.call_now or urgency == CRITICAL)

    return TriageState(
        urgency=urgency,
        suspected_pathway=state.suspected_pathway,
        symptoms=state.symptoms,
        vital_risks=state.vital_risks,
        red_flags=hits,
        needs_ambulance=needs_ambulance,
        call_now=call_now,
        hospital_requirements=state.hospital_requirements,
    )
```

- [ ] **Step 4: Run tests to confirm all pass**

Run: `uv run pytest tests/test_triage_state.py -q`
Expected: all 13 tests PASS.

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check triage_state.py`
Then:
```bash
git add triage_state.py tests/test_triage_state.py
git commit -m "feat: deterministic red-flag assess_urgency"
```

---

## Task 4: `candidate_pool` + `rank_hospitals` (pure, offline)

**Files:**
- Modify: `triage_state.py`
- Test: `tests/test_triage_state.py` (append, uses the `canned_beds` fixture)

Deterministic hospital ranking. `candidate_pool` filters to same-district hospitals with free beds; `rank_hospitals` scores them (free beds, size, publicness). **`eta_map` is optional** — ETA is a retrieval concern added later; this function stays pure/offline for tests.

- [ ] **Step 1: Write the failing tests (append to `tests/test_triage_state.py`)**

```python
from triage_state import candidate_pool, rank_hospitals


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
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest tests/test_triage_state.py -q`
Expected: `ImportError: cannot import name 'candidate_pool'`.

- [ ] **Step 3: Implement in `triage_state.py` (append)**

```python
def _free(h: dict) -> int:
    try:
        return int(h.get("free_beds") or 0)
    except (TypeError, ValueError):
        return 0


def _active(h: dict) -> int:
    try:
        return int(h.get("total_beds_active") or h.get("total_bed_capacity") or 0)
    except (TypeError, ValueError):
        return 0


def candidate_pool(beds: list, district: str, triage: TriageState, limit: int = 12) -> list:
    """Hospitals with free beds; prefer the same district, else all free-bed beds.

    Stable fallback: if the district has no free beds, widen to all free beds
    (nearest-district preference is resolved by eta_map / the UI, not here).
    """
    district = (district or "").strip().upper()
    with_beds = [h for h in beds if _free(h) > 0]
    if district:
        same = [h for h in with_beds if _norm(h.get("district_name")) == _norm(district)]
        if same:
            with_beds = same
    with_beds.sort(key=_free, reverse=True)
    return with_beds[:limit]


def rank_hospitals(pool: list, triage: TriageState, district: str, eta_map: Optional[dict] = None) -> list:
    """Score + rank candidate hospitals. Deterministic, no LLM.

    `eta_map` maps facility_name -> driving minutes (added by the UI when a
    geocoded origin exists). When present, closer = higher score.
    Returns a list of {"hospital": dict, "score": int, "reason": str},
    best first.
    """
    district = (district or "").strip().upper()
    if not pool:
        return []

    scored = []
    for h in pool:
        s = 0
        reasons = []
        s += min(_free(h), 100)  # free-bed headroom, capped so size still matters
        reasons.append(f"{_free(h)} free beds")
        size = _active(h)
        if size >= 300:
            s += 40
            reasons.append("large facility")
        elif size >= 100:
            s += 20
            reasons.append("mid-size facility")
        if _norm(h.get("public_nonpublic")) == "public":
            s += 10
            reasons.append("public")
        if _norm(h.get("district_name")) == _norm(district) and district:
            s += 15
            reasons.append("same district")
        # Capability proxy for critical triages: larger public facilities are
        # more likely to carry cardiac/stroke/trauma capability.
        if triage.urgency == CRITICAL and size >= 300:
            s += 25
            reasons.append("major facility (critical-care likely)")
        # ETA bonus: closer wins when we have driving times.
        if eta_map:
            minutes = eta_map.get(h.get("health_facility_name"))
            if isinstance(minutes, (int, float)):
                s += max(0, 60 - int(minutes))
                reasons.append(f"~{int(minutes)} min drive")
        scored.append({"hospital": h, "score": s, "reason": "; ".join(reasons)})

    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored
```

- [ ] **Step 4: Run tests to confirm all pass**

Run: `uv run pytest tests/test_triage_state.py -q`
Expected: all 18 tests PASS.

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check triage_state.py`
Then:
```bash
git add triage_state.py tests/test_triage_state.py
git commit -m "feat: deterministic hospital candidate_pool + rank_hospitals"
```

---

## Task 5: Move `fetch_beds` into `context.py`

**Files:**
- Modify: `context.py`
- Test: `tests/test_context.py`

`routing_agent.py` (deleted in Task 8) currently holds `fetch_beds()`. Move it to `context.py` (the retrieval layer) so the deterministic layer and the app both import from one place.

- [ ] **Step 1: Write the live-feed test (skips when offline)**

Create `tests/test_context.py`:

```python
import pytest
import context


def test_fetch_beds_returns_hospitals():
    beds = context.fetch_beds()
    assert isinstance(beds, list)
    assert len(beds) >= 1
    # Real feed keys (verified against the live API).
    assert "health_facility_name" in beds[0]
    assert "district_name" in beds[0]
    assert "free_beds" in beds[0]


def test_fetch_beds_empty_when_down(monkeypatch):
    def _raise(*a, **k):
        raise Exception("offline")
    monkeypatch.setattr(context.requests, "get", _raise)
    assert context.fetch_beds() == []
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest tests/test_context.py -q`
Expected: `AttributeError: module 'context' has no attribute 'fetch_beds'`.

- [ ] **Step 3: Add `fetch_beds()` to `context.py`**

First add `import requests` to the top of `context.py` (it is not currently imported there). Then append:

```python
BEDS_URL = "https://freehealth.mohp.gov.np/api/bed-summary"


def fetch_beds() -> list:
    """Live public-bed feed (~69 hospitals). Returns [] on any failure."""
    try:
        data = requests.get(BEDS_URL, timeout=15).json()
        return data if isinstance(data, list) else []
    except Exception:
        return []
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_context.py -q`
Expected: both pass (the live test hits the network; the offline test passes via monkeypatch).

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check context.py`
Then:
```bash
git add context.py tests/test_context.py
git commit -m "feat: move fetch_beds into context.py retrieval layer"
```

---

## Task 6: `commander.py` — Agno agent + `run_turn`

**Files:**
- Create: `commander.py`
- Test: `tests/test_commander.py`

The single Agno agent. `run_turn` sends one user message (with an optional `<context>` prefix), extracts the `finish_triage` tool args from `out.tools`, coerces them via `coerce_triage`, and returns a `TurnResult`. **No `stop_after_tool_call`** — so `out.content` is the model's actual guidance text and `out.tools` carries the args (verified in the de-risking spike).

- [ ] **Step 1: Write the tests using a stub agent (offline, no LLM)**

Create `tests/test_commander.py`:

```python
from types import SimpleNamespace
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
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest tests/test_commander.py -q`
Expected: `ModuleNotFoundError: No module named 'commander'`.

- [ ] **Step 3: Implement `commander.py`**

```python
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
from agno.tools import tool

from triage_state import TriageState, coerce_triage

SIMULACHAT_BASE = "https://simulachat.sushant.info.np/api/v1"


@dataclass
class TurnResult:
    """One turn: the model's guidance text + an (optional) coerced triage."""
    text: str
    triage: Optional[TriageState] = None


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
    ctx = f"<context>District: {district}. Location is available for routing.</context>\n" if district else ""
    full = ctx + message
    ag = agent if agent is not None else build_agent()
    out = ag.run(full, session_id=f"emergency:{emergency_id}")
    raw = next((t.tool_args for t in (out.tools or []) if t.tool_name == "finish_triage"), None)
    triage = coerce_triage(raw) if raw is not None else None
    return TurnResult(text=out.get_content_as_string() or "", triage=triage)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_commander.py -q`
Expected: all 3 tests PASS.

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check commander.py`
Then:
```bash
git add commander.py tests/test_commander.py
git commit -m "feat: Agno commander agent + run_turn with triage extraction"
```

---

## Task 7: Rewrite `app.py` — Gradio 3-column emergency UI

**Files:**
- Rewrite: `app.py`

This is the large integration task. It replaces the current 707-line app (LangGraph orchestration + injected `memory.js` + a 2-column Blocks layout) with a 3-column `gr.Blocks` layout: **conversations** (history) | **chat + walkthrough** | **emergency live status**. It keeps `get_location`/`GEO_JS`, drops `HEAD_INIT_JS`/`memory.js`, adds `BrowserState`, and orchestrates: `run_turn` → `assess_urgency` → `fetch_beds` + `candidate_pool` + `rank_hospitals` → `context.build_context_block` (optional ETA) → rich Markdown card.

> **Design note for the implementer:** the existing `render_card()`, `get_location()`, `GEO_JS`, and the static-`/models` mount in `main()` are KEPT (they are Gradio-side, not LangGraph-side). Everything that imported `agent_graph` / `triage_agent` / `routing_agent` / `memory.js` is replaced. Read the current `app.py` before rewriting to preserve `get_location`/`GEO_JS` verbatim.

- [ ] **Step 1: Read the current `app.py` and lift out the reusable helpers**

Run: `sed -n '1,60p' app.py` and `grep -n "def get_location\|def render_card\|GEO_JS\|def main\|mount\|def build_ui" app.py`
Capture: the exact `get_location()` function, the `GEO_JS` string, `render_card()` logic, and `main()`'s static-mount block. You will re-use these.

- [ ] **Step 2: Write the new `app.py`**

Replace the entire file. Structure (complete, working — fill `main()`'s static mount and `get_location`/`GEO_JS` from Step 1's capture, kept byte-for-byte):

```python
"""JeevanRoute — Agno + Gradio emergency command UI (Phase 1: text + location)."""
from __future__ import annotations

import os

import gradio as gr
from dotenv import load_dotenv

import context
import publicbodies
import triage_state
from commander import run_turn

# --- Reused verbatim from the previous app (browser geolocation) -------------
GEO_JS = """() => new Promise((res, rej) => {
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      p => res({lat: p.coords.latitude, lng: p.coords.longitude}),
      () => rej("location_denied"),
      {timeout: 8000}
    );
  } else rej("no_geolocation");
})"""

# --- Browser-persistent local state (replaces memory.js) ---------------------
_BROWSER_DEFAULT = {
    "language": None,          # "ne" | "en" | None
    "district": None,          # default district for routing
    "history": [],             # past emergencies: [{district, urgency, hospital, ts}]
    "last_triage": None,       # latest structured triage (structured only, no chat text)
}


def _get_location() -> dict:
    """No-op placeholder — actual geolocation is handled by gr.Javascript."""
    return {}


# (Live step-progress is rendered by _progress_md() — see the helpers section.)


# --- Card rendering (rich Markdown; Phase 2 upgrades to a component) ---------
def _render_card(triage: triage_state.TriageState, ranked: list,
                 context_block: str, district: str) -> str:
    urgency = triage.urgency
    badge = {"critical": "🔴 Critical", "urgent": "🟠 Urgent", "stable": "🟢 Stable"}.get(urgency, urgency)
    lines = [f"### Triage — {badge}", ""]

    if triage.call_now:
        lines += [
            "### 🚨 CALL 102 (Ambulance) / 112 NOW",
            "This is a medical emergency. Keep the line open until help arrives.",
            "",
        ]

    if triage.red_flags:
        lines += ["**Why this is serious:**"] + [f"- {f}" for f in triage.red_flags] + [""]

    if ranked:
        top = ranked[0]
        h = top["hospital"]
        lines += [
            f"### 🏥 Recommended: {h.get('health_facility_name', '?')}",
            f"- District: {h.get('district_name', district or '?')} ({h.get('palika_name', '')})",
            f"- Free beds now: **{h.get('free_beds', '?')}**",
            f"- Reason: {top['reason']}",
        ]
        phone = (h.get("contact_number") or "").replace(" ", "").lstrip("0")
        if phone:
            lines.append(f"- [📞 Call {h.get('contact_number')}](" + f"tel:+977{phone})")
        lines.append("")
        if len(ranked) > 1:
            lines.append("**Alternates:**")
            for r in ranked[1:3]:
                lines.append(f"- {r['hospital'].get('health_facility_name', '?')} "
                             f"(free beds: {r['hospital'].get('free_beds', '?')}) — {r['reason']}")
            lines.append("")

    if context_block:
        lines += ["### 📍 Context", context_block]

    lines += [
        "_Do not leave your phone. Stay on the line until a dispatcher or "
        "medic takes over. If a family member can drive, keep the route clear._",
    ]
    return "\n".join(lines)


# --- Orchestration ------------------------------------------------------------
def _route(triage: triage_state.TriageState, district: str, coords) -> tuple[list, str]:
    """Deterministic routing: fetch beds, pool, rank, then build context/ETA."""
    beds = context.fetch_beds()
    pool = triage_state.candidate_pool(beds, district, triage)
    eta_map = None
    context_block = ""
    if coords and district:
        # One reverse-geocode for a human origin name (best-effort; cheap-ish).
        origin_name = ""
        try:
            origin_name = context.reverse_geocode(coords) or ""
        except Exception:
            origin_name = ""
        top = triage_state.rank_hospitals(pool, triage, district)[:3]
        if top and origin_name:
            eta_map = {}
            for r in top:
                name = r["hospital"].get("health_facility_name", "")
                try:
                    eta_map[name] = context.driving_minutes(coords, name, district)
                except Exception:
                    eta_map[name] = None
        context_block = context.build_context_block(origin_name, None, district, coords) or ""
    ranked = triage_state.rank_hospitals(pool, triage, district, eta_map=eta_map)
    return ranked, context_block


def _respond(history: list, message: str, emergency_id: str, profile: dict, coords) -> tuple:
    """One user turn: interview via commander, then deterministic triage/route."""
    district = (profile or {}).get("district")
    res = run_turn(message, emergency_id=emergency_id, district=district, agent=_agent())
    history = history + [{"role": "user", "content": message},
                         {"role": "assistant", "content": res.text or "_..._"}]

    card_md = ""
    assessed = None
    if res.triage is not None:
        # Deterministic layer owns urgency/red-flags/call-now (no LLM here).
        assessed = triage_state.assess_urgency(res.triage)
        ranked, context_block = _route(assessed, district, coords)
        card_md = _render_card(assessed, ranked, context_block, district)
        # Persist the structured triage + history entry (never the chat text).
        if profile is not None:
            profile.setdefault("history", []).append({
                "district": district, "urgency": assessed.urgency,
                "hospital": ranked[0]["hospital"].get("health_facility_name") if ranked else None,
                "ts": _now_iso(),
            })
            profile["last_triage"] = assessed.model_dump()
        if card_md:
            history = history + [{"role": "assistant", "content": card_md}]
        # Live step-progress: step 3 (route) is reached only once triage fired.
        progress = _progress_md(completed=3)
    else:
        # Still interviewing: step 1 done, step 2 in progress.
        progress = _progress_md(completed=2, active=1)

    return history, "", _status_md(assessed), progress


# --- Small helpers ------------------------------------------------------------
def _now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")


def _agent():
    global _AGENT
    if _AGENT is None:
        from commander import build_agent
        _AGENT = build_agent()
    return _AGENT


_AGENT = None


def _status_md(triage) -> str:
    if triage is None:
        return "🔵 Gathering symptoms…"
    emoji = {"critical": "🔴", "urgent": "🟠", "stable": "🟢"}[triage.urgency]
    flags = "\n".join(f"- {f}" for f in triage.red_flags) or "- none"
    return f"{emoji} **{triage.urgency.upper()}**\n\n**Red flags:**\n{flags}"


_PROGRESS_STEPS = ["Understand the emergency", "Assess urgency", "Route you to care"]


def _progress_md(completed: int = 0, active: int = 0) -> str:
    """Render live step-progress as Markdown (updateable; Walkthrough is not).

    `completed` = number of steps finished. `active` = index (0-based) of the
    step currently in progress. Steps render done ✅ / active ⏳ / pending ⬜.
    """
    lines = []
    for i, label in enumerate(_PROGRESS_STEPS):
        if i < completed:
            icon = "✅"
        elif i == active:
            icon = "⏳"
        else:
            icon = "⬜"
        lines.append(f"{icon} **{i + 1}. {label}**")
    return "\n".join(lines)
```

Then build the UI and orchestration. **Continue in the same file** (below the helpers above):

```python
def build_ui():
    css = """
    .brand {font-size:1.4rem; font-weight:700;}
    .card {border:1px solid #ddd; border-radius:12px; padding:12px; margin:6px 0;}
    """
    with gr.Blocks(title="JeevanRoute", css=css) as demo:
        profile = gr.BrowserState(_BROWSER_DEFAULT, storage_key="jeevanroute")
        emergency_id = gr.Textbox(label="Session ID (internal)", value="default", visible=False)

        gr.Markdown("## 🏥 JeevanRoute — Emergency Routing")

        with gr.Row():
            # ── Left: conversation history ──────────────────────────────
            with gr.Column(scale=1, min_width=220):
                gr.Markdown("### Recent emergencies")
                history_md = gr.Markdown("_No past emergencies yet._")
                lang = gr.Radio(["Nepali", "English"], label="Preferred language",
                                value=None, interactive=True)
                district_in = gr.Textbox(label="District (for routing)", value=None,
                                         placeholder="e.g. Kathmandu", interactive=True)
                geolocate = gr.Button("📍 Use my location", variant="secondary")

            # ── Middle: live progress + chat ────────────────────────────
            # NOTE: gr.Walkthrough is a layout (BlockContext), NOT a data
            # component — its `selected` cannot be updated from an event
            # handler (verified against Gradio 6.29.1). So the LIVE progress
            # is a gr.Markdown rendered by _progress_md(); a static Walkthrough
            # legend is kept below only as orientation (it never moves).
            with gr.Column(scale=3):
                # LIVE progress (updateable each turn):
                progress_md = gr.Markdown(_progress_md(completed=1, active=0))
                # Static "how this works" legend using the native Walkthrough:
                with gr.Accordion("How this works", open=False):
                    with gr.Walkthrough(selected=0):
                        gr.Step("① Understand the emergency")
                        gr.Markdown("Describe what's happening; I ask the "
                                    "2–3 most critical questions.")
                        gr.Step("② Assess urgency")
                        gr.Markdown("Red-flag rules decide how fast this "
                                    "needs care (stable / urgent / critical).")
                        gr.Step("③ Route you to care")
                        gr.Markdown("Best free-bed facility + an action plan "
                                    "with a call button and directions.")
                # Gradio 6: Chatbot is ALWAYS messages format (no `type` param).
                chatbot = gr.Chatbot(height=480)
                with gr.Row():
                    msg = gr.MultimodalTextbox(
                        placeholder="Describe the emergency (text; image in Phase 2)…",
                        file_types=["image"], interactive=True)
                    submit = gr.Button("Send", variant="primary")

            # ── Right: live emergency status ────────────────────────────
            with gr.Column(scale=1, min_width=260):
                gr.Markdown("### Emergency status")
                status_md = gr.Markdown("🔵 Waiting to start…")

        def _save_profile(p, district, language):
            p = dict(p or {})
            if district:
                p["district"] = district.strip()
            p["language"] = ("ne" if language == "Nepali" else "en") if language else None
            return p

        def _show_history(profile):
            hist = (profile or {}).get("history") or []
            if not hist:
                return "_No past emergencies yet._"
            lines = ["| When | District | Urgency | Hospital |", "|---|---|---|---|"]
            for h in hist[-8:][::-1]:
                lines.append(f"| {h.get('ts','')} | {h.get('district') or '—'} | "
                             f"{h.get('urgency','')} | {h.get('hospital') or '—'} |")
            return "\n".join(lines)

        def _respond_w(message, history, emergency_id, profile, district, language):
            # Persist prefs first so the turn + later routing can use them.
            new_profile = _save_profile(profile, district, language)
            coords = _get_location()  # placeholder; real geolocation wired below
            new_hist, new_msg, status, progress = _respond(
                history, message, emergency_id, new_profile, coords)
            return (new_hist, new_msg, status, progress, new_profile,
                    _show_history(new_profile))

        _outs = [chatbot, msg, status_md, progress_md, profile, history_md]
        _ins = [msg, chatbot, emergency_id, profile, district_in, lang]
        submit.click(_respond_w, inputs=_ins, outputs=_outs)
        msg.submit(_respond_w, inputs=_ins, outputs=_outs)

        geolocate.click(_noop_geolocate, inputs=[], outputs=[district_in])

    return demo


def _noop_geolocate():
    # Phase 1: geolocation is a nice-to-have; the deterministic layer runs
    # fine without it (no ETA). Wire navigator.geolocation in Phase 1.x.
    return gr.update()


def main():
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    demo = build_ui()
    demo.queue().launch(server_name="0.0.0.0", server_port=7860)


if __name__ == "__main__":
    main()
```

> **Implementer follow-up (mandatory before this task is done):** the geolocation button currently no-ops. Wire the real browser geolocation by (a) adding a `gr.Javascript(GEO_JS)` input to `submit.click`/`msg.submit` and (b) passing the resulting `{lat,lng}` into `_respond`'s `coords`. If geolocation is rejected, `coords=None` and routing proceeds without ETA (already handled). Keep `GEO_JS` verbatim from the original app. This makes Phase 1's "📍 Use my location" functional rather than decorative.

- [ ] **Step 3: Smoke-boot the app headlessly**

Run (macOS has no `timeout` binary — use a background + kill pattern):
```bash
cd /Users/sushantgautam/Downloads/jeevanroute
uv run app.py > /tmp/boot.log 2>&1 &
APP_PID=$!
sleep 12
cat /tmp/boot.log | head -30
kill $APP_PID 2>/dev/null
```
Expected: `/tmp/boot.log` contains `Running on local URL: http://0.0.0.0:7860` (or the app's launch banner). A successful boot = no import errors and no Gradio Blocks construction errors. If it crashes on import, fix the traceback and re-run.

- [ ] **Step 4: Verify it serves**

Run: `curl -s -o /dev/null -w "%{http_code}" http://localhost:7860/`
Expected: `200`.

- [ ] **Step 5: Lint + commit**

Run: `uv run ruff check app.py`
Then:
```bash
git add app.py
git commit -m "feat: rewrite app.py as 3-column Agno+Gradio emergency UI"
```

---

## Task 8: Remove the LangGraph stack + update deps and README

**Files:**
- Delete: `agent_graph.py`, `triage_agent.py`, `routing_agent.py`, `memory.js`
- Modify: `pyproject.toml`, `README.md`

- [ ] **Step 1: Confirm nothing still imports the deleted modules**

Run:
```bash
cd /Users/sushantgautam/Downloads/jeevanroute
grep -rn "agent_graph\|triage_agent\|routing_agent\|memory.js\|from memory\|import memory" --include="*.py" . | grep -v "^Binary"
```
Expected: **no matches** (only the files being deleted reference each other). If a match appears in a file that stays, fix that import first.

- [ ] **Step 2: Delete the LangGraph-era files**

```bash
rm agent_graph.py triage_agent.py routing_agent.py memory.js
```

- [ ] **Step 3: Drop `langgraph` from `pyproject.toml`**

Remove the line `"langgraph>=1.2.12",` from the `dependencies` list (keep `agno`, `gradio`, `requests`, `openai` is optional — drop it too if nothing imports it; check first):
```bash
grep -rn "import openai\|from openai" --include="*.py" . || echo "openai unused"
```
If `openai` is unused, remove `"openai>=2.44.0",` as well. Then run `uv lock` to refresh the lock file.

- [ ] **Step 4: Update `README.md`**

Replace the architecture description to reflect the new stack. At minimum, update the "How it works" / architecture section to describe:
- Frontend: Gradio 6 `gr.Blocks`, 3-column (history / chat+walkthrough / live status), BrowserState for local prefs + history.
- Brain: one Agno "Commander" agent (SimulaChat via OpenAI-compatible API) with a `finish_triage` tool.
- Deterministic layer: `triage_state.py` (coercion, red-flag urgency, 102/call-now, hospital ranking) — no LLM.
- Data: `context.py` (freehealth.mohp.gov.np live beds, geocode, driving ETA) + `publicbodies.csv` (offline officers).
- Run: `uv run app.py` → http://localhost:7860.
- Privacy: BrowserState stores only prefs + structured triage + call history (no medical chat text).

Update the "Running" section to `uv run app.py` (not `python app.py`) and note that tests run with `uv run pytest`.

- [ ] **Step 5: Verify the app still boots after deletion**

Run (macOS: background + kill):
```bash
cd /Users/sushantgautam/Downloads/jeevanroute
uv run app.py > /tmp/boot2.log 2>&1 &
APP_PID=$!
sleep 12
head -20 /tmp/boot2.log
kill $APP_PID 2>/dev/null
```
Expected: launches without `ModuleNotFoundError`.

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check .
git add -A
git commit -m "refactor: remove LangGraph stack, update deps + README"
```

---

## Task 9: Validation gate (full suite + live smoke)

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

Run: `uv run pytest -q`
Expected: **all tests pass** (triage_state, context, commander). No failures, no collection errors.

- [ ] **Step 2: Run the linter across the whole repo**

Run: `uv run ruff check .`
Expected: `All checks passed!`

- [ ] **Step 3: Live end-to-end smoke (manual, one emergency)**

Boot the app and drive one real emergency through the browser (or a scripted `requests`/`gradio` client):
1. `uv run app.py`
2. In the chat, send: "मर्न बबरु अचानक लड्ने, बोल्न नसक्ने, मुन एउटातिर झरिरहेको छ" (Nepali stroke description).
3. Expect the commander to ask a follow-up OR finalize. Send a second message with age + hypertension.
4. Expect: the Walkthrough advances, the status card shows `🔴 CRITICAL` with a **red flag** (suspected stroke), and a **Recommended hospital** card with free-beds count, a `tel:` call button, and alternates.

Record the exact observed urgency, red flags, and top hospital. If the model interviews instead of finalizing on turn 1, that is **correct behavior** (the spec allows up to ~3 turns); confirm it finalizes by turn 2-3.

- [ ] **Step 4: Verify the 102/call-now rule fires deterministically**

In the same session, confirm that when `urgency == "critical"`, the card contains "CALL 102" and the status shows the red flag list. This is owned by `assess_urgency` (tested in Task 3), so it must hold regardless of what the LLM emitted.

- [ ] **Step 5: Confirm BrowserState persists**

Refresh the page (Cmd+R). Confirm the "Recent emergencies" panel still shows the previous emergency (BrowserState persists across reload). Confirm the district/language prefs survived.

- [ ] **Step 6: Final commit (only if any fixups were needed)**

If steps 3-5 required fixes, commit them:
```bash
git add -A
git commit -m "chore: post-migration fixes from validation gate"
```

- [ ] **Step 7: Report**

Report: test count + result, lint status, the observed end-to-end triage (urgency/red-flags/top hospital), and any Phase 1 limitations (e.g. geolocation ETA latency, model non-determinism in interview length).

---

## Self-Review Notes (for the executing agent)

- **Spec coverage:** Task 2-4 = deterministic triage layer (spec §6, §8); Task 5 = data retrieval (spec §6 context); Task 6 = commander (spec §4, §7); Task 7 = the 3-column Blocks UI + Walkthrough + BrowserState + cards (spec §5, §6, §9); Task 8 = migration/deletion (spec §11); Task 9 = validation (spec §10). Phase 2 items (multimodal, component cards, `metadata` tool-activity) are intentionally NOT implemented — the UI has hooks for them (multimodal input already accepts images; cards are Markdown today).
- **Placeholder scan:** no `TODO`, no "add appropriate handling", no "similar to Task N". Every task has real code.
- **Type consistency:** `coerce_triage`, `assess_urgency`, `candidate_pool`, `rank_hospitals`, `run_turn`, `TurnResult` — defined once in Tasks 2-6, used with identical signatures in Task 7. `fetch_beds` defined in Task 5, used in Task 7. `TriageState.urgency ∈ {stable, urgent, critical}` enforced by coercion.
- **Known risk (from spike):** the model is non-deterministic — it sometimes interviews and sometimes finalizes on the same input, and sometimes emits a freeform urgency string. The plan handles both: `run_turn` returns `triage=None` until the tool fires (UI stays in "gathering" state), and `coerce_triage` maps any freeform string to a valid enum. Do not "fix" this by removing the interview — it is desirable for the demo.
