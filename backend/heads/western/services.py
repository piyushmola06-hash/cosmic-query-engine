"""
S-06 — Western Astrology Head Engine

Computes Western astrological findings using the tropical zodiac (no ayanamsha).
Placidus house system, falling back to whole sign above 66°N/S latitude.
Moon sign and certainty are inherited from S-03 output — never recomputed here.

Done condition (from spec):
  All three tiers produce valid output. Cusp handling correct for all tiers.
  S-03 moon_sign_certain inherited correctly — never recomputed.
  Tendency window in weeks or null.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

try:
    import swisseph as swe
    _SWE_AVAILABLE = True
except ImportError:
    _SWE_AVAILABLE = False

# ── Ephemeris path ────────────────────────────────────────────────────────────
_EPH_PATH = str(Path(__file__).resolve().parent.parent.parent / "ephe")

# ── Tropical zodiac signs ─────────────────────────────────────────────────────
SIGNS: list[str] = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

# ── House sign lords (classical — outer planets not considered rulers) ─────────
_SIGN_LORDS: dict[str, str] = {
    "Aries": "Mars", "Taurus": "Venus", "Gemini": "Mercury", "Cancer": "Moon",
    "Leo": "Sun", "Virgo": "Mercury", "Libra": "Venus", "Scorpio": "Mars",
    "Sagittarius": "Jupiter", "Capricorn": "Saturn", "Aquarius": "Saturn",
    "Pisces": "Jupiter",
}

# ── Aspect definitions ────────────────────────────────────────────────────────
ASPECTS: list[tuple[str, float]] = [
    ("Conjunction", 0.0),
    ("Sextile", 60.0),
    ("Square", 90.0),
    ("Trine", 120.0),
    ("Opposition", 180.0),
]
ASPECT_ORB = 8.0       # degrees tolerance
MAX_ASPECTS = 8        # maximum returned, tightest first

# ── Planet IDs ────────────────────────────────────────────────────────────────
if _SWE_AVAILABLE:
    _NATAL_PLANET_IDS: dict[str, int] = {
        "Sun": swe.SUN,
        "Moon": swe.MOON,
        "Mercury": swe.MERCURY,
        "Venus": swe.VENUS,
        "Mars": swe.MARS,
        "Jupiter": swe.JUPITER,
        "Saturn": swe.SATURN,
        "Uranus": swe.URANUS,
        "Neptune": swe.NEPTUNE,
        "Pluto": swe.PLUTO,
        "North Node": swe.MEAN_NODE,
    }
    _OUTER_PLANET_IDS: dict[str, int] = {
        "Jupiter": swe.JUPITER,
        "Saturn": swe.SATURN,
        "Uranus": swe.URANUS,
        "Neptune": swe.NEPTUNE,
        "Pluto": swe.PLUTO,
        "North Node": swe.MEAN_NODE,
    }
    # Approximate daily speed in degrees (used for transit window calculation)
    _PLANET_DAILY_SPEED: dict[str, float] = {
        "Jupiter": 0.083,
        "Saturn": 0.034,
        "Uranus": 0.012,
        "Neptune": 0.006,
        "Pluto": 0.004,
        "North Node": -0.053,   # retrograde
    }

# ── Cusp proximity (sun moves ~1°/day; 2 days ≈ 2°) ──────────────────────────
CUSP_PROXIMITY_DEGREES = 2.0

# ── Extreme latitude Placidus fallback ───────────────────────────────────────
EXTREME_LAT = 66.0

# ── City geocoding ────────────────────────────────────────────────────────────
_CITY_COORDS: dict[str, tuple[float, float]] = {
    "mumbai": (19.076, 72.877), "delhi": (28.614, 77.209),
    "new delhi": (28.614, 77.209), "kolkata": (22.573, 88.363),
    "chennai": (13.083, 80.270), "bangalore": (12.972, 77.594),
    "bengaluru": (12.972, 77.594), "hyderabad": (17.385, 78.487),
    "pune": (18.520, 73.856), "ahmedabad": (23.022, 72.572),
    "london": (51.509, -0.118), "new york": (40.713, -74.006),
    "new york city": (40.713, -74.006), "los angeles": (34.052, -118.244),
    "chicago": (41.878, -87.630), "toronto": (43.653, -79.383),
    "sydney": (-33.869, 151.209), "melbourne": (-37.814, 144.963),
    "paris": (48.857, 2.347), "berlin": (52.520, 13.405),
    "tokyo": (35.690, 139.692), "beijing": (39.904, 116.407),
    "shanghai": (31.224, 121.469), "dubai": (25.205, 55.271),
    "singapore": (1.290, 103.850), "hong kong": (22.320, 114.169),
    "moscow": (55.755, 37.617), "istanbul": (41.015, 28.979),
    "cairo": (30.065, 31.250), "nairobi": (-1.286, 36.818),
    "johannesburg": (-26.195, 28.034), "sao paulo": (-23.549, -46.633),
    "mexico city": (19.433, -99.133), "buenos aires": (-34.603, -58.381),
    "jakarta": (-6.175, 106.827), "karachi": (24.906, 67.082),
    "lahore": (31.558, 74.357), "dhaka": (23.811, 90.412),
    "colombo": (6.927, 79.862), "kathmandu": (27.717, 85.317),
    "amsterdam": (52.370, 4.895), "madrid": (40.416, -3.703),
    "rome": (41.902, 12.496), "vienna": (48.208, 16.373),
    # Extreme latitudes for testing Placidus fallback
    "reykjavik": (64.135, -21.895), "tromsø": (69.650, 18.956),
    "anchorage": (61.218, -149.900), "murmansk": (68.972, 33.075),
    "longyearbyen": (78.223, 15.636),
}

_COUNTRY_COORDS: dict[str, tuple[float, float]] = {
    "india": (28.614, 77.209), "uk": (51.509, -0.118),
    "united kingdom": (51.509, -0.118), "usa": (38.907, -77.036),
    "united states": (38.907, -77.036), "canada": (45.424, -75.695),
    "australia": (-35.282, 149.128), "pakistan": (33.720, 73.061),
    "bangladesh": (23.811, 90.412), "sri lanka": (6.927, 79.862),
    "nepal": (27.717, 85.317), "germany": (52.520, 13.405),
    "france": (48.857, 2.347), "china": (39.904, 116.407),
    "japan": (35.690, 139.692), "russia": (55.755, 37.617),
    "uae": (25.205, 55.271), "singapore": (1.290, 103.850),
    "norway": (59.913, 10.740), "iceland": (64.135, -21.895),
}


# ── Pure math helpers ─────────────────────────────────────────────────────────

def longitude_to_sign(longitude: float) -> str:
    """Tropical ecliptic longitude (0–360) → zodiac sign name."""
    return SIGNS[int(longitude / 30) % 12]


def _angular_separation(lon1: float, lon2: float) -> float:
    """
    Shortest angular distance between two longitudes, in [0, 180].
    """
    diff = abs((lon1 - lon2) % 360.0)
    return diff if diff <= 180.0 else 360.0 - diff


def _aspect_orb(lon1: float, lon2: float, aspect_angle: float) -> Optional[float]:
    """
    Return the orb (degrees) between two planets for a given aspect angle.
    Returns None if not within ASPECT_ORB tolerance.
    """
    sep = _angular_separation(lon1, lon2)
    orb = abs(sep - aspect_angle)
    # Conjunction: check both 0 and 360 representations
    if aspect_angle == 0.0:
        orb = min(orb, abs(sep - 360.0)) if sep > 180 else orb
    return orb if orb <= ASPECT_ORB else None


def _get_coords(birth_location: dict) -> tuple[float, float, bool]:
    """Resolve birth location to (lat, lon, found)."""
    city = (birth_location.get("city") or "").lower().strip()
    country = (birth_location.get("country") or "").lower().strip()
    if city and city in _CITY_COORDS:
        return (*_CITY_COORDS[city], True)
    if country and country in _COUNTRY_COORDS:
        return (*_COUNTRY_COORDS[country], True)
    return (0.0, 0.0, False)


# ── Planetary positions (tropical) ───────────────────────────────────────────

def compute_planetary_positions(birth_jd: float) -> dict[str, Optional[float]]:
    """
    Compute tropical longitudes for all natal planets.
    Returns {planet_name: longitude_degrees} or None on individual failure.
    South Node is derived as North Node + 180°.
    """
    if not _SWE_AVAILABLE:
        return {}

    positions: dict[str, Optional[float]] = {}
    for name, pid in _NATAL_PLANET_IDS.items():
        try:
            result, _ = swe.calc_ut(birth_jd, pid)      # tropical — no FLG_SIDEREAL
            positions[name] = result[0] % 360.0
        except Exception:
            positions[name] = None

    # South Node = North Node + 180°
    nn = positions.get("North Node")
    positions["South Node"] = (nn + 180.0) % 360.0 if nn is not None else None

    return positions


# ── Sun sign and cusp handling ────────────────────────────────────────────────

def compute_sun_sign(
    dob: dict, birth_hour: float, birth_jd: float
) -> tuple[str, bool]:
    """
    Compute tropical sun sign from DOB.

    Returns (sun_sign, sun_sign_certain).
    sun_sign_certain = False when sun is within CUSP_PROXIMITY_DEGREES of a sign boundary.
    """
    if not _SWE_AVAILABLE or birth_jd is None:
        # Fallback: compute from static date boundaries (approximate)
        return _sun_sign_from_date(dob), True

    try:
        result, _ = swe.calc_ut(birth_jd, swe.SUN)
        sun_lon = result[0] % 360.0
        sign = longitude_to_sign(sun_lon)
        pos_in_sign = sun_lon % 30.0
        # Cusp: within CUSP_PROXIMITY_DEGREES of a boundary
        near_cusp = pos_in_sign < CUSP_PROXIMITY_DEGREES or pos_in_sign > (30.0 - CUSP_PROXIMITY_DEGREES)
        return sign, not near_cusp
    except Exception:
        return _sun_sign_from_date(dob), True


def _sun_sign_from_date(dob: dict) -> str:
    """
    Approximate sun sign from calendar date.
    Boundaries are approximate (tropical sign entry dates vary by ±1 day per year).
    Used only as fallback when ephemeris unavailable.
    """
    m, d = dob["month"], dob["day"]
    # Approximate boundaries (day is entry into the sign)
    if (m == 3 and d >= 21) or (m == 4 and d <= 19):
        return "Aries"
    if (m == 4 and d >= 20) or (m == 5 and d <= 20):
        return "Taurus"
    if (m == 5 and d >= 21) or (m == 6 and d <= 20):
        return "Gemini"
    if (m == 6 and d >= 21) or (m == 7 and d <= 22):
        return "Cancer"
    if (m == 7 and d >= 23) or (m == 8 and d <= 22):
        return "Leo"
    if (m == 8 and d >= 23) or (m == 9 and d <= 22):
        return "Virgo"
    if (m == 9 and d >= 23) or (m == 10 and d <= 22):
        return "Libra"
    if (m == 10 and d >= 23) or (m == 11 and d <= 21):
        return "Scorpio"
    if (m == 11 and d >= 22) or (m == 12 and d <= 21):
        return "Sagittarius"
    if (m == 12 and d >= 22) or (m == 1 and d <= 19):
        return "Capricorn"
    if (m == 1 and d >= 20) or (m == 2 and d <= 18):
        return "Aquarius"
    return "Pisces"


# ── Aspect calculation ────────────────────────────────────────────────────────

def compute_aspects(positions: dict[str, Optional[float]]) -> list[dict]:
    """
    Compute major aspects between all natal planet pairs.
    Returns up to MAX_ASPECTS entries sorted by tightest orb.

    Each entry: {planet1, planet2, aspect, angle, orb}
    """
    planet_names = [k for k, v in positions.items() if v is not None]
    candidates: list[tuple[float, dict]] = []

    for i in range(len(planet_names)):
        for j in range(i + 1, len(planet_names)):
            p1 = planet_names[i]
            p2 = planet_names[j]
            lon1 = positions[p1]
            lon2 = positions[p2]
            if lon1 is None or lon2 is None:
                continue

            for aspect_name, aspect_angle in ASPECTS:
                orb = _aspect_orb(lon1, lon2, aspect_angle)
                if orb is not None:
                    candidates.append((orb, {
                        "planet1": p1,
                        "planet2": p2,
                        "aspect": aspect_name,
                        "angle": aspect_angle,
                        "orb": round(orb, 2),
                    }))

    # Sort by orb (tightest first), return max MAX_ASPECTS
    candidates.sort(key=lambda x: x[0])
    return [entry for _, entry in candidates[:MAX_ASPECTS]]


# ── Houses and angles ─────────────────────────────────────────────────────────

def compute_houses(
    birth_jd: float, lat: float, lon: float
) -> tuple[dict, Optional[str], Optional[str], bool]:
    """
    Compute Placidus houses. Falls back to whole sign for extreme latitudes.

    Returns:
        (houses_dict, rising_sign, midheaven_sign, used_whole_sign_fallback)
    houses_dict: {"1st": sign, ..., "12th": sign}
    """
    if not _SWE_AVAILABLE:
        return {}, None, None, False

    house_labels = [
        "1st", "2nd", "3rd", "4th", "5th", "6th",
        "7th", "8th", "9th", "10th", "11th", "12th",
    ]

    used_fallback = False
    hsys = b"P"  # Placidus

    if abs(lat) > EXTREME_LAT:
        hsys = b"W"  # whole sign fallback
        used_fallback = True

    try:
        cusps, ascmc = swe.houses(birth_jd, lat, lon, hsys)
        # cusps[0] is unused (index 1–12 are the house cusps)
        rising_lon = ascmc[0] % 360.0
        mc_lon = ascmc[1] % 360.0
        rising_sign = longitude_to_sign(rising_lon)
        mc_sign = longitude_to_sign(mc_lon)
        houses_dict = {
            house_labels[i]: longitude_to_sign(cusps[i] % 360.0)
            for i in range(12)
        }
        return houses_dict, rising_sign, mc_sign, used_fallback

    except Exception:
        # Last-resort whole sign fallback
        try:
            cusps, ascmc = swe.houses(birth_jd, lat, lon, b"W")
            rising_lon = ascmc[0] % 360.0
            mc_lon = ascmc[1] % 360.0
            rising_sign = longitude_to_sign(rising_lon)
            mc_sign = longitude_to_sign(mc_lon)
            houses_dict = {
                house_labels[i]: longitude_to_sign(cusps[i] % 360.0)
                for i in range(12)
            }
            return houses_dict, rising_sign, mc_sign, True
        except Exception:
            return {label: None for label in house_labels}, None, None, True


# ── Chart pattern detection ───────────────────────────────────────────────────

def detect_chart_pattern(positions: dict[str, Optional[float]]) -> Optional[str]:
    """
    Detect the overall chart pattern from planetary distribution.

    Patterns (from most to least constrained):
    Bundle    → all planets span ≤ 120°
    Bowl      → all planets within 180° (max arc gap ≥ 180°)
    Bucket    → 10 planets in hemisphere, 1 isolated (the handle)
    Locomotive → continuous arc of ~240° with one 120° empty sector
    Seesaw    → two distinct clusters of planets
    Splash    → planets spread across all quadrants
    """
    lons = sorted(v % 360.0 for v in positions.values() if v is not None)
    if len(lons) < 3:
        return None

    # Compute gaps between consecutive planets (including wrap-around gap)
    gaps: list[float] = []
    for i in range(len(lons)):
        next_lon = lons[(i + 1) % len(lons)]
        gap = (next_lon - lons[i]) % 360.0
        gaps.append(gap)
    max_gap = max(gaps)
    arc_span = 360.0 - max_gap  # degrees the planets actually span

    if arc_span <= 120.0:
        return "Bundle"

    if max_gap >= 180.0:
        return "Bowl"

    # Bucket: check if one planet is isolated (gap of ≥ 150° on both sides)
    for i, gap in enumerate(gaps):
        if gap >= 150.0:
            prev_gap = gaps[(i - 1) % len(gaps)]
            if prev_gap >= 150.0:
                return "Bucket"

    if max_gap >= 120.0:
        # Locomotive: one ~120° empty sector
        return "Locomotive"

    # Seesaw: two distinct groups
    # Check for two gaps each ≥ 60°
    large_gaps = [g for g in gaps if g >= 60.0]
    if len(large_gaps) >= 2:
        return "Seesaw"

    return "Splash"


# ── Transits ──────────────────────────────────────────────────────────────────

def compute_current_transits(
    natal_positions: dict[str, Optional[float]], today_jd: float
) -> list[dict]:
    """
    Compute current transiting outer planet aspects against natal chart.
    Returns entries with {transiting_planet, natal_planet, aspect, orb, transit_note}.
    """
    if not _SWE_AVAILABLE:
        return []

    transits: list[dict] = []
    for transit_name, transit_id in _OUTER_PLANET_IDS.items():
        try:
            result, _ = swe.calc_ut(today_jd, transit_id)
            transit_lon = result[0] % 360.0
        except Exception:
            continue

        for natal_name, natal_lon in natal_positions.items():
            if natal_lon is None:
                continue
            for aspect_name, aspect_angle in ASPECTS:
                orb = _aspect_orb(transit_lon, natal_lon, aspect_angle)
                if orb is not None and orb <= 3.0:   # tighter orb for transits
                    transits.append({
                        "transiting_planet": transit_name,
                        "natal_planet": natal_name,
                        "aspect": aspect_name,
                        "orb": round(orb, 2),
                        "transit_note": (
                            f"Transiting {transit_name} {aspect_name.lower()} "
                            f"natal {natal_name} (orb {orb:.1f}°)"
                        ),
                    })

    # Sort by orb, return max 8
    transits.sort(key=lambda x: x["orb"])
    return transits[:8]


# ── Tendency window ───────────────────────────────────────────────────────────

def compute_tendency_window(
    natal_positions: dict[str, Optional[float]],
    today_jd: float,
    today: date,
) -> Optional[dict]:
    """
    Find nearest exact aspect between transiting outer planet and natal planet
    within 6-month window (~26 weeks). Returns {min, max} in weeks or None.
    """
    if not _SWE_AVAILABLE or not natal_positions:
        return None

    window_weeks: list[float] = []
    max_weeks = 26.0

    for transit_name, transit_id in _OUTER_PLANET_IDS.items():
        try:
            result, _ = swe.calc_ut(today_jd, transit_id, swe.FLG_SPEED)
            transit_lon = result[0] % 360.0
            # Daily speed (may be negative for retrograde)
            daily_speed = result[3]
        except Exception:
            continue

        if abs(daily_speed) < 0.001:
            continue  # stationary — skip

        for natal_lon in natal_positions.values():
            if natal_lon is None:
                continue

            for _, aspect_angle in ASPECTS:
                # Check each aspect
                sep = (transit_lon - natal_lon) % 360.0
                # Exact aspect occurs when sep == aspect_angle
                # Distance to exact: how far the transiting planet must travel
                diff_fwd = (aspect_angle - sep) % 360.0
                diff_bwd = (sep - aspect_angle) % 360.0

                # Choose shortest direction
                if daily_speed > 0:
                    dist = diff_fwd if diff_fwd <= diff_bwd else None
                else:
                    dist = diff_bwd if diff_bwd <= diff_fwd else None

                if dist is None:
                    continue

                # Weeks to exact
                weeks = dist / (abs(daily_speed) * 7.0)
                if 0 < weeks <= max_weeks:
                    window_weeks.append(round(weeks, 1))

    if not window_weeks:
        return None

    window_weeks.sort()
    return {"min": window_weeks[0], "max": window_weeks[-1]}


# ── Query relevance ───────────────────────────────────────────────────────────

_CAREER_KW = frozenset({"career", "job", "work", "business", "professional", "promotion", "salary"})
_RELATIONSHIP_KW = frozenset({"relationship", "love", "marriage", "partner", "romantic", "spouse"})
_FINANCE_KW = frozenset({"finance", "money", "wealth", "investment", "income", "financial"})
_HEALTH_KW = frozenset({"health", "illness", "wellness", "body", "disease", "medical"})
_TRAVEL_KW = frozenset({"travel", "move", "relocate", "abroad", "foreign", "journey", "relocation"})
_DIRECTION_KW = frozenset({"direction", "purpose", "path", "life", "future", "guidance", "general"})


def build_query_relevant_findings(
    query: str,
    sun_sign: Optional[str],
    moon_sign: Optional[str],
    positions: dict[str, Optional[float]],
    houses: dict,
    rising_sign: Optional[str],
    chart_pattern: Optional[str],
    transits: list[dict],
    north_node_sign: Optional[str],
    midheaven: Optional[str],
) -> list[dict]:
    """
    Build query-relevant findings list. Never returns empty.
    """
    tokens = set(re.split(r"\W+", (query or "").lower()))
    relevant: list[dict] = []

    def _sign_entry(planet: str, note: str) -> dict:
        lon = positions.get(planet)
        sign = longitude_to_sign(lon) if lon is not None else None
        return {
            "finding": planet.lower().replace(" ", "_"),
            "value": sign or "unavailable",
            "note": note + (f" In {sign}." if sign else " Position unavailable."),
        }

    def _house_lord_entry(house_label: str, house_num: int, note: str) -> Optional[dict]:
        sign = houses.get(house_label)
        if sign:
            lord = _SIGN_LORDS.get(sign)
            return {
                "finding": f"house_{house_num}_ruler",
                "value": lord or sign,
                "note": f"{note} house ruler: {lord or sign}.",
            }
        return None

    def _transit_entries(planet: str) -> list[dict]:
        return [
            {
                "finding": f"{planet.lower()}_transit",
                "value": t["aspect"],
                "note": t["transit_note"],
            }
            for t in transits
            if t["transiting_planet"] == planet
        ][:2]  # max 2 transit entries per planet

    if tokens & _CAREER_KW:
        lord = _house_lord_entry("10th", 10, "Career (10th)")
        if lord:
            relevant.append(lord)
        relevant.append(_sign_entry("Saturn", "Saturn — career, discipline, ambition."))
        relevant.append(_sign_entry("Sun", "Sun — identity and career drive."))
        if midheaven:
            relevant.append({"finding": "midheaven", "value": midheaven, "note": f"Midheaven (MC): {midheaven}."})
        relevant.extend(_transit_entries("Saturn"))

    elif tokens & _RELATIONSHIP_KW:
        lord = _house_lord_entry("7th", 7, "Relationships (7th)")
        if lord:
            relevant.append(lord)
        relevant.append(_sign_entry("Venus", "Venus — love, harmony, attraction."))
        relevant.append(_sign_entry("Mars", "Mars — desire and drive in relationships."))
        relevant.extend(_transit_entries("Venus"))

    elif tokens & _FINANCE_KW:
        lord = _house_lord_entry("2nd", 2, "Finances (2nd)")
        if lord:
            relevant.append(lord)
        relevant.append(_sign_entry("Jupiter", "Jupiter — wealth, expansion, abundance."))
        relevant.append(_sign_entry("Venus", "Venus — material comfort and accumulation."))
        relevant.extend(_transit_entries("Jupiter"))

    elif tokens & _HEALTH_KW:
        lord_1 = _house_lord_entry("1st", 1, "Body (1st)")
        lord_6 = _house_lord_entry("6th", 6, "Health (6th)")
        if lord_1:
            relevant.append(lord_1)
        if lord_6:
            relevant.append(lord_6)
        relevant.append(_sign_entry("Mars", "Mars — physical vitality."))

    elif tokens & _TRAVEL_KW:
        lord = _house_lord_entry("9th", 9, "Long travel (9th)")
        if lord:
            relevant.append(lord)
        relevant.append(_sign_entry("Jupiter", "Jupiter — travel, expansion, abroad."))
        if north_node_sign:
            relevant.append({
                "finding": "north_node",
                "value": north_node_sign,
                "note": f"North Node in {north_node_sign} — direction of growth.",
            })

    elif tokens & _DIRECTION_KW:
        if rising_sign:
            relevant.append({
                "finding": "rising_sign",
                "value": rising_sign,
                "note": f"Rising sign: {rising_sign} — your outer presentation and approach to life.",
            })
        if sun_sign:
            relevant.append({
                "finding": "sun_sign",
                "value": sun_sign,
                "note": f"Sun sign: {sun_sign} — your core identity.",
            })
        if moon_sign:
            relevant.append({
                "finding": "moon_sign",
                "value": moon_sign,
                "note": f"Moon sign: {moon_sign} — your emotional nature.",
            })
        if north_node_sign:
            relevant.append({
                "finding": "north_node",
                "value": north_node_sign,
                "note": f"North Node in {north_node_sign} — karmic direction.",
            })
        if chart_pattern:
            relevant.append({
                "finding": "chart_pattern",
                "value": chart_pattern,
                "note": f"Chart pattern: {chart_pattern}.",
            })

    # No match / fallback
    if not relevant:
        if sun_sign:
            relevant.append({
                "finding": "sun_sign",
                "value": sun_sign,
                "note": f"Sun sign: {sun_sign}.",
            })
        if moon_sign:
            relevant.append({
                "finding": "moon_sign",
                "value": moon_sign,
                "note": f"Moon sign: {moon_sign}.",
            })
        for t in transits[:2]:
            relevant.append({
                "finding": "major_transit",
                "value": t["transit_note"],
                "note": t["transit_note"],
            })

    # Spec: never empty
    if not relevant:
        relevant.append({
            "finding": "sun_sign",
            "value": sun_sign or "unavailable",
            "note": f"Sun sign: {sun_sign}.",
        })

    return relevant


# ── Main engine ───────────────────────────────────────────────────────────────

class WesternHeadEngine:
    """
    S-06 Western Astrology Head Engine.

    Tropical zodiac throughout. Moon sign inherited from S-03 — never recomputed.
    Placidus houses for exact tier (whole sign fallback for extreme latitudes).
    """

    def compute(
        self,
        dob: dict,
        birth_time: dict,
        birth_location: dict,
        gender: Optional[str],
        moon: dict,
        query: str,
        today: Optional[date] = None,
    ) -> dict:
        """
        Compute Western astrology findings.

        Args:
            dob: {"day": int, "month": int, "year": int}
            birth_time: {"tier": str, "normalised_time": str|None, ...}
            birth_location: {"city": str, "country": str}
            gender: optional
            moon: {"moon_sign": str, "moon_sign_certain": bool,
                   "transition_occurred": bool}   ← inherited from S-03, never recomputed
            query: user question string
            today: date override for testing

        Returns:
            S-06 contract output dict.
        """
        if today is None:
            today = date.today()

        tier = birth_time.get("tier", "none")
        normalised_time = birth_time.get("normalised_time")

        available_findings: list[str] = []
        unavailable_findings: list[str] = []
        confidence_issues: list[str] = []
        trail_sections: list[dict] = []

        # ── Initialise ephemeris (tropical — do NOT set sidereal mode) ────────
        if _SWE_AVAILABLE:
            swe.set_ephe_path(_EPH_PATH)

        # ── Julian day for birth ──────────────────────────────────────────────
        birth_hour = 12.0  # Default noon for cusp computation per spec
        if normalised_time:
            try:
                h, m = normalised_time.split(":")
                birth_hour = int(h) + int(m) / 60.0
            except (ValueError, AttributeError):
                birth_hour = 12.0

        birth_jd: Optional[float] = None
        if _SWE_AVAILABLE:
            try:
                birth_jd = swe.julday(dob["year"], dob["month"], dob["day"], birth_hour)
            except Exception:
                birth_jd = None

        # ── Sun sign (tropical) with cusp handling ────────────────────────────
        sun_sign, sun_sign_certain = compute_sun_sign(dob, birth_hour, birth_jd)

        # Spec: cusp date + non-exact tier → flag uncertain (already done in compute_sun_sign)
        if not sun_sign_certain and tier != "exact":
            confidence_issues.append(
                f"Sun born near sign boundary — sun sign may be {sun_sign} or adjacent. "
                "Exact time required for certainty."
            )

        available_findings.append("sun_sign")
        trail_sections.append({
            "title": "Sun Sign",
            "content": (
                f"Sun sign: {sun_sign} (tropical)."
                + ("" if sun_sign_certain else " Born near sign cusp — uncertain.")
            ),
            "available": True,
        })

        # ── Moon sign — inherited from S-03, NEVER recomputed ─────────────────
        moon_sign: Optional[str] = moon.get("moon_sign")
        moon_sign_certain: bool = moon.get("moon_sign_certain", True)
        available_findings.append("moon_sign")
        trail_sections.append({
            "title": "Moon Sign",
            "content": (
                f"Moon sign: {moon_sign} (from S-03)."
                + ("" if moon_sign_certain else " Moon sign uncertain — born near sign boundary.")
            ),
            "available": True,
        })

        # ── Planetary positions (tropical) ────────────────────────────────────
        positions: dict[str, Optional[float]] = {}
        if _SWE_AVAILABLE and birth_jd is not None:
            positions = compute_planetary_positions(birth_jd)
            available_findings.append("planetary_positions")
        else:
            confidence_issues.append("Swiss Ephemeris unavailable — planetary positions not computed.")
            unavailable_findings.append("planetary_positions")

        def _sign_from_pos(planet: str) -> Optional[str]:
            lon = positions.get(planet)
            return longitude_to_sign(lon) if lon is not None else None

        mercury_sign = _sign_from_pos("Mercury")
        venus_sign = _sign_from_pos("Venus")
        mars_sign = _sign_from_pos("Mars")
        jupiter_sign = _sign_from_pos("Jupiter")
        saturn_sign = _sign_from_pos("Saturn")
        north_node_sign = _sign_from_pos("North Node")
        south_node_sign = _sign_from_pos("South Node")

        trail_sections.append({
            "title": "Planetary Positions",
            "content": (
                "; ".join(
                    f"{p}: {longitude_to_sign(positions[p])}"
                    for p in ("Mercury", "Venus", "Mars", "Jupiter", "Saturn",
                               "Uranus", "Neptune", "Pluto", "North Node")
                    if positions.get(p) is not None
                ) or "Planetary positions unavailable."
            ),
            "available": bool(positions),
        })

        # ── Aspects ───────────────────────────────────────────────────────────
        aspects: list[dict] = []
        if positions:
            aspects = compute_aspects(positions)
            if aspects:
                available_findings.append("aspects")

        trail_sections.append({
            "title": "Aspects",
            "content": (
                "; ".join(
                    f"{a['planet1']} {a['aspect']} {a['planet2']} (orb {a['orb']}°)"
                    for a in aspects
                ) or "No major aspects within 8° orb."
            ),
            "available": bool(aspects),
        })

        # ── Rising sign, houses, midheaven (exact tier only) ──────────────────
        rising_sign: Optional[str] = None
        rising_sign_available = False
        houses_dict: dict = {
            "1st": None, "2nd": None, "3rd": None, "4th": None,
            "5th": None, "6th": None, "7th": None, "8th": None,
            "9th": None, "10th": None, "11th": None, "12th": None,
        }
        midheaven: Optional[str] = None
        midheaven_available = False
        whole_sign_fallback_used = False

        if tier == "exact" and _SWE_AVAILABLE and birth_jd is not None:
            lat, lon, coords_found = _get_coords(birth_location)
            if not coords_found:
                confidence_issues.append(
                    f"Birth location '{birth_location.get('city', '')}' not found — "
                    "rising sign omitted."
                )
                unavailable_findings.extend(["rising_sign", "houses", "midheaven"])
                trail_sections.append({
                    "title": "Rising Sign",
                    "content": (
                        f"Rising sign unavailable — location "
                        f"'{birth_location.get('city', '')}' not found."
                    ),
                    "available": False,
                })
            else:
                computed_houses, rising, mc, used_fallback = compute_houses(birth_jd, lat, lon)
                whole_sign_fallback_used = used_fallback

                if rising:
                    rising_sign = rising
                    rising_sign_available = True
                    midheaven = mc
                    midheaven_available = mc is not None
                    houses_dict = computed_houses
                    available_findings.extend(["rising_sign", "houses", "midheaven"])
                    if used_fallback:
                        confidence_issues.append(
                            f"Latitude {lat:.1f}° exceeds 66° — "
                            "Placidus house system not valid; whole sign system used."
                        )
                    trail_sections.append({
                        "title": "Rising Sign",
                        "content": (
                            f"Rising sign: {rising_sign}"
                            + (" (Placidus)" if not used_fallback else " (whole sign — Placidus not valid at this latitude)")
                            + f". Midheaven: {midheaven}."
                        ),
                        "available": True,
                    })
                else:
                    unavailable_findings.extend(["rising_sign", "houses", "midheaven"])
                    trail_sections.append({
                        "title": "Rising Sign",
                        "content": "Rising sign unavailable — house calculation failed.",
                        "available": False,
                    })
        else:
            if tier != "exact":
                unavailable_findings.extend(["rising_sign", "houses", "midheaven"])
            trail_sections.append({
                "title": "Rising Sign",
                "content": (
                    f"Rising sign unavailable — birth time tier is '{tier}'. "
                    "Exact birth time required."
                ),
                "available": False,
            })

        # ── Houses trail (combined in rising sign section above) ──────────────
        trail_sections.append({
            "title": "Houses",
            "content": (
                "; ".join(f"{k}: {v}" for k, v in houses_dict.items() if v is not None)
                if rising_sign_available
                else f"Houses unavailable — birth time tier is '{tier}'."
            ),
            "available": rising_sign_available,
        })

        trail_sections.append({
            "title": "Midheaven",
            "content": (
                f"Midheaven (MC): {midheaven}." if midheaven
                else f"Midheaven unavailable — tier is '{tier}'."
            ),
            "available": midheaven_available,
        })

        # ── Chart pattern ─────────────────────────────────────────────────────
        chart_pattern: Optional[str] = None
        if positions:
            chart_pattern = detect_chart_pattern(positions)
            if chart_pattern:
                available_findings.append("chart_pattern")

        trail_sections.append({
            "title": "Chart Pattern",
            "content": (
                f"Chart pattern: {chart_pattern}." if chart_pattern
                else "Chart pattern unavailable — insufficient planetary data."
            ),
            "available": chart_pattern is not None,
        })

        # ── Current transits ──────────────────────────────────────────────────
        current_transits: list[dict] = []
        if _SWE_AVAILABLE and positions:
            try:
                today_jd = swe.julday(today.year, today.month, today.day, 0.0)
                current_transits = compute_current_transits(positions, today_jd)
                if current_transits:
                    available_findings.append("transits")
            except Exception:
                pass

        trail_sections.append({
            "title": "Current Transits",
            "content": (
                "; ".join(t["transit_note"] for t in current_transits)
                if current_transits
                else "No significant transits (within 3° orb) at this time."
            ),
            "available": bool(current_transits),
        })

        # ── Tendency window ───────────────────────────────────────────────────
        tendency_window: Optional[dict] = None
        if _SWE_AVAILABLE and positions and birth_jd is not None:
            try:
                today_jd = swe.julday(today.year, today.month, today.day, 0.0)
                tendency_window = compute_tendency_window(positions, today_jd, today)
            except Exception:
                tendency_window = None

        # ── Query-relevant findings ───────────────────────────────────────────
        query_relevant = build_query_relevant_findings(
            query=query,
            sun_sign=sun_sign,
            moon_sign=moon_sign,
            positions=positions,
            houses=houses_dict,
            rising_sign=rising_sign,
            chart_pattern=chart_pattern,
            transits=current_transits,
            north_node_sign=north_node_sign,
            midheaven=midheaven,
        )
        available_findings.append("query_relevant_findings")

        trail_sections.append({
            "title": "Query-Relevant Findings",
            "content": "; ".join(
                f"{item['finding']}: {item['value']}" for item in query_relevant
            ),
            "available": True,
        })

        # ── Confidence ────────────────────────────────────────────────────────
        if tier in ("approximate", "none"):
            confidence_flag = True
            if not any("tier" in issue for issue in confidence_issues):
                confidence_issues.append(
                    f"Birth time tier '{tier}' — rising sign, houses, and midheaven unavailable."
                )
        elif confidence_issues:
            confidence_flag = True
        else:
            confidence_flag = False

        confidence_reason = " ".join(confidence_issues) if confidence_issues else None

        # ── Assemble output ───────────────────────────────────────────────────
        findings: dict = {
            "sun_sign": sun_sign,
            "sun_sign_certain": sun_sign_certain,
            "moon_sign": moon_sign,
            "moon_sign_certain": moon_sign_certain,
            "rising_sign": rising_sign,
            "rising_sign_available": rising_sign_available,
            "mercury_sign": mercury_sign,
            "venus_sign": venus_sign,
            "mars_sign": mars_sign,
            "jupiter_sign": jupiter_sign,
            "saturn_sign": saturn_sign,
            "north_node_sign": north_node_sign,
            "south_node_sign": south_node_sign,
            "houses": houses_dict,
            "midheaven": midheaven,
            "midheaven_available": midheaven_available,
            "aspects": aspects,
            "current_transits": current_transits,
            "chart_pattern": chart_pattern,
            "query_relevant_findings": query_relevant,
            "tendency_window_weeks": tendency_window,
        }

        return {
            "head": "western",
            "available_findings": available_findings,
            "unavailable_findings": unavailable_findings,
            "findings": findings,
            "confidence_flag": confidence_flag,
            "confidence_reason": confidence_reason,
            "explainability_trail": {
                "label": "Western astrology",
                "sections": trail_sections,
            },
        }
