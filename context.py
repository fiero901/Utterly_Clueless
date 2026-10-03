"""JeevanRoute — live context layer (100% free, keyless).

Enriches the routing recommendation with real-world context, all from
public endpoints that require NO API key and NO signup:

  * Nominatim  (OSM)  -> geocode a district / municipality to lat,lng
  * OSRM demo  (OSM)  -> real driving travel-time (ETA) between two points
  * Open-Meteo         -> current weather at a location (rain / heat / wind)
  * BIPAD              -> recent earthquakes & fires near a location (disaster risk)

Every function degrades gracefully: on any network/parse error it returns
a safe default so a flaky external call can never break the emergency card.
"""
import math
import time

import requests

_UA = {"User-Agent": "jeevanroute/1.0 (emergency-routing research)"}
_TIMEOUT = 12

_NOMINATIM = "https://nominatim.openstreetmap.org/search"
_NOMINATIM_REV = "https://nominatim.openstreetmap.org/reverse"
_OSRM = "https://router.project-osrm.org/route/v1/driving"
_OPENMETEO = "https://api.open-meteo.com/v1/forecast"
_BIPAD = "https://bipadportal.gov.np/api/v1"


# --------------------------------------------------------------------------- #
# Geocoding (Nominatim / OSM)
# --------------------------------------------------------------------------- #
def geocode(query):
    """Return (lat, lng) for a place name, or None.

    Nominatim is free but rate-limited to ~1 request/second, so we sleep
    briefly between calls (the caller may geocode origin + destination).
    """
    try:
        r = requests.get(
            _NOMINATIM,
            params={"format": "json", "limit": 1, "countrycodes": "np", "q": query},
            headers=_UA,
            timeout=_TIMEOUT,
        )
        data = r.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass
    return None


def reverse_geocode(lat, lng):
    """Return a human-readable district name for (lat, lng), or "".

    Uses Nominatim reverse geocoding. In Nepal the OSM admin levels map to
    `county` = district (e.g. "Kathmandu") and `state` = province (e.g.
    "Bagmati Province"). We want the DISTRICT because the freehealth bed feed
    is keyed by English district names (KATHMANDU, BHAKTAPUR, ...) — a
    province value would never match and silently break location routing.
    So `county`/`district` are preferred, and we request English output so
    the value matches the feed's English names.
    """
    try:
        r = requests.get(
            _NOMINATIM_REV,
            params={"format": "json", "lat": lat, "lon": lng, "zoom": 10,
                    "accept-language": "en"},
            headers=_UA,
            timeout=_TIMEOUT,
        )
        addr = r.json().get("address", {})
        for key in ("county", "district", "city_district", "municipality", "state"):
            if addr.get(key):
                return addr[key].upper()
        return ""
    except Exception:
        return ""


# --------------------------------------------------------------------------- #
# Travel time (OSRM)
# --------------------------------------------------------------------------- #
# Administrative suffixes that appear in the bed feed's palika names but hurt
# Nominatim matching. We strip them to get the bare town name.
_ADMIN_SUFFIXES = (
    "METROPOLITAN CITY", "MUNICIPALITY", "RURAL MUNICIPALITY",
    "SUB METROPOLITAN CITY", "MUNICIPAL",
)


def _bare_town(palika):
    """'BIRATNAGAR METROPOLITAN CITY' -> 'Biratnagar'."""
    name = (palika or "").strip()
    for suf in _ADMIN_SUFFIXES:
        if name.upper().endswith(suf):
            name = name[: -len(suf)].strip()
    return name.title() or (palika or "").title()


def _geocode_destination(palika, district):
    """Geocode a hospital's location, trying several query forms.

    The bed feed gives ALL-CAPS palika + district names. Nominatim matches
    best on the bare town name, so we try: bare-town+district, full
    palika+district, then bare-town alone. Returns (lat,lng) or None.
    """
    town = _bare_town(palika)
    district_t = (district or "").title()
    queries = []
    if town and district_t:
        queries.append(f"{town} {district_t} Nepal")
    if palika and district:
        queries.append(f"{palika.title()} {district_t} Nepal")
    if town:
        queries.append(f"{town} Nepal")
    # Last resort: the district itself (small rural municipalities often
    # don't geocode, but the district always does).
    if district_t:
        queries.append(f"{district_t} Nepal")

    for q in queries:
        loc = geocode(q)
        if loc is not None:
            return loc
        time.sleep(1.1)  # respect Nominatim rate limit between attempts
    return None
def driving_minutes(origin, destination):
    """Real driving ETA in whole minutes between two (lat,lng) points, or None."""
    if not origin or not destination:
        return None
    try:
        olat, olng = origin
        dlat, dlng = destination
        r = requests.get(
            f"{_OSRM}/{olng},{olat};{dlng},{dlat}",
            params={"overview": "false"},
            headers=_UA,
            timeout=_TIMEOUT,
        )
        route = r.json()["routes"][0]
        return max(1, round(route["duration"] / 60))
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Weather (Open-Meteo)
# --------------------------------------------------------------------------- #
# WMO weather codes -> short human label. Only the codes that matter for
# emergency transport are mapped; anything else is "clear".
_WMO = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "rime fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain", 67: "heavy freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "rain showers", 81: "heavy showers", 82: "violent showers",
    85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm w/ hail", 99: "severe thunderstorm",
}


def weather(lat, lng):
    """Return a short weather dict for a location, or None.

    Shape: {"label": str, "temp_c": float, "rain_mm": float, "wind_kmh": float,
            "adverse": bool}  (adverse = conditions that slow transport)
    """
    if lat is None or lng is None:
        return None
    try:
        r = requests.get(
            _OPENMETEO,
            params={
                "latitude": lat, "longitude": lng,
                "current": "temperature_2m,precipitation,weather_code,wind_speed_10m",
                "timezone": "auto",
            },
            headers=_UA,
            timeout=_TIMEOUT,
        )
        cur = r.json()["current"]
        code = int(cur.get("weather_code", 0))
        label = _WMO.get(code, "clear")
        rain = float(cur.get("precipitation", 0) or 0)
        wind = float(cur.get("wind_speed_10m", 0) or 0)
        temp = float(cur.get("temperature_2m", 0) or 0)
        # Adverse = measurable rain, strong wind, or a storm/fog code.
        adverse = rain >= 0.5 or wind >= 30 or code in (95, 96, 99, 45, 48)
        return {"label": label, "temp_c": temp, "rain_mm": rain,
                "wind_kmh": wind, "adverse": adverse}
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Disaster risk (BIPAD)
# --------------------------------------------------------------------------- #
def _haversine_km(a, b):
    lat1, lng1 = a
    lat2, lng2 = b
    r = 6371.0
    dlat, dlng = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    h = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(h))


def disaster_warnings(lat, lng, within_km=150, lookback_days=30):
    """Return a list of short human warnings for quakes/fires nearby.

    Queries BIPAD's public earthquake + fire feeds and keeps events within
    `within_km` of the location. Recent events (within `lookback_days`) are
    surfaced as active warnings. If there are none, it falls back to the most
    significant nearby *historical* earthquakes as seismic-context (BIPAD's
    feed is a historical archive, so this keeps the demo informative).
    """
    if lat is None or lng is None:
        return []
    point = (lat, lng)
    now = time.time()
    cutoff = now - lookback_days * 86400

    recent, historical = [], []

    for kind, path, mag_field in (
        ("earthquake", "earthquake", "magnitude"),
        ("fire", "fire", None),
    ):
        try:
            r = requests.get(
                f"{_BIPAD}/{path}/",
                params={"page_size": 100},
                headers=_UA,
                timeout=_TIMEOUT,
            )
            results = r.json().get("results", [])
        except Exception:
            continue

        for ev in results:
            ts = None
            for key in ("eventOn", "createdOn"):
                raw = ev.get(key)
                if raw:
                    try:
                        ts = time.mktime(time.strptime(raw[:19], "%Y-%m-%dT%H:%M:%S"))
                        break
                    except Exception:
                        continue
            if ts is None:
                continue

            coords = (ev.get("point") or {}).get("coordinates")
            if not coords or len(coords) != 2:
                continue
            dist = _haversine_km(point, (coords[1], coords[0]))
            if dist > within_km:
                continue

            days_ago = max(0, round((now - ts) / 86400))
            place = ev.get("address") or ev.get("district") or "nearby"
            mag = ev.get(mag_field) if mag_field else None
            mag_s = f" M{mag}" if mag else ""

            if kind == "earthquake":
                if ts >= cutoff:
                    recent.append(f"⚠ Earthquake{mag_s} near {place} ({days_ago}d ago, ~{round(dist)} km)")
                else:
                    historical.append((mag or 0, dist, f"{place}", mag_s, ts))
            else:
                if ts >= cutoff:
                    recent.append(f"🔥 Fire reported near {place} ({days_ago}d ago, ~{round(dist)} km)")

    if recent:
        return recent[:4]

    # No recent events -> show the 2 strongest nearby historical quakes as context.
    historical.sort(key=lambda h: (-h[0], h[1]))
    fallback = []
    for mag, dist, place, mag_s, ts in historical[:2]:
        year = time.strftime("%Y", time.localtime(ts))
        fallback.append(
            f"📜 Seismic history: M{mag} near {place} ({year}, ~{round(dist)} km)")
    return fallback


# --------------------------------------------------------------------------- #
# Combined context block
# --------------------------------------------------------------------------- #
def build_context_block(origin_name, dest_name, dest_district="", origin_coords=None):
    """Geocode + enrich, then return a markdown context block (or "").

    `origin_name`    = caller's district (e.g. "KATHMANDU")
    `dest_name`      = recommended hospital's municipality/palika
    `dest_district`  = recommended hospital's district (fallback for geocoding)
    `origin_coords`  = optional (lat, lng) tuple; when provided, skips the
                       Nominatim geocode of origin_name (more accurate, faster)
    """
    if origin_coords:
        origin = tuple(origin_coords)
    else:
        origin = geocode(f"{origin_name} Nepal") if origin_name else None
        time.sleep(1.1)  # Nominatim rate limit
    dest = None
    if dest_name:
        dest = _geocode_destination(dest_name, dest_district)
    time.sleep(1.1)

    parts = []

    # Real ETA (replaces the LLM's guessed eta_minutes). Skip it when origin
    # and destination geocode to the same place (e.g. same city) — a ~1 min
    # OSRM result there is misleading, and the LLM's estimate is already fine.
    same_place = (
        origin and dest and
        abs(origin[0] - dest[0]) < 0.01 and abs(origin[1] - dest[1]) < 0.01
    )
    eta = driving_minutes(origin, dest) if not same_place else None
    if eta is not None:
        parts.append(f"🚗 **Real road ETA: ~{eta} min** (OSRM)")

    # Weather at the caller's location.
    wx = weather(*origin) if origin else None
    if wx:
        flag = " ⚠️" if wx["adverse"] else ""
        parts.append(
            f"🌦 **Weather:** {wx['label']}, {wx['temp_c']:.0f}°C, "
            f"wind {wx['wind_kmh']:.0f} km/h{flag}")
        if wx["adverse"]:
            parts.append("_Adverse conditions may slow transport._")

    # Nearby disaster warnings.
    warns = disaster_warnings(*origin) if origin else []
    if warns:
        parts.append("**Nearby alerts:**")
        parts += [f"- {w}" for w in warns]

    if not parts:
        return ""
    return "\n".join(parts)


# --- Live public-bed feed (moved from routing_agent.py) -----------------------
BEDS_URL = "https://freehealth.mohp.gov.np/api/bed-summary"


def fetch_beds() -> list:
    """Live public-bed feed (~69 hospitals). Returns [] on any failure."""
    try:
        data = requests.get(BEDS_URL, timeout=15).json()
        return data if isinstance(data, list) else []
    except Exception:
        return []
