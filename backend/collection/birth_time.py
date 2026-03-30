"""
S-02 — Birth Time Tier Detection

Takes a raw birth time string and classifies it into one of three tiers:
exact, approximate, or none. Produces a fully structured output including
normalised time, window bounds, confidence flag, and reason.

This module is a pure classifier — it performs no I/O and holds no session
state. The confirmation interaction described in S-02 is the caller's
responsibility (S-01 DataCollectionService / session layer).

Done condition (from spec):
  Every possible birth time input produces a valid structured output with
  the correct tier. No input causes a crash or silent default. All
  approximate inputs confirmed before locking. Confidence flag correct on
  every non-exact tier.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .constants import APPROXIMATE_TIME_WINDOWS, TIER_APPROXIMATE, TIER_EXACT, TIER_NONE

# ── Confidence reasons ────────────────────────────────────────────────────────

_REASON_APPROXIMATE = (
    "Approximate birth time — ascendant and house-based findings carry lower certainty."
)
_REASON_NONE = (
    "Birth time unknown — ascendant and house-based findings are unavailable."
)
_REASON_INVALID = (
    "Birth time could not be recognised — treated as unknown."
)
_REASON_HEDGED = (
    "Birth time given with uncertainty — treated as approximate."
)

# ── Hedge words (trigger approximate tier for stated exact times) ─────────────

_HEDGE_WORDS = frozenset({
    "think", "maybe", "not sure", "around", "approximately",
    "roughly", "probably", "believe", "guess", "unsure", "about",
})

# ── Explicit not-knowing phrases (trigger none tier immediately) ──────────────

_NONE_PHRASES = frozenset({
    "don't know", "dont know", "do not know", "unknown", "not sure",
    "no idea", "can't remember", "cant remember", "skip", "none",
    "i don't know", "i dont know", "i do not know", "unsure",
    "no clue", "have no idea", "not known", "didn't record",
    "no birth time", "no time",
})


# ── Output dataclass ──────────────────────────────────────────────────────────


@dataclass
class BirthTimeResult:
    """
    Structured output produced by BirthTimeTierDetector.classify().

    Fields match the S-02 contract exactly.
    needs_rephrase is not part of the spec output — it is an internal
    signal to the caller that the input was unrecognisable and a single
    re-ask is warranted before falling back to none tier.
    """

    tier: str
    normalised_time: Optional[str]
    window_start: Optional[str]
    window_end: Optional[str]
    confidence_flag: bool
    confidence_reason: Optional[str]
    # Caller signal — True means: ask once more before accepting none tier.
    needs_rephrase: bool = False

    def to_dict(self) -> dict:
        """Return the S-02 contract output shape (excludes needs_rephrase)."""
        return {
            "tier": self.tier,
            "normalised_time": self.normalised_time,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "confidence_flag": self.confidence_flag,
            "confidence_reason": self.confidence_reason,
        }


# ── Detector ──────────────────────────────────────────────────────────────────


class BirthTimeTierDetector:
    """
    Classifies a raw birth time string into a tiered BirthTimeResult.

    Classification priority (evaluated in order):
      1. None input or explicit not-knowing → TIER_NONE
      2. Natural-language approximate expression → TIER_APPROXIMATE
      3. Time range stated explicitly → TIER_APPROXIMATE (window used directly)
      4. Recognisable clock time:
         a. With hedge words → TIER_APPROXIMATE (2-hour centred window)
         b. Without hedge words, valid → TIER_EXACT
         c. Without hedge words, invalid (e.g. 25:00) → needs_rephrase=True, TIER_NONE
      5. Unrecognised → needs_rephrase=True, TIER_NONE
    """

    def classify(self, raw_input: Optional[str]) -> BirthTimeResult:
        """
        Classify a raw birth time input.

        Never raises. Every input — including None, empty string, and
        nonsense — produces a valid BirthTimeResult.

        Evaluation order (priority high → low):
          1. Null / empty → TIER_NONE
          2. Approximate table match — checked before hedge detection so that
             phrases like "around noon" always resolve to their table window
             rather than being treated as hedged clock times.
          3. Explicit time range → TIER_APPROXIMATE
          4. Clock time (valid + no hedge) → TIER_EXACT
          5. Clock time (valid + hedge words present) → TIER_APPROXIMATE
          6. Clock time pattern found but value invalid (e.g. 25:00) →
             TIER_NONE + needs_rephrase
          7. Explicit not-knowing phrases → TIER_NONE
             (checked here, after clock time, so that phrases like
             "not sure" embedded in "I think it was 3pm but not sure"
             are not swallowed before the clock time is found)
          8. Unrecognised → TIER_NONE + needs_rephrase
        """
        # ── 1. Null / empty ───────────────────────────────────────────────────
        if not raw_input or not raw_input.strip():
            return self._none_result()

        lower = raw_input.strip().lower()

        # ── 2. Approximate table match (unconditional — no hedge filtering) ───
        approx = _match_approximate_expression(lower)
        if approx:
            phrase, ws, we = approx
            return BirthTimeResult(
                tier=TIER_APPROXIMATE,
                normalised_time=None,
                window_start=ws,
                window_end=we,
                confidence_flag=True,
                confidence_reason=_REASON_APPROXIMATE,
            )

        # ── 3. Explicit time range (e.g. "between 2pm and 4pm") ──────────────
        time_range = _parse_time_range(lower)
        if time_range:
            ws, we = time_range
            return BirthTimeResult(
                tier=TIER_APPROXIMATE,
                normalised_time=None,
                window_start=ws,
                window_end=we,
                confidence_flag=True,
                confidence_reason=_REASON_APPROXIMATE,
            )

        # ── 4–6. Clock time ───────────────────────────────────────────────────
        parsed = _parse_clock_time(lower)

        if parsed is not None:
            valid, normalised = parsed
            if not valid:
                # Invalid time value (e.g. 25:00)
                return BirthTimeResult(
                    tier=TIER_NONE,
                    normalised_time=None,
                    window_start=None,
                    window_end=None,
                    confidence_flag=True,
                    confidence_reason=_REASON_INVALID,
                    needs_rephrase=True,
                )
            # Valid clock time — check for hedge words now
            has_hedge = any(word in lower for word in _HEDGE_WORDS)
            if has_hedge:
                ws, we = _two_hour_window(normalised)
                return BirthTimeResult(
                    tier=TIER_APPROXIMATE,
                    normalised_time=normalised,
                    window_start=ws,
                    window_end=we,
                    confidence_flag=True,
                    confidence_reason=_REASON_HEDGED,
                )
            return BirthTimeResult(
                tier=TIER_EXACT,
                normalised_time=normalised,
                window_start=None,
                window_end=None,
                confidence_flag=False,
                confidence_reason=None,
            )

        # ── 7. Explicit not-knowing (checked after clock time parsing) ────────
        if any(phrase in lower for phrase in _NONE_PHRASES):
            return self._none_result()

        # ── 8. Unrecognised ───────────────────────────────────────────────────
        return BirthTimeResult(
            tier=TIER_NONE,
            normalised_time=None,
            window_start=None,
            window_end=None,
            confidence_flag=True,
            confidence_reason=_REASON_INVALID,
            needs_rephrase=True,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _none_result() -> BirthTimeResult:
        return BirthTimeResult(
            tier=TIER_NONE,
            normalised_time=None,
            window_start=None,
            window_end=None,
            confidence_flag=True,
            confidence_reason=_REASON_NONE,
        )


# ── Module-level parsing helpers ──────────────────────────────────────────────


def _match_approximate_expression(lower: str) -> Optional[tuple[str, str, str]]:
    """
    Match a natural-language time expression against the S-02 window table.

    Returns (matched_phrase, window_start, window_end) or None.
    Longer/more specific phrases are checked before shorter ones to avoid
    'morning' swallowing 'late morning'.
    """
    # Sort by phrase length descending to prefer most-specific match
    candidates: list[tuple[str, str, str]] = []
    for phrase_set, ws, we in APPROXIMATE_TIME_WINDOWS:
        for phrase in phrase_set:
            candidates.append((phrase, ws, we))
    candidates.sort(key=lambda x: len(x[0]), reverse=True)

    for phrase, ws, we in candidates:
        if phrase in lower:
            return phrase, ws, we
    return None


def _parse_time_range(lower: str) -> Optional[tuple[str, str]]:
    """
    Parse an explicit time range from natural language.

    Handles patterns like:
      "between 2pm and 4pm"
      "2 to 4 pm"
      "14:00 - 16:00"
      "2-4pm"

    Returns (window_start HH:MM, window_end HH:MM) or None.
    """
    # "between X and Y"
    m = re.search(
        r"between\s+(\d{1,2}(?::\d{2})?(?:\s*(?:am|pm))?)"
        r"\s+and\s+"
        r"(\d{1,2}(?::\d{2})?(?:\s*(?:am|pm))?)",
        lower,
    )
    if m:
        t1 = _parse_clock_time(m.group(1).strip())
        t2 = _parse_clock_time(m.group(2).strip())
        if t1 and t2 and t1[0] and t2[0]:
            return t1[1], t2[1]

    # "X to Y pm" or "X-Y pm"
    m = re.search(
        r"(\d{1,2}(?::\d{2})?)\s*(?:to|-)\s*(\d{1,2}(?::\d{2})?)\s*(am|pm)?",
        lower,
    )
    if m:
        raw1 = m.group(1)
        raw2 = m.group(2)
        suffix = m.group(3) or ""
        t1 = _parse_clock_time(raw1 + suffix)
        t2 = _parse_clock_time(raw2 + suffix)
        if t1 and t2 and t1[0] and t2[0]:
            return t1[1], t2[1]

    return None


def _parse_clock_time(lower: str) -> Optional[tuple[bool, str]]:
    """
    Attempt to parse a clock time from a string.

    Returns (is_valid, normalised_HH:MM) or None if no time pattern found.
    Returns (False, "") if a time pattern was found but the value is invalid
    (e.g. hour=25).
    """
    lower = lower.strip()

    # ── HH:MM or H:MM with optional AM/PM ─────────────────────────────────
    m = re.search(r"\b(\d{1,2}):(\d{2})\s*(am|pm)?\b", lower)
    if m:
        hour, minute, ampm = int(m.group(1)), int(m.group(2)), m.group(3)
        return _validate_and_normalise(hour, minute, ampm)

    # ── HH.MM with optional AM/PM ─────────────────────────────────────────
    m = re.search(r"\b(\d{1,2})\.(\d{2})\s*(am|pm)?\b", lower)
    if m:
        hour, minute, ampm = int(m.group(1)), int(m.group(2)), m.group(3)
        return _validate_and_normalise(hour, minute, ampm)

    # ── HHMM (4-digit, no separator) e.g. 1430, 0230 ────────────────────
    m = re.fullmatch(r"(\d{4})", lower.strip())
    if m:
        raw = m.group(1)
        hour, minute = int(raw[:2]), int(raw[2:])
        return _validate_and_normalise(hour, minute, None)

    # ── H or HH with AM/PM e.g. "3pm", "10 am" ───────────────────────────
    m = re.search(r"\b(\d{1,2})\s*(am|pm)\b", lower)
    if m:
        hour, ampm = int(m.group(1)), m.group(2)
        return _validate_and_normalise(hour, 0, ampm)

    return None


def _validate_and_normalise(
    hour: int, minute: int, ampm: Optional[str]
) -> tuple[bool, str]:
    """
    Apply AM/PM conversion and validate range.

    Returns (True, "HH:MM") for valid times, (False, "") for invalid ones.
    """
    if ampm:
        ampm = ampm.lower()
        if ampm == "am":
            if hour == 12:
                hour = 0
            elif not (1 <= hour <= 12):
                return False, ""
        elif ampm == "pm":
            if hour == 12:
                pass  # 12pm = 12:00
            elif 1 <= hour <= 11:
                hour += 12
            else:
                return False, ""

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return False, ""

    return True, f"{hour:02d}:{minute:02d}"


def _two_hour_window(normalised: str) -> tuple[str, str]:
    """
    Return a ±1-hour window centred on a normalised HH:MM time.

    Per spec: hedged times use the stated time as the centre of a 2-hour window.
    """
    h, m = map(int, normalised.split(":"))
    start_h = (h - 1) % 24
    end_h = (h + 1) % 24
    return f"{start_h:02d}:{m:02d}", f"{end_h:02d}:{m:02d}"
