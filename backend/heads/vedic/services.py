"""
S-05 — Vedic Astrology Head Engine

Computes Vedic astrological findings across all available dimensions.
Uses pyswisseph (Swiss Ephemeris) with Lahiri ayanamsha for sidereal zodiac.

Done condition (from spec):
  All three tiers produce valid output. query_relevant_findings always has
  at least one entry. Tendency window always in weeks or null. Unavailable
  findings explicitly listed. Trail complete regardless of availability.
  Confidence flag correctly set.
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
# Absolute path derived from this file's location: backend/heads/vedic/services.py
# → parent.parent.parent = backend/  → backend/ephe
_EPH_PATH = str(Path(__file__).resolve().parent.parent.parent / "ephe")

# ── Zodiac signs ──────────────────────────────────────────────────────────────
SIGNS: list[str] = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

# ── Sign lords (classical Vedic — no outer planets) ───────────────────────────
_SIGN_LORDS: dict[str, str] = {
    "Aries": "Mars", "Taurus": "Venus", "Gemini": "Mercury", "Cancer": "Moon",
    "Leo": "Sun", "Virgo": "Mercury", "Libra": "Venus", "Scorpio": "Mars",
    "Sagittarius": "Jupiter", "Capricorn": "Saturn", "Aquarius": "Saturn",
    "Pisces": "Jupiter",
}

# ── Nakshatras (27 × 13°20') ──────────────────────────────────────────────────
NAKSHATRAS: list[str] = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni",
    "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha",
    "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana",
    "Dhanishtha", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati",
]

NAKSHATRA_SPAN: float = 360.0 / 27          # ≈ 13.333°
PADA_SPAN: float = NAKSHATRA_SPAN / 4       # ≈ 3.333°

# ── Vimshottari dasha sequence ────────────────────────────────────────────────
VIMSHOTTARI_SEQUENCE: list[tuple[str, int]] = [
    ("Ketu", 7), ("Venus", 20), ("Sun", 6), ("Moon", 10), ("Mars", 7),
    ("Rahu", 18), ("Jupiter", 16), ("Saturn", 19), ("Mercury", 17),
]
VIMSHOTTARI_TOTAL: int = 120  # years

# Each nakshatra maps to a dasha lord (cycles through 9-planet sequence)
NAKSHATRA_LORDS: list[str] = [VIMSHOTTARI_SEQUENCE[i % 9][0] for i in range(27)]

# ── Planet IDs for pyswisseph ─────────────────────────────────────────────────
if _SWE_AVAILABLE:
    _PLANET_IDS: dict[str, int] = {
        "sun": swe.SUN,
        "moon": swe.MOON,
        "mars": swe.MARS,
        "mercury": swe.MERCURY,
        "jupiter": swe.JUPITER,
        "venus": swe.VENUS,
        "saturn": swe.SATURN,
    }

# ── City geocoding (lat, lon) ─────────────────────────────────────────────────
_CITY_COORDS: dict[str, tuple[float, float]] = {
    "cuttack": (20.462, 85.883), "bhubaneswar": (20.296, 85.825),
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
}


# ── Pure math helpers ─────────────────────────────────────────────────────────

def longitude_to_sign(longitude: float) -> str:
    """Convert ecliptic longitude (0–360) to zodiac sign name."""
    return SIGNS[int(longitude / 30) % 12]


def nakshatra_index(longitude: float) -> int:
    """Return nakshatra index (0–26) for an ecliptic longitude."""
    return int(longitude / NAKSHATRA_SPAN) % 27


def nakshatra_pada(longitude: float) -> int:
    """Return pada (1–4) within the nakshatra for an ecliptic longitude."""
    pos_within = longitude % NAKSHATRA_SPAN
    return int(pos_within / PADA_SPAN) + 1


def _get_coords(birth_location: dict) -> tuple[float, float, bool]:
    """Resolve birth location to (lat, lon, found)."""
    city = (birth_location.get("city") or "").lower().strip()
    country = (birth_location.get("country") or "").lower().strip()
    if city and city in _CITY_COORDS:
        return (*_CITY_COORDS[city], True)
    if country and country in _COUNTRY_COORDS:
        return (*_COUNTRY_COORDS[country], True)
    return (0.0, 0.0, False)


# ── Bhava computation ─────────────────────────────────────────────────────────

def compute_bhavas(lagna_sign: str) -> list[dict]:
    """
    Compute all 12 bhavas (whole sign house system).
    Lagna sign = 1st bhava; each subsequent sign = next bhava.
    """
    lagna_idx = SIGNS.index(lagna_sign)
    return [
        {
            "bhava": i + 1,
            "sign": SIGNS[(lagna_idx + i) % 12],
            "lord": _SIGN_LORDS[SIGNS[(lagna_idx + i) % 12]],
        }
        for i in range(12)
    ]


def _get_bhava_lord(bhavas: list[dict], bhava_num: int) -> Optional[str]:
    """Return the lord of a given bhava number, or None."""
    for b in bhavas:
        if b["bhava"] == bhava_num:
            return b["lord"]
    return None


# ── Vimshottari dasha ─────────────────────────────────────────────────────────

def _compute_antardashas(
    mahadasha_planet: str, start: date, total_years: float
) -> list[dict]:
    """Compute antardasha sub-periods within a mahadasha."""
    start_pos = next(
        i for i, (name, _) in enumerate(VIMSHOTTARI_SEQUENCE) if name == mahadasha_planet
    )
    total_days = total_years * 365.25
    antardashas: list[dict] = []
    current = start
    for i in range(9):
        planet_name, dasha_years = VIMSHOTTARI_SEQUENCE[(start_pos + i) % 9]
        fraction = dasha_years / VIMSHOTTARI_TOTAL
        duration_days = int(total_days * fraction)
        end = current + timedelta(days=duration_days)
        antardashas.append({
            "planet": planet_name,
            "start_date": current.isoformat(),
            "end_date": end.isoformat(),
        })
        current = end
    return antardashas


def compute_vimshottari_sequence(
    moon_longitude: float, birth_date: date
) -> list[dict]:
    """
    Compute the Vimshottari dasha sequence starting from birth.

    The moon's nakshatra determines the first dasha lord. The fraction of the
    nakshatra already traversed at birth gives the remaining years in that dasha.
    """
    nak_idx = nakshatra_index(moon_longitude)
    lord_name = NAKSHATRA_LORDS[nak_idx]
    lord_pos = next(
        i for i, (name, _) in enumerate(VIMSHOTTARI_SEQUENCE) if name == lord_name
    )

    pos_within_nakshatra = moon_longitude % NAKSHATRA_SPAN
    fraction_elapsed = pos_within_nakshatra / NAKSHATRA_SPAN
    first_dasha_years = VIMSHOTTARI_SEQUENCE[lord_pos][1]
    days_elapsed = int(fraction_elapsed * first_dasha_years * 365.25)
    dasha_start = birth_date - timedelta(days=days_elapsed)

    dashas: list[dict] = []
    seq_pos = lord_pos
    current_start = dasha_start

    for _ in range(9):
        planet_name, duration_years = VIMSHOTTARI_SEQUENCE[seq_pos % 9]
        duration_days = int(duration_years * 365.25)
        current_end = current_start + timedelta(days=duration_days)
        dashas.append({
            "planet": planet_name,
            "start_date": current_start.isoformat(),
            "end_date": current_end.isoformat(),
            "duration_years": duration_years,
            "antardashas": _compute_antardashas(planet_name, current_start, duration_years),
        })
        current_start = current_end
        seq_pos += 1

    return dashas


def _find_current_dasha(dashas: list[dict], today: date) -> Optional[dict]:
    """Return the dasha period that contains today."""
    for d in dashas:
        if date.fromisoformat(d["start_date"]) <= today < date.fromisoformat(d["end_date"]):
            return d
    return None


def _find_current_antardasha(dasha: dict, today: date) -> Optional[dict]:
    """Return the antardasha within the current dasha that contains today."""
    for a in dasha.get("antardashas", []):
        if date.fromisoformat(a["start_date"]) <= today < date.fromisoformat(a["end_date"]):
            return a
    return None


# ── Yoga detection ────────────────────────────────────────────────────────────

def detect_yogas(
    sign_positions: dict[str, str],
    bhavas: Optional[list[dict]],
    lagna_sign: Optional[str],
) -> list[dict]:
    """
    Detect common Vedic yogas from planetary sign positions.

    Returns list of {name, description, planets_involved}.
    """
    yogas: list[dict] = []

    # Gajakesari Yoga: Jupiter in kendra (1, 4, 7, 10) from Moon
    moon_sign = sign_positions.get("moon")
    jupiter_sign = sign_positions.get("jupiter")
    if moon_sign and jupiter_sign and moon_sign in SIGNS and jupiter_sign in SIGNS:
        moon_idx = SIGNS.index(moon_sign)
        jupiter_idx = SIGNS.index(jupiter_sign)
        diff = (jupiter_idx - moon_idx) % 12
        if diff in (0, 3, 6, 9):
            yogas.append({
                "name": "Gajakesari Yoga",
                "description": "Jupiter in kendra from Moon — wisdom, recognition, prosperity.",
                "planets_involved": ["Jupiter", "Moon"],
            })

    # Budha-Aditya Yoga: Sun and Mercury conjunct
    sun_sign = sign_positions.get("sun")
    mercury_sign = sign_positions.get("mercury")
    if sun_sign and mercury_sign and sun_sign == mercury_sign:
        yogas.append({
            "name": "Budha-Aditya Yoga",
            "description": "Sun and Mercury conjunct — intelligence, communication, career success.",
            "planets_involved": ["Sun", "Mercury"],
        })

    # Chandra-Mangal Yoga: Moon and Mars conjunct
    mars_sign = sign_positions.get("mars")
    if moon_sign and mars_sign and moon_sign == mars_sign:
        yogas.append({
            "name": "Chandra-Mangal Yoga",
            "description": "Moon and Mars conjunct — ambition, drive, material pursuit.",
            "planets_involved": ["Moon", "Mars"],
        })

    # Raj Yoga (partial): Jupiter or Venus in kendra from lagna
    if bhavas and lagna_sign:
        kendra_signs = {b["sign"] for b in bhavas if b["bhava"] in (1, 4, 7, 10)}
        for planet in ("Jupiter", "Venus"):
            p_sign = sign_positions.get(planet.lower())
            if p_sign and p_sign in kendra_signs:
                yogas.append({
                    "name": f"Raj Yoga (partial — {planet})",
                    "description": f"{planet} in a kendra from lagna — authority, prestige.",
                    "planets_involved": [planet],
                })
                break  # one instance sufficient

    return yogas


# ── Transit detection ─────────────────────────────────────────────────────────

def compute_transits(natal_positions: dict[str, Optional[str]], today_jd: float) -> list[dict]:
    """
    Compute current transits of slow-moving planets (Saturn, Jupiter, Rahu)
    against natal sign positions.
    """
    if not _SWE_AVAILABLE:
        return []

    transits: list[dict] = []
    slow_planets = [("saturn", swe.SATURN), ("jupiter", swe.JUPITER)]
    swe.set_sid_mode(swe.SIDM_LAHIRI)

    for planet_name, planet_id in slow_planets:
        try:
            result, _ = swe.calc_ut(today_jd, planet_id, swe.FLG_SIDEREAL)
            current_sign = longitude_to_sign(result[0] % 360.0)
            natal_sign = natal_positions.get(planet_name)
            transits.append({
                "planet": planet_name.capitalize(),
                "natal_sign": natal_sign,
                "current_sign": current_sign,
                "transit_note": (
                    f"{planet_name.capitalize()} transiting {current_sign}"
                    + (f" (natal: {natal_sign})" if natal_sign and natal_sign != current_sign else "")
                ),
            })
        except Exception:
            pass

    # Rahu transit
    try:
        result, _ = swe.calc_ut(today_jd, swe.MEAN_NODE, swe.FLG_SIDEREAL)
        rahu_sign = longitude_to_sign(result[0] % 360.0)
        natal_rahu = natal_positions.get("rahu")
        transits.append({
            "planet": "Rahu",
            "natal_sign": natal_rahu,
            "current_sign": rahu_sign,
            "transit_note": (
                f"Rahu transiting {rahu_sign}"
                + (f" (natal: {natal_rahu})" if natal_rahu and natal_rahu != rahu_sign else "")
            ),
        })
    except Exception:
        pass

    return transits


# ── Query relevance mapping ───────────────────────────────────────────────────

_CAREER_KW = frozenset({"career", "job", "work", "business", "professional", "promotion", "salary"})
_RELATIONSHIP_KW = frozenset({"relationship", "love", "marriage", "partner", "romantic", "spouse"})
_FINANCE_KW = frozenset({"finance", "money", "wealth", "investment", "income", "financial"})
_HEALTH_KW = frozenset({"health", "illness", "wellness", "body", "disease", "medical"})
_TRAVEL_KW = frozenset({"travel", "move", "relocate", "abroad", "foreign", "journey", "relocation"})
_DIRECTION_KW = frozenset({"direction", "purpose", "path", "life", "future", "guidance", "general"})


def build_query_relevant_findings(
    query: str,
    rashi: Optional[str],
    nakshatra: Optional[str],
    planetary_positions: dict[str, Optional[str]],
    bhavas: Optional[list[dict]],
    current_dasha: Optional[dict],
    current_antardasha: Optional[dict],
    yogas: list[dict],
) -> list[dict]:
    """
    Build query-relevant findings list. Never returns an empty list.

    Spec mapping:
    Career      → 10th bhava lord, Saturn, Sun, current dasha
    Relationships → 7th bhava lord, Venus, Jupiter, dasha
    Finances    → 2nd + 11th bhava lords, Jupiter, Venus
    Health      → 1st + 6th bhava lords, Mars, Saturn transits
    Travel      → 9th + 12th bhava lords, Rahu, transits
    Direction   → lagna lord, dasha + antardasha, yogas
    No match    → dasha + antardasha, rashi, nakshatra
    """
    tokens = set(re.split(r"\W+", (query or "").lower()))
    relevant: list[dict] = []

    def _dasha_entry() -> dict:
        if current_dasha:
            return {
                "finding": "current_dasha",
                "value": current_dasha["planet"],
                "note": f"Mahadasha of {current_dasha['planet']} until {current_dasha['end_date']}.",
            }
        return {
            "finding": "rashi",
            "value": rashi,
            "note": f"Rashi (moon sign): {rashi}.",
        }

    def _antardasha_entry() -> Optional[dict]:
        if current_antardasha:
            return {
                "finding": "current_antardasha",
                "value": current_antardasha["planet"],
                "note": (
                    f"Antardasha of {current_antardasha['planet']} "
                    f"until {current_antardasha['end_date']}."
                ),
            }
        return None

    def _bhava_lord_entry(bhava_num: int, label: str) -> Optional[dict]:
        if bhavas:
            lord = _get_bhava_lord(bhavas, bhava_num)
            if lord:
                return {
                    "finding": f"bhava_{bhava_num}_lord",
                    "value": lord,
                    "note": f"{label} (bhava {bhava_num}) lord: {lord}.",
                }
        return None

    def _planet_entry(planet: str, note: str) -> dict:
        sign = planetary_positions.get(planet.lower())
        return {
            "finding": planet.lower(),
            "value": sign or "unavailable",
            "note": note + (f" In {sign}." if sign else " Position unavailable."),
        }

    if tokens & _CAREER_KW:
        lord = _bhava_lord_entry(10, "Career")
        if lord:
            relevant.append(lord)
        relevant.append(_planet_entry("Saturn", "Saturn — career and discipline."))
        relevant.append(_planet_entry("Sun", "Sun — authority and career."))
        relevant.append(_dasha_entry())

    elif tokens & _RELATIONSHIP_KW:
        lord = _bhava_lord_entry(7, "Relationships")
        if lord:
            relevant.append(lord)
        relevant.append(_planet_entry("Venus", "Venus — relationships and harmony."))
        relevant.append(_planet_entry("Jupiter", "Jupiter — growth and marriage."))
        relevant.append(_dasha_entry())

    elif tokens & _FINANCE_KW:
        lord_2 = _bhava_lord_entry(2, "Finances (2nd)")
        lord_11 = _bhava_lord_entry(11, "Gains (11th)")
        if lord_2:
            relevant.append(lord_2)
        if lord_11:
            relevant.append(lord_11)
        relevant.append(_planet_entry("Jupiter", "Jupiter — wealth and expansion."))
        relevant.append(_planet_entry("Venus", "Venus — luxury and accumulation."))

    elif tokens & _HEALTH_KW:
        lord_1 = _bhava_lord_entry(1, "Self (1st)")
        lord_6 = _bhava_lord_entry(6, "Health (6th)")
        if lord_1:
            relevant.append(lord_1)
        if lord_6:
            relevant.append(lord_6)
        relevant.append(_planet_entry("Mars", "Mars — vitality and energy."))
        relevant.append(_planet_entry("Saturn", "Saturn — chronic conditions."))

    elif tokens & _TRAVEL_KW:
        lord_9 = _bhava_lord_entry(9, "Long travel (9th)")
        lord_12 = _bhava_lord_entry(12, "Foreign (12th)")
        if lord_9:
            relevant.append(lord_9)
        if lord_12:
            relevant.append(lord_12)
        relevant.append(_planet_entry("Rahu", "Rahu — foreign connections and travel."))
        relevant.append(_dasha_entry())

    elif tokens & _DIRECTION_KW:
        lagna_lord = _get_bhava_lord(bhavas, 1) if bhavas else None
        if lagna_lord:
            relevant.append({
                "finding": "lagna_lord",
                "value": lagna_lord,
                "note": f"Lagna lord {lagna_lord} — personal direction and identity.",
            })
        relevant.append(_dasha_entry())
        ad = _antardasha_entry()
        if ad:
            relevant.append(ad)
        for yoga in yogas[:2]:
            relevant.append({
                "finding": "yoga",
                "value": yoga["name"],
                "note": yoga["description"],
            })

    # General direction / no keyword match
    if not relevant:
        relevant.append(_dasha_entry())
        ad = _antardasha_entry()
        if ad:
            relevant.append(ad)
        relevant.append({
            "finding": "rashi",
            "value": rashi,
            "note": f"Rashi (moon sign): {rashi}.",
        })
        relevant.append({
            "finding": "nakshatra",
            "value": nakshatra,
            "note": f"Nakshatra: {nakshatra}.",
        })

    # Spec: query_relevant_findings never empty
    if not relevant:
        relevant.append({
            "finding": "rashi",
            "value": rashi,
            "note": f"Rashi (moon sign): {rashi}.",
        })

    return relevant


# ── Tendency window ───────────────────────────────────────────────────────────

def compute_tendency_window(
    current_dasha: Optional[dict],
    current_antardasha: Optional[dict],
    today: date,
) -> Optional[dict]:
    """
    Compute tendency window from dasha/antardasha end dates, expressed in weeks.
    Returns None if neither is available.
    """
    if not current_dasha and not current_antardasha:
        return None

    if current_antardasha:
        ad_end = date.fromisoformat(current_antardasha["end_date"])
        ad_weeks = max(1, round((ad_end - today).days / 7))
    else:
        ad_weeks = 4  # fallback: 4 weeks minimum

    if current_dasha:
        maha_end = date.fromisoformat(current_dasha["end_date"])
        maha_weeks = max(ad_weeks, round((maha_end - today).days / 7))
    else:
        maha_weeks = ad_weeks

    return {"min": ad_weeks, "max": maha_weeks}


# ── Main engine ───────────────────────────────────────────────────────────────

class VedicHeadEngine:
    """
    S-05 Vedic Astrology Head Engine.

    Uses pyswisseph with Lahiri ayanamsha for all planetary calculations.
    Rashi (moon sign) is taken from S-03 output.
    Exact tier: full computation including lagna, bhavas, transits.
    Approximate / none tiers: lagna and bhavas omitted, confidence_flag = True.
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
        Compute Vedic astrology findings.

        Args:
            dob: {"day": int, "month": int, "year": int}
            birth_time: {"tier": str, "normalised_time": str|None, ...}
            birth_location: {"city": str, "country": str}
            gender: optional
            moon: {"moon_sign": str, "moon_sign_certain": bool,
                   "transition_occurred": bool}
            query: user question string
            today: date override for testing

        Returns:
            S-05 contract output dict.
        """
        if today is None:
            today = date.today()

        tier = birth_time.get("tier", "none")
        normalised_time = birth_time.get("normalised_time")

        birth_date = date(dob["year"], dob["month"], dob["day"])

        available_findings: list[str] = []
        unavailable_findings: list[str] = []
        confidence_issues: list[str] = []
        trail_sections: list[dict] = []

        # ── Initialise ephemeris ──────────────────────────────────────────────
        if _SWE_AVAILABLE:
            swe.set_ephe_path(_EPH_PATH)
            swe.set_sid_mode(swe.SIDM_LAHIRI)

        # ── Julian day for birth ──────────────────────────────────────────────
        birth_hour = 0.0
        if normalised_time:
            try:
                h, m = normalised_time.split(":")
                birth_hour = int(h) + int(m) / 60.0
            except (ValueError, AttributeError):
                birth_hour = 0.0

        birth_jd: Optional[float] = None
        if _SWE_AVAILABLE:
            try:
                birth_jd = swe.julday(dob["year"], dob["month"], dob["day"], birth_hour)
            except Exception:
                birth_jd = None

        # ── Rashi from S-03 ───────────────────────────────────────────────────
        rashi = moon.get("moon_sign")
        rashi_certain = moon.get("moon_sign_certain", True)
        available_findings.append("rashi")
        trail_sections.append({
            "title": "Rashi (Moon Sign)",
            "content": (
                f"Rashi: {rashi}."
                + ("" if rashi_certain else " Moon sign uncertain — born near sign boundary.")
            ),
            "available": True,
        })

        # ── Planetary positions (sidereal, Lahiri) ────────────────────────────
        planetary_positions: dict[str, Optional[str]] = {
            p: None for p in ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn", "rahu", "ketu")
        }
        moon_longitude: Optional[float] = None

        if _SWE_AVAILABLE and birth_jd is not None:
            for planet_name, planet_id in _PLANET_IDS.items():
                try:
                    result, _ = swe.calc_ut(birth_jd, planet_id, swe.FLG_SIDEREAL)
                    lon = result[0] % 360.0
                    planetary_positions[planet_name] = longitude_to_sign(lon)
                    if planet_name == "moon":
                        moon_longitude = lon
                except Exception:
                    planetary_positions[planet_name] = None

            # Rahu (mean north node) and Ketu (always 180° from Rahu)
            try:
                result, _ = swe.calc_ut(birth_jd, swe.MEAN_NODE, swe.FLG_SIDEREAL)
                rahu_lon = result[0] % 360.0
                ketu_lon = (rahu_lon + 180.0) % 360.0
                planetary_positions["rahu"] = longitude_to_sign(rahu_lon)
                planetary_positions["ketu"] = longitude_to_sign(ketu_lon)
            except Exception:
                planetary_positions["rahu"] = None
                planetary_positions["ketu"] = None

            available_findings.append("planetary_positions")
        else:
            confidence_issues.append(
                "Swiss Ephemeris unavailable — planetary positions not computed."
            )
            unavailable_findings.append("planetary_positions")

        # If swe moon longitude not available, estimate from rashi for nakshatra
        if moon_longitude is None and rashi and rashi in SIGNS:
            rashi_idx = SIGNS.index(rashi)
            moon_longitude = rashi_idx * 30.0 + 15.0  # midpoint of sign
            confidence_issues.append(
                "Moon longitude estimated from rashi — nakshatra position approximate."
            )

        # ── Nakshatra and pada ────────────────────────────────────────────────
        nak_name: Optional[str] = None
        nak_pada: Optional[int] = None

        if moon_longitude is not None:
            nak_idx = nakshatra_index(moon_longitude)
            nak_name = NAKSHATRAS[nak_idx]
            nak_pada = nakshatra_pada(moon_longitude)
            available_findings.append("nakshatra")

        trail_sections.append({
            "title": "Nakshatra",
            "content": (
                f"Nakshatra: {nak_name}, Pada {nak_pada}. "
                f"Nakshatra lord: {NAKSHATRA_LORDS[nakshatra_index(moon_longitude)]}."
                if nak_name and moon_longitude is not None
                else "Nakshatra: unavailable (moon longitude not computed)."
            ),
            "available": nak_name is not None,
        })

        # ── Lagna (exact tier only) ───────────────────────────────────────────
        lagna_sign: Optional[str] = None
        lagna_available = False
        bhavas: Optional[list[dict]] = None

        if tier == "exact" and _SWE_AVAILABLE and birth_jd is not None:
            lat, lon, coords_found = _get_coords(birth_location)
            if not coords_found:
                confidence_issues.append(
                    f"Birth location '{birth_location.get('city', '')}' not found — lagna omitted."
                )
                unavailable_findings.append("lagna")
                unavailable_findings.append("bhavas")
                trail_sections.append({
                    "title": "Lagna (Ascendant)",
                    "content": (
                        f"Lagna unavailable — location '{birth_location.get('city', '')}' "
                        "not found in geocoding lookup."
                    ),
                    "available": False,
                })
            else:
                try:
                    # Compute tropical ASC then subtract ayanamsha for sidereal
                    cusps, ascmc = swe.houses(birth_jd, lat, lon, b"W")
                    ayanamsha = swe.get_ayanamsa_ut(birth_jd)
                    asc_sidereal = (ascmc[0] - ayanamsha) % 360.0
                    lagna_sign = longitude_to_sign(asc_sidereal)
                    lagna_available = True
                    bhavas = compute_bhavas(lagna_sign)
                    available_findings.append("lagna")
                    available_findings.append("bhavas")
                    trail_sections.append({
                        "title": "Lagna (Ascendant)",
                        "content": (
                            f"Lagna: {lagna_sign}. "
                            f"Computed from birth time {normalised_time} at "
                            f"{birth_location.get('city', 'unknown')}."
                        ),
                        "available": True,
                    })
                except Exception as exc:
                    confidence_issues.append(f"Lagna calculation failed: {exc}")
                    unavailable_findings.append("lagna")
                    unavailable_findings.append("bhavas")
                    trail_sections.append({
                        "title": "Lagna (Ascendant)",
                        "content": f"Lagna unavailable — calculation error: {exc}",
                        "available": False,
                    })
        else:
            if tier != "exact":
                unavailable_findings.append("lagna")
                unavailable_findings.append("bhavas")
            trail_sections.append({
                "title": "Lagna (Ascendant)",
                "content": (
                    f"Lagna unavailable — birth time tier is '{tier}'. "
                    "Exact birth time required for ascendant calculation."
                ),
                "available": False,
            })

        # ── Vimshottari dasha ─────────────────────────────────────────────────
        dasha_sequence: list[dict] = []
        current_dasha: Optional[dict] = None
        current_antardasha: Optional[dict] = None

        if moon_longitude is not None:
            try:
                dasha_sequence = compute_vimshottari_sequence(moon_longitude, birth_date)
                current_dasha = _find_current_dasha(dasha_sequence, today)
                if current_dasha:
                    current_antardasha = _find_current_antardasha(current_dasha, today)
                available_findings.append("dasha")
                if tier in ("approximate", "none"):
                    confidence_issues.append(
                        f"Birth time tier '{tier}' — dasha computed from nakshatra only, approximate."
                    )
            except Exception as exc:
                confidence_issues.append(f"Dasha calculation failed: {exc}")
                unavailable_findings.append("dasha")

        trail_sections.append({
            "title": "Current Dasha",
            "content": (
                f"Mahadasha: {current_dasha['planet']} "
                f"({current_dasha['start_date']} → {current_dasha['end_date']})."
                if current_dasha
                else "Dasha unavailable — moon longitude not computed."
            ),
            "available": current_dasha is not None,
        })
        trail_sections.append({
            "title": "Antardasha",
            "content": (
                f"Antardasha: {current_antardasha['planet']} "
                f"({current_antardasha['start_date']} → {current_antardasha['end_date']})."
                if current_antardasha
                else "Antardasha unavailable."
            ),
            "available": current_antardasha is not None,
        })

        # ── Yogas ─────────────────────────────────────────────────────────────
        yogas: list[dict] = []
        sign_positions = {k: v for k, v in planetary_positions.items() if v is not None}
        if sign_positions:
            yogas = detect_yogas(sign_positions, bhavas, lagna_sign)
            if yogas:
                available_findings.append("yogas")

        trail_sections.append({
            "title": "Active Yogas",
            "content": (
                "; ".join(f"{y['name']}: {y['description']}" for y in yogas)
                if yogas
                else "No major yogas detected from available planetary data."
            ),
            "available": bool(yogas),
        })

        # ── Transits (exact tier only) ────────────────────────────────────────
        current_transits: list[dict] = []
        if _SWE_AVAILABLE and tier == "exact" and birth_jd is not None:
            try:
                today_jd = swe.julday(today.year, today.month, today.day, 0.0)
                current_transits = compute_transits(planetary_positions, today_jd)
                if current_transits:
                    available_findings.append("transits")
            except Exception:
                pass

        trail_sections.append({
            "title": "Current Transits",
            "content": (
                "; ".join(t["transit_note"] for t in current_transits)
                if current_transits
                else (
                    "Transits computed for exact tier only."
                    if tier != "exact"
                    else "No significant transits available."
                )
            ),
            "available": bool(current_transits),
        })

        # ── Query-relevant findings ───────────────────────────────────────────
        query_relevant = build_query_relevant_findings(
            query=query,
            rashi=rashi,
            nakshatra=nak_name,
            planetary_positions=planetary_positions,
            bhavas=bhavas,
            current_dasha=current_dasha,
            current_antardasha=current_antardasha,
            yogas=yogas,
        )
        available_findings.append("query_relevant_findings")

        trail_sections.append({
            "title": "Query-Relevant Findings",
            "content": "; ".join(
                f"{item['finding']}: {item['value']}" for item in query_relevant
            ),
            "available": True,
        })

        # ── Tendency window ───────────────────────────────────────────────────
        tendency_window = compute_tendency_window(current_dasha, current_antardasha, today)

        # ── Confidence ────────────────────────────────────────────────────────
        if tier in ("approximate", "none"):
            confidence_flag = True
            if not any("tier" in issue for issue in confidence_issues):
                confidence_issues.append(
                    f"Birth time tier '{tier}' — lagna and bhavas unavailable."
                )
        elif confidence_issues:
            confidence_flag = True
        else:
            confidence_flag = False

        confidence_reason = " ".join(confidence_issues) if confidence_issues else None

        # ── Assemble output ───────────────────────────────────────────────────
        findings: dict = {
            "rashi": rashi,
            "rashi_certain": rashi_certain,
            "lagna": lagna_sign,
            "lagna_available": lagna_available,
            "nakshatra": nak_name,
            "nakshatra_pada": nak_pada,
            "current_dasha": (
                {
                    "planet": current_dasha["planet"],
                    "start_date": current_dasha["start_date"],
                    "end_date": current_dasha["end_date"],
                }
                if current_dasha else None
            ),
            "current_antardasha": (
                {
                    "planet": current_antardasha["planet"],
                    "start_date": current_antardasha["start_date"],
                    "end_date": current_antardasha["end_date"],
                }
                if current_antardasha else None
            ),
            "active_bhavas": bhavas or [],
            "planetary_positions": {
                "sun": planetary_positions.get("sun"),
                "moon": planetary_positions.get("moon"),
                "mars": planetary_positions.get("mars"),
                "mercury": planetary_positions.get("mercury"),
                "jupiter": planetary_positions.get("jupiter"),
                "venus": planetary_positions.get("venus"),
                "saturn": planetary_positions.get("saturn"),
                "rahu": planetary_positions.get("rahu"),
                "ketu": planetary_positions.get("ketu"),
            },
            "yogas": yogas,
            "current_transits": current_transits,
            "query_relevant_findings": query_relevant,
            "tendency_window_weeks": tendency_window,
        }

        return {
            "head": "vedic",
            "available_findings": available_findings,
            "unavailable_findings": unavailable_findings,
            "findings": findings,
            "confidence_flag": confidence_flag,
            "confidence_reason": confidence_reason,
            "explainability_trail": {
                "label": "Vedic astrology",
                "sections": trail_sections,
            },
        }
