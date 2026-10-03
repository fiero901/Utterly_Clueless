"""JeevanRoute — Routing Agent.

Takes the structured triage state + a district, queries the LIVE public
freehealth.mohp.gov.np bed data, and recommends the best hospital.

Data source (public, no auth):
    GET https://freehealth.mohp.gov.np/api/bed-summary
    -> 69 hospitals: name, district, free_beds, capacity, contact, ...

The bed feed has no capability flags (CT/ICU/...), so the LLM picks the best
match from the candidate list using the triage `requirements` and produces a
clean recommendation block.
"""
import os
import json

import requests
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

_API_KEY = os.environ.get("SIMULACHAT_API_KEY")
if not _API_KEY:
    raise RuntimeError("SIMULACHAT_API_KEY is not set. Copy .env.example to .env.")

client = OpenAI(
    base_url="https://simulachat.sushant.info.np/api/v1",
    api_key=_API_KEY,
)

BEDS_URL = "https://freehealth.mohp.gov.np/api/bed-summary"


def fetch_beds():
    """Return the live list of hospitals (69) from the public feed."""
    return requests.get(BEDS_URL, timeout=15).json()


def _candidates(triage, district, limit=12):
    """Filter hospitals: prefer the given district, else nearby, with free beds."""
    beds = fetch_beds()
    district = (district or "").strip().upper()

    def free(h):
        try:
            return int(h.get("free_beds") or 0)
        except (TypeError, ValueError):
            return 0

    pool = [h for h in beds if free(h) > 0]
    if district:
        same = [h for h in pool if h.get("district_name", "").upper() == district]
        if same:
            pool = same
    # Rank by free beds (desc) to surface the best-stocked options first.
    pool.sort(key=free, reverse=True)
    return pool[:limit]


def route(triage, district=""):
    """Recommend a hospital for a triage state.

    Returns a dict:
      {
        "recommended": {...} | None,   # chosen hospital record
        "block": str,                  # markdown block to append to the card
        "candidates": int,             # how many candidates were considered
      }
    """
    cands = _candidates(triage, district)
    if not cands:
        return {
            "recommended": None,
            "block": ("🏥 **No hospital with free beds found** for this district. "
                      "Call **102** for dispatch."),
            "candidates": 0,
        }

    system = (
        "You are the ROUTING AGENT of a Nepal emergency dispatch system. "
        "Given a patient's triage requirements and a list of candidate hospitals "
        "(with live free-bed counts), choose the single best hospital. "
        "Prefer hospitals likely to meet the requirements (e.g. CT/ICU/stroke "
        "capability) and with the most free beds. Be concise. "
        "Output ONLY valid JSON with keys:\n"
        "  facility_name: string (must be one of the candidate names)\n"
        "  district: string\n"
        "  free_beds: integer\n"
        "  reason: string (one short sentence on why this hospital)\n"
        "  eta_minutes: integer (a reasonable estimate, 5-40)\n"
        "  capabilities: array of short strings the hospital is assumed to have\n"
        "Do not add prose or code fences."
    )
    user = (
        "Triage requirements: " + json.dumps(triage.get("requirements", [])) + "\n"
        "Suspected pathway: " + str(triage.get("suspected_pathway", "")) + "\n"
        "Urgency: " + str(triage.get("urgency", "")) + "\n"
        "Requested district: " + (district or "(any)") + "\n\n"
        "Candidate hospitals (live free beds):\n" +
        json.dumps([{
            "facility_name": h["health_facility_name"],
            "district": h.get("district_name", ""),
            "palika": h.get("palika_name", ""),
            "free_beds": int(h.get("free_beds") or 0),
            "capacity": h.get("total_bed_capacity", ""),
            "public_nonpublic": h.get("public_nonpublic", ""),
            "contact_number": h.get("contact_number", ""),
        } for h in cands], ensure_ascii=False)
    )

    resp = client.chat.completions.create(
        model="default",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    pick = json.loads(resp.choices[0].message.content)

    # Map the chosen name back to the full live record (for contact, etc.).
    rec = next((h for h in cands
                if h["health_facility_name"].lower() == pick.get("facility_name", "").lower()),
               cands[0])

    caps = ", ".join(pick.get("capabilities", [])) or "general emergency"
    block = (
        f"\n\n---\n🏥 **Recommended: {rec['health_facility_name']}**\n"
        f"• District: {rec.get('district_name', '')} ({rec.get('palika_name', '')})\n"
        f"• Free beds now: **{pick.get('free_beds', rec.get('free_beds', '?'))}** "
        f"(capacity {rec.get('total_bed_capacity', '?')})\n"
        f"• {caps}\n"
        f"• ETA: ~{pick.get('eta_minutes', '?')} min\n"
        f"• Contact: {rec.get('contact_person', '')} — {rec.get('contact_number', '')}\n"
        f"• Why: {pick.get('reason', '')}"
    )
    return {"recommended": rec, "block": block, "candidates": len(cands)}


if __name__ == "__main__":
    # Quick standalone test.
    triage = {
        "urgency": "critical",
        "suspected_pathway": "stroke",
        "requirements": ["CT", "stroke_capability", "ICU", "oxygen"],
    }
    result = route(triage, district="KATHMANDU")
    print(json.dumps(result["recommended"], indent=2, ensure_ascii=False))
    print(result["block"])
