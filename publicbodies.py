"""JeevanRoute — Public Bodies / Information Officer lookup.

Data source: Open Knowledge Nepal `publicbodies-data`
    https://github.com/openknowledgenp/publicbodies-data
    -> publicbodies data.csv  (432 public bodies across 71 districts)

Each row carries the agency name, district, contact phone/email, website,
and — crucially — the **Information Officer** (name, phone, email) who is
the official point of contact for information requests (RTI / RTA) and
general follow-ups with that body.

The CSV is vendored into `data/publicbodies.csv` so the app works offline
and never depends on GitHub at runtime. Re-copy the file to refresh.

Every function degrades gracefully: a missing district or no match simply
returns None so the caller can omit the block from the emergency card.
"""
import csv
import os
import re

_CSV_PATH = os.path.join(os.path.dirname(__file__), "data", "publicbodies.csv")

# Column indices in the vendored CSV (0-based).
_COL_NAME = 0
_COL_WEBSITE = 1
_COL_ADDRESS = 2
_COL_DISTRICT = 3
_COL_BODY_EMAIL = 4
_COL_BODY_PHONE = 5
_COL_IO_NAME = 6
_COL_IO_EMAIL = 7
_COL_IO_PHONE = 8


def _clean(value):
    """Trim a CSV cell; treat '-' / empty as missing."""
    v = (value or "").strip()
    if v in ("-", "--", "N/A", "NA"):
        return ""
    return v


def _norm_district(name):
    """Normalize a district for comparison: lowercase, strip, drop diacritics.

    The bed feed and the publicbodies CSV both use ALL-CAPS / Title-case
    district names, so a case-insensitive compare is enough. We also strip
    a trailing ' District' if present.
    """
    d = (name or "").strip().lower()
    d = re.sub(r"\s+district$", "", d)
    return d


def _load():
    """Load the CSV once into a list of dicts. Returns [] if file missing."""
    if not os.path.exists(_CSV_PATH):
        return []
    rows = []
    with open(_CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)  # skip header
        for r in reader:
            if len(r) < 9:
                continue
            rows.append({
                "name": _clean(r[_COL_NAME]),
                "website": _clean(r[_COL_WEBSITE]),
                "address": _clean(r[_COL_ADDRESS]),
                "district": _clean(r[_COL_DISTRICT]),
                "body_email": _clean(r[_COL_BODY_EMAIL]),
                "body_phone": _clean(r[_COL_BODY_PHONE]),
                "io_name": _clean(r[_COL_IO_NAME]),
                "io_email": _clean(r[_COL_IO_EMAIL]),
                "io_phone": _clean(r[_COL_IO_PHONE]),
            })
    return rows


# Lazy-load and cache (the file is static for the life of the process).
_CACHE = None


def _rows():
    global _CACHE
    if _CACHE is None:
        _CACHE = _load()
    return _CACHE


def _score(row, query):
    """Score how well a row matches a free-text query (higher = better)."""
    if not query:
        return 0
    q = query.lower()
    name = row["name"].lower()
    # Exact substring in the name is the strongest signal.
    if q in name:
        return 10
    # Word-level overlap.
    q_words = set(re.findall(r"[a-z0-9]+", q))
    n_words = set(re.findall(r"[a-z0-9]+", name))
    overlap = len(q_words & n_words)
    return overlap


def find_officer(district, query=""):
    """Find the best-matching public body for a district (and optional query).

    Args:
        district: the caller's district (e.g. "Kathmandu").
        query: optional free-text hint (e.g. "health", "police", "electricity")
               used to rank matches within the district.

    Returns a dict with the agency + its Information Officer, or None if no
    suitable match is found.
    """
    rows = _rows()
    if not rows:
        return None

    d_norm = _norm_district(district)
    pool = [r for r in rows if _norm_district(r["district"]) == d_norm] if d_norm else list(rows)
    if not pool:
        return None

    # Rank: query score first, then prefer a NAMED information officer (a real
    # person to call), then any officer contact at all.
    pool.sort(
        key=lambda r: (_score(r, query), bool(r["io_name"]), bool(r["io_phone"] or r["io_email"])),
        reverse=True,
    )
    best = pool[0]

    return {
        "name": best["name"],
        "district": best["district"],
        "address": best["address"],
        "website": best["website"],
        "body_phone": best["body_phone"],
        "body_email": best["body_email"],
        "io_name": best["io_name"],
        "io_phone": best["io_phone"],
        "io_email": best["io_email"],
    }


def render_block(result):
    """Format a find_officer() result as a markdown block for the card.

    Returns "" if result is None or has no usable contact.
    """
    if not result:
        return ""
    io_name = result.get("io_name") or "Information Officer"
    io_phone = result.get("io_phone") or result.get("body_phone") or ""
    io_email = result.get("io_email") or result.get("body_email") or ""

    lines = [
        f"\n\n📞 **Relevant public body: {result['name']}**",
        f"• District: {result.get('district', '')}",
    ]
    if result.get("address"):
        lines.append(f"• Address: {result['address']}")
    if io_phone:
        lines.append(f"• Information Officer: **{io_name}** — {io_phone}")
    if io_email:
        lines.append(f"• Email: {io_email}")
    if result.get("website"):
        lines.append(f"• Website: {result['website']}")
    lines.append("_For information requests (RTI/RTA) or follow-ups, contact the officer above._")
    return "\n".join(lines)


if __name__ == "__main__":
    # Quick self-test.
    import json
    for d, q in [("Kathmandu", ""), ("Kathmandu", "health"), ("Lalitpur", ""), ("Chitwan", "police")]:
        r = find_officer(d, q)
        print(f"--- district={d!r} query={q!r} ---")
        print(json.dumps(r, indent=2, ensure_ascii=False) if r else "  (no match)")
        if r:
            print(render_block(r))
