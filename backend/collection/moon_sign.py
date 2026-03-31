"""
S-03 — Moon Sign Ambiguity Resolution

Determines whether the moon changes signs on the user's birth date. If it
does and birth time is unknown or approximate, applies the majority-day rule
to assign a definitive moon sign. Flags the result for downstream heads and
the confidence note generator.

This module uses pyswisseph for all ephemeris calculations. The Moshier
built-in algorithm is used when no ephemeris data files are present.

Done condition (from spec):
  Every combination of birth time tier × moon transition scenario produces
  valid output. Majority-day rule applied only when window genuinely overlaps.
  Exact tier never uses majority-day rule. Location always used for local time
  calculation — UTC is fallback only.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import swisseph as swe

from .constants import TIER_APPROXIMATE, TIER_EXACT, TIER_NONE

log = logging.getLogger(__name__)

# ── Ephemeris setup ───────────────────────────────────────────────────────────

_EPHE_PATH = "./backend/ephe"
swe.set_ephe_path(_EPHE_PATH)

# ── Zodiac sign names (ecliptic order, 30° each) ─────────────────────────────

SIGN_NAMES: list[str] = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

# ── City → IANA timezone name lookup ─────────────────────────────────────────
# Key: (city_lower, country_lower). Falls back to UTC if not found.

CITY_TIMEZONE_MAP: dict[tuple[str, str], str] = {
    ("mumbai", "india"): "Asia/Kolkata",
    ("delhi", "india"): "Asia/Kolkata",
    ("new delhi", "india"): "Asia/Kolkata",
    ("kolkata", "india"): "Asia/Kolkata",
    ("bangalore", "india"): "Asia/Kolkata",
    ("hyderabad", "india"): "Asia/Kolkata",
    ("chennai", "india"): "Asia/Kolkata",
    ("pune", "india"): "Asia/Kolkata",
    ("london", "uk"): "Europe/London",
    ("london", "united kingdom"): "Europe/London",
    ("new york", "us"): "America/New_York",
    ("new york", "usa"): "America/New_York",
    ("new york", "united states"): "America/New_York",
    ("los angeles", "us"): "America/Los_Angeles",
    ("los angeles", "usa"): "America/Los_Angeles",
    ("chicago", "us"): "America/Chicago",
    ("chicago", "usa"): "America/Chicago",
    ("paris", "france"): "Europe/Paris",
    ("berlin", "germany"): "Europe/Berlin",
    ("tokyo", "japan"): "Asia/Tokyo",
    ("osaka", "japan"): "Asia/Tokyo",
    ("beijing", "china"): "Asia/Shanghai",
    ("shanghai", "china"): "Asia/Shanghai",
    ("singapore", "singapore"): "Asia/Singapore",
    ("sydney", "australia"): "Australia/Sydney",
    ("melbourne", "australia"): "Australia/Melbourne",
    ("dubai", "uae"): "Asia/Dubai",
    ("dubai", "united arab emirates"): "Asia/Dubai",
    ("toronto", "canada"): "America/Toronto",
    ("vancouver", "canada"): "America/Vancouver",
    ("moscow", "russia"): "Europe/Moscow",
    ("istanbul", "turkey"): "Europe/Istanbul",
    ("cairo", "egypt"): "Africa/Cairo",
    ("johannesburg", "south africa"): "Africa/Johannesburg",
    ("sao paulo", "brazil"): "America/Sao_Paulo",
    ("rio de janeiro", "brazil"): "America/Sao_Paulo",
    ("mexico city", "mexico"): "America/Mexico_City",
    ("amsterdam", "netherlands"): "Europe/Amsterdam",
    ("rome", "italy"): "Europe/Rome",
    ("madrid", "spain"): "Europe/Madrid",
    ("barcelona", "spain"): "Europe/Madrid",
    ("bangkok", "thailand"): "Asia/Bangkok",
    ("jakarta", "indonesia"): "Asia/Jakarta",
    ("karachi", "pakistan"): "Asia/Karachi",
    ("lahore", "pakistan"): "Asia/Karachi",
    ("dhaka", "bangladesh"): "Asia/Dhaka",
    ("tehran", "iran"): "Asia/Tehran",
    ("seoul", "south korea"): "Asia/Seoul",
    ("hong kong", "hong kong"): "Asia/Hong_Kong",
    ("taipei", "taiwan"): "Asia/Taipei",
    ("kuala lumpur", "malaysia"): "Asia/Kuala_Lumpur",
    ("kathmandu", "nepal"): "Asia/Kathmandu",
    ("colombo", "sri lanka"): "Asia/Colombo",
    ("nairobi", "kenya"): "Africa/Nairobi",
    ("lagos", "nigeria"): "Africa/Lagos",
    ("accra", "ghana"): "Africa/Accra",
    ("athens", "greece"): "Europe/Athens",
    ("stockholm", "sweden"): "Europe/Stockholm",
    ("oslo", "norway"): "Europe/Oslo",
    ("copenhagen", "denmark"): "Europe/Copenhagen",
    ("helsinki", "finland"): "Europe/Helsinki",
    ("zurich", "switzerland"): "Europe/Zurich",
    ("vienna", "austria"): "Europe/Vienna",
    ("prague", "czech republic"): "Europe/Prague",
    ("warsaw", "poland"): "Europe/Warsaw",
    ("budapest", "hungary"): "Europe/Budapest",
    ("bucharest", "romania"): "Europe/Bucharest",
    ("kyiv", "ukraine"): "Europe/Kyiv",
    ("riyadh", "saudi arabia"): "Asia/Riyadh",
    ("doha", "qatar"): "Asia/Qatar",
    ("muscat", "oman"): "Asia/Muscat",
    ("tashkent", "uzbekistan"): "Asia/Tashkent",
    ("almaty", "kazakhstan"): "Asia/Almaty",
    ("islamabad", "pakistan"): "Asia/Karachi",
}

# ── Confidence reason strings ─────────────────────────────────────────────────

_REASON_UTC_FALLBACK = (
    "Birth location could not be resolved to a timezone. UTC used as fallback — "
    "moon sign transition time may be off by several hours."
)
_REASON_MAJORITY_NONE = (
    "Birth time unknown. Moon changed signs on this date. "
    "Majority-day rule applied — sign assigned may not match actual birth sign."
)
_REASON_MAJORITY_APPROXIMATE = (
    "Approximate birth time window overlaps a moon sign transition. "
    "Majority-day rule applied — sign assigned may not match actual birth sign."
)
_REASON_UNUSUAL_DOUBLE = (
    "Moon changed signs twice on this date (unusual). "
    "Longest continuous block used."
)
_REASON_EPHEM_FAIL = "Ephemeris calculation failed — moon sign unavailable."

# ── Pure module-level helpers ─────────────────────────────────────────────────


def _longitude_to_sign_index(longitude: float) -> int:
    """Return 0-based sign index. 0 = Aries, 11 = Pisces."""
    return int(longitude / 30) % 12


def _longitude_to_sign_name(longitude: float) -> str:
    """Return sign name for an ecliptic longitude."""
    return SIGN_NAMES[_longitude_to_sign_index(longitude)]


def _hhmm_to_hours(hhmm: str) -> float:
    """
    Convert "HH:MM" to decimal hours.

    "00:00" → 0.0 (start of day / midnight)
    "23:59" → 23.983...
    """
    parts = hhmm.split(":")
    return int(parts[0]) + int(parts[1]) / 60.0


def _hhmm_end_to_hours(hhmm: str) -> float:
    """
    Convert a window_end "HH:MM" to decimal hours.

    "00:00" as an end boundary means midnight = end of day = 24.0.
    All other values convert normally.
    """
    if hhmm == "00:00":
        return 24.0
    return _hhmm_to_hours(hhmm)


def _hours_to_hhmm(hours: float) -> str:
    """Convert decimal hours to "HH:MM" string."""
    h = int(hours) % 24
    m = int(round((hours % 1) * 60))
    if m == 60:
        h = (h + 1) % 24
        m = 0
    return f"{h:02d}:{m:02d}"


def _local_to_jd(
    year: int, month: int, day: int, local_hour: float, utc_offset_hours: float
) -> float:
    """
    Convert a local date+time to a Julian Day number (UTC-based).

    local_hour is decimal hours (e.g. 10.5 = 10:30 AM local).
    utc_offset_hours is the signed UTC offset (e.g. +5.5 for IST).
    """
    utc_hour = local_hour - utc_offset_hours
    # Use datetime arithmetic to handle day rollovers gracefully
    dt_utc = datetime(year, month, day) + timedelta(hours=utc_hour)
    decimal_hour = dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0
    return swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, decimal_hour)


# ── Pure routing function ─────────────────────────────────────────────────────


def _apply_routing(
    *,
    sign_at_start: str,
    sign_at_end: str,
    transition_hour: Optional[float],
    majority_sign: Optional[str],
    minority_sign: Optional[str],
    majority_hours: Optional[float],
    tier: str,
    normalised_time: Optional[str],
    window_start: Optional[str],
    window_end: Optional[str],
    utc_fallback: bool,
    unusual_double_transition: bool = False,
) -> dict:
    """
    Pure routing logic — no ephemeris dependency.

    Implements the Step 3 routing rules from the S-03 contract.
    All inputs must be pre-computed by the caller. Never raises.
    """

    def _build(
        moon_sign: str,
        moon_sign_certain: bool,
        confidence_flag: bool,
        confidence_reason: Optional[str],
    ) -> dict:
        """Assemble the full S-03 output dict."""
        reasons: list[str] = []
        if confidence_reason:
            reasons.append(confidence_reason)
        if unusual_double_transition:
            reasons.append(_REASON_UNUSUAL_DOUBLE)
        if utc_fallback:
            reasons.append(_REASON_UTC_FALLBACK)
        return {
            "moon_sign": moon_sign,
            "moon_sign_certain": moon_sign_certain,
            "transition_occurred": transition_hour is not None,
            "transition_time_local": (
                _hours_to_hhmm(transition_hour) if transition_hour is not None else None
            ),
            "majority_sign": majority_sign,
            "minority_sign": minority_sign,
            "majority_hours": majority_hours,
            "confidence_flag": confidence_flag or utc_fallback or unusual_double_transition,
            "confidence_reason": " | ".join(reasons) if reasons else None,
        }

    # ── No transition ─────────────────────────────────────────────────────────
    if transition_hour is None:
        return _build(
            moon_sign=sign_at_start,
            moon_sign_certain=True,
            confidence_flag=utc_fallback,
            confidence_reason=None,
        )

    # ── Transition occurred — midnight edge case ───────────────────────────────
    # If transition_hour is effectively zero, the entire day belongs to sign_at_end.
    _MIDNIGHT_EPSILON = 1.0 / 60.0  # 1 minute
    if transition_hour <= _MIDNIGHT_EPSILON:
        return _build(
            moon_sign=sign_at_end,
            moon_sign_certain=True,
            confidence_flag=utc_fallback,
            confidence_reason=None,
        )

    # ── Exact tier ────────────────────────────────────────────────────────────
    if tier == TIER_EXACT:
        birth_hour = _hhmm_to_hours(normalised_time) if normalised_time else 0.0
        moon_sign = sign_at_start if birth_hour < transition_hour else sign_at_end
        return _build(
            moon_sign=moon_sign,
            moon_sign_certain=True,
            confidence_flag=utc_fallback,
            confidence_reason=None,
        )

    # ── Approximate tier ──────────────────────────────────────────────────────
    if tier == TIER_APPROXIMATE:
        ws = _hhmm_to_hours(window_start) if window_start else 0.0
        we = _hhmm_end_to_hours(window_end) if window_end else 24.0

        entirely_before = we <= transition_hour
        entirely_after = ws >= transition_hour

        if entirely_before:
            return _build(
                moon_sign=sign_at_start,
                moon_sign_certain=True,
                confidence_flag=utc_fallback,
                confidence_reason=None,
            )
        if entirely_after:
            return _build(
                moon_sign=sign_at_end,
                moon_sign_certain=True,
                confidence_flag=utc_fallback,
                confidence_reason=None,
            )
        # Window overlaps → majority-day rule
        return _build(
            moon_sign=majority_sign,
            moon_sign_certain=False,
            confidence_flag=True,
            confidence_reason=_REASON_MAJORITY_APPROXIMATE,
        )

    # ── None tier → majority-day rule unconditionally ────────────────────────
    return _build(
        moon_sign=majority_sign,
        moon_sign_certain=False,
        confidence_flag=True,
        confidence_reason=_REASON_MAJORITY_NONE,
    )


# ── Resolver class ────────────────────────────────────────────────────────────


class MoonSignResolver:
    """
    Resolves moon sign for a birth date, handling ambiguity when the moon
    transitions signs on that date.

    All public methods are safe — they never raise and always return a
    structurally valid output dict.
    """

    def resolve(
        self,
        dob: dict,
        birth_time: dict,
        birth_location: Optional[dict],
    ) -> dict:
        """
        Main entry point for S-03.

        Args:
            dob: {"day": int, "month": int, "year": int}
            birth_time: S-02 output — {"tier": str, "normalised_time": str|None,
                        "window_start": str|None, "window_end": str|None}
            birth_location: {"city": str, "country": str} or None

        Returns:
            S-03 output dict (all keys always present).
        """
        try:
            return self._resolve_internal(dob, birth_time, birth_location)
        except Exception as exc:
            log.error("MoonSignResolver.resolve failed: %s", exc, exc_info=True)
            return self._error_result(str(exc))

    # ── Internal implementation ───────────────────────────────────────────────

    def _resolve_internal(
        self,
        dob: dict,
        birth_time: dict,
        birth_location: Optional[dict],
    ) -> dict:
        year = int(dob["year"])
        month = int(dob["month"])
        day = int(dob["day"])

        utc_offset, is_utc_fallback = self._get_utc_offset(birth_location)

        # Step 1: positions at local midnight and end of day
        lon_start, lon_end = self._get_day_positions(year, month, day, utc_offset)

        sign_start = _longitude_to_sign_name(lon_start)
        sign_end = _longitude_to_sign_name(lon_end)

        tier = birth_time.get("tier", TIER_NONE)
        normalised_time = birth_time.get("normalised_time")
        window_start = birth_time.get("window_start")
        window_end = birth_time.get("window_end")

        # Step 1 result: no transition
        if sign_start == sign_end:
            return _apply_routing(
                sign_at_start=sign_start,
                sign_at_end=sign_end,
                transition_hour=None,
                majority_sign=None,
                minority_sign=None,
                majority_hours=None,
                tier=tier,
                normalised_time=normalised_time,
                window_start=window_start,
                window_end=window_end,
                utc_fallback=is_utc_fallback,
            )

        # Step 2: find transition
        jd_midnight = _local_to_jd(year, month, day, 0.0, utc_offset)
        jd_endofday = _local_to_jd(year, month, day, 23.0 + 59.0 / 60.0, utc_offset)
        sign_idx_start = _longitude_to_sign_index(lon_start)

        jd_transition = self._find_transition_jd(
            jd_midnight, jd_endofday, sign_idx_start
        )
        transition_hour = (jd_transition - jd_midnight) * 24.0

        # Check for a second transition (rare but spec-required)
        unusual_double = False
        sign_just_after = _longitude_to_sign_name(
            self._moon_longitude(jd_transition + 0.001)
        )
        sign_idx_after = _longitude_to_sign_index(
            self._moon_longitude(jd_transition + 0.001)
        )
        sign_at_endofday = _longitude_to_sign_name(lon_end)

        if sign_just_after != sign_at_endofday:
            unusual_double = True
            # Find second transition
            jd_transition2 = self._find_transition_jd(
                jd_transition + 0.001, jd_endofday, sign_idx_after
            )
            transition2_hour = (jd_transition2 - jd_midnight) * 24.0

            # Three blocks: sign_start [0→T1], sign_just_after [T1→T2], sign_at_endofday [T2→24]
            block_a = (sign_start, transition_hour)
            block_b = (sign_just_after, transition2_hour - transition_hour)
            block_c = (sign_at_endofday, 24.0 - transition2_hour)

            longest = max([block_a, block_b, block_c], key=lambda x: x[1])
            majority_sign = longest[0]
            majority_hours = longest[1]
            # minority = any other
            minority_sign = next(
                s for s, _ in [block_a, block_b, block_c] if s != majority_sign
            )

            # For transition_hour, use the first one
            # sign_at_start for routing purposes remains sign_start
            sign_end_for_routing = sign_at_endofday  # not used in majority context
        else:
            # Single transition
            majority_hours = 24.0 - transition_hour
            minority_hours = transition_hour
            if transition_hour > 12.0:
                majority_sign = sign_start
                majority_hours = transition_hour
                minority_sign = sign_end
            else:
                majority_sign = sign_end
                minority_sign = sign_start

            sign_end_for_routing = sign_end

        return _apply_routing(
            sign_at_start=sign_start,
            sign_at_end=sign_end_for_routing,
            transition_hour=transition_hour,
            majority_sign=majority_sign,
            minority_sign=minority_sign,
            majority_hours=majority_hours,
            tier=tier,
            normalised_time=normalised_time,
            window_start=window_start,
            window_end=window_end,
            utc_fallback=is_utc_fallback,
            unusual_double_transition=unusual_double,
        )

    # ── Timezone resolution ───────────────────────────────────────────────────

    def _get_utc_offset(
        self, birth_location: Optional[dict]
    ) -> tuple[float, bool]:
        """
        Return (utc_offset_hours, is_utc_fallback).

        Looks up city + country in CITY_TIMEZONE_MAP. Falls back to UTC (0.0)
        if location is None, empty, or not in the map.
        """
        if not birth_location:
            return 0.0, True

        city = str(birth_location.get("city", "")).strip().lower()
        country = str(birth_location.get("country", "")).strip().lower()

        tz_name = CITY_TIMEZONE_MAP.get((city, country))
        if tz_name is None:
            # Try city-only fallback
            for (c, _), tz in CITY_TIMEZONE_MAP.items():
                if c == city:
                    tz_name = tz
                    break

        if tz_name is None:
            log.debug("Timezone not found for %r, %r — using UTC", city, country)
            return 0.0, True

        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            log.warning("ZoneInfo not found: %r — using UTC", tz_name)
            return 0.0, True

        # Use noon on any day to get the standard offset (avoids DST edge cases at midnight)
        ref = datetime(2000, 6, 15, 12, 0, tzinfo=tz)
        offset_seconds = ref.utcoffset().total_seconds()
        return offset_seconds / 3600.0, False

    # ── Ephemeris calls ───────────────────────────────────────────────────────

    def _get_day_positions(
        self, year: int, month: int, day: int, utc_offset: float
    ) -> tuple[float, float]:
        """
        Return (moon_longitude_at_local_midnight, moon_longitude_at_local_23:59).

        Both longitudes are tropical ecliptic, in degrees [0, 360).
        """
        jd_start = _local_to_jd(year, month, day, 0.0, utc_offset)
        jd_end = _local_to_jd(year, month, day, 23.0 + 59.0 / 60.0, utc_offset)
        return self._moon_longitude(jd_start), self._moon_longitude(jd_end)

    def _moon_longitude(self, jd: float) -> float:
        """Return moon's tropical ecliptic longitude for a given Julian Day."""
        result, _ = swe.calc_ut(jd, swe.MOON)
        return result[0]

    def _find_transition_jd(
        self, jd_start: float, jd_end: float, sign_idx_start: int
    ) -> float:
        """
        Binary search for the Julian Day of a moon sign transition.

        Assumes sign_idx_start is the sign at jd_start and the moon has
        changed sign by jd_end. Returns the JD at the transition point
        to within ~1 minute of precision.
        """
        # 14 iterations: 1 day / 2^14 ≈ 1.46 minutes — sufficient for moon transitions
        for _ in range(14):
            mid = (jd_start + jd_end) / 2.0
            if _longitude_to_sign_index(self._moon_longitude(mid)) == sign_idx_start:
                jd_start = mid
            else:
                jd_end = mid
        return (jd_start + jd_end) / 2.0

    # ── Error result ──────────────────────────────────────────────────────────

    @staticmethod
    def _error_result(reason: str) -> dict:
        """Return a structurally valid output dict when calculation fails."""
        return {
            "moon_sign": None,
            "moon_sign_certain": False,
            "transition_occurred": False,
            "transition_time_local": None,
            "majority_sign": None,
            "minority_sign": None,
            "majority_hours": None,
            "confidence_flag": True,
            "confidence_reason": f"{_REASON_EPHEM_FAIL} Detail: {reason}",
        }
