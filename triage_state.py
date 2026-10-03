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


def rank_hospitals(pool: list, triage: TriageState, district: str,
                   eta_map: Optional[dict] = None) -> list:
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

