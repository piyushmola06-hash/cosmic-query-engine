"""
S-01 — Data Collection Layer

Collects all user data required by active heads at session start.
Implements the full question sequence, tolerance rules, and confirmation
protocol from the S-01 contract.

This service is stateless. The caller (session layer) owns the state dict
and passes it in on every call. No data is stored inside the service.

Done condition (from spec):
  All required fields populated or explicitly null.
  Output object valid and structured.
  Ambiguous inputs confirmed back to user before accepting.
  No field silently missing or silently defaulted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from .constants import (
    APPROXIMATE_TIME_WINDOWS,
    MANDATORY_HEADS,
    MAX_REPHRASE_ATTEMPTS,
    OPTIONAL_HEAD_ICHING,
    STEP_BIRTH_LOCATION,
    STEP_BIRTH_LOCATION_COUNTRY,
    STEP_BIRTH_TIME,
    STEP_BIRTH_TIME_CONFIRM,
    STEP_COMPLETE,
    STEP_CURRENT_NAME,
    STEP_DOB,
    STEP_DOB_CONFIRM,
    STEP_FULL_BIRTH_NAME,
    STEP_GENDER,
    STEP_ICHING_OPTIN,
    STEP_QUERY,
    TIER_APPROXIMATE,
    TIER_EXACT,
    TIER_NONE,
)


# ── Public data structures ────────────────────────────────────────────────────


@dataclass
class CollectionState:
    """Mutable state passed between collection turns."""

    step: str = STEP_QUERY
    data: dict = field(default_factory=dict)
    # Parsed value waiting for user confirmation before being committed.
    pending_confirmation: Optional[dict] = None
    # Tracks how many rephrase attempts have been made per step.
    rephrase_counts: dict = field(default_factory=dict)

    def rephrase_count(self, step: str) -> int:
        """Return the number of rephrase attempts made for a given step."""
        return self.rephrase_counts.get(step, 0)

    def increment_rephrase(self, step: str) -> None:
        """Increment the rephrase counter for a step."""
        self.rephrase_counts[step] = self.rephrase_count(step) + 1


@dataclass
class CollectionPrompt:
    """A message the system sends to the user, plus metadata."""

    message: str
    # True when this message is asking the user to confirm a parsed value.
    is_confirmation_request: bool = False
    # True when the collection is now complete and output is ready.
    is_complete: bool = False


# ── Service ───────────────────────────────────────────────────────────────────


class DataCollectionService:
    """
    Drives the S-01 data collection conversation.

    Usage:
        service = DataCollectionService()
        state = CollectionState()
        prompt = service.current_prompt(state)        # first question
        state, prompt = service.handle_response(state, user_input)
        # … repeat until prompt.is_complete is True
        output = service.build_output(state)
    """

    # ── Entry point ───────────────────────────────────────────────────────────

    def current_prompt(self, state: CollectionState) -> CollectionPrompt:
        """Return the question or confirmation message for the current step."""
        if state.pending_confirmation is not None:
            return self._confirmation_prompt(state)
        return self._question_for_step(state.step)

    def handle_response(
        self, state: CollectionState, raw_input: str
    ) -> tuple[CollectionState, CollectionPrompt]:
        """
        Process one user response and advance state.

        Returns the updated state and the next prompt to send.
        Never raises — all failures produce a null field and a rephrase or
        continuation prompt.
        """
        raw = raw_input.strip()

        # ── Confirmation branch ───────────────────────────────────────────────
        if state.pending_confirmation is not None:
            return self._handle_confirmation(state, raw)

        # ── Normal response branch ────────────────────────────────────────────
        step = state.step

        if step == STEP_QUERY:
            return self._handle_query(state, raw)
        if step == STEP_ICHING_OPTIN:
            return self._handle_iching_optin(state, raw)
        if step == STEP_DOB:
            return self._handle_dob(state, raw)
        if step == STEP_BIRTH_TIME:
            return self._handle_birth_time(state, raw)
        if step == STEP_BIRTH_LOCATION:
            return self._handle_birth_location(state, raw)
        if step == STEP_BIRTH_LOCATION_COUNTRY:
            return self._handle_birth_location_country(state, raw)
        if step == STEP_FULL_BIRTH_NAME:
            return self._handle_full_birth_name(state, raw)
        if step == STEP_CURRENT_NAME:
            return self._handle_current_name(state, raw)
        if step == STEP_GENDER:
            return self._handle_gender(state, raw)

        # Should never reach here
        raise ValueError(f"Unknown collection step: {step!r}")

    # ── Output builder ────────────────────────────────────────────────────────

    def build_output(self, state: CollectionState) -> dict:
        """
        Assemble the final S-01 output object.

        All required fields are present; optional fields that were skipped
        are explicitly null. Never called before is_complete() is True.
        """
        if state.step != STEP_COMPLETE:
            raise ValueError("Cannot build output before collection is complete.")

        d = state.data
        active_heads = list(MANDATORY_HEADS)
        if d.get("iching_opted_in"):
            active_heads.append(OPTIONAL_HEAD_ICHING)

        return {
            "query": d.get("query"),
            "iching_opted_in": d.get("iching_opted_in", False),
            "dob": d.get("dob"),
            "birth_time": d.get("birth_time"),
            "birth_location": d.get("birth_location"),
            "full_birth_name": d.get("full_birth_name"),
            "current_name": d.get("current_name", None),
            "gender": d.get("gender", None),
            "active_heads": active_heads,
        }

    # ── Step prompts ──────────────────────────────────────────────────────────

    def _question_for_step(self, step: str) -> CollectionPrompt:
        """Return the standard question for a given step."""
        questions = {
            STEP_QUERY: CollectionPrompt(
                "What is your question? Ask about your future, life direction, "
                "career, relationships, or anything you want a reading on."
            ),
            STEP_ICHING_OPTIN: CollectionPrompt(
                "Would you like to include the I Ching in your reading? "
                "It adds a sixth perspective drawn from an ancient divination system. "
                "Reply yes or no."
            ),
            STEP_DOB: CollectionPrompt(
                "What is your full date of birth? (day, month, year — any format)"
            ),
            STEP_BIRTH_TIME: CollectionPrompt(
                "What time were you born? If you know the exact time, great. "
                "If approximate (e.g. morning, evening), that works too. "
                "If you don't know, just say so."
            ),
            STEP_BIRTH_LOCATION: CollectionPrompt(
                "What city and country were you born in?"
            ),
            STEP_FULL_BIRTH_NAME: CollectionPrompt(
                "What is your full birth name — exactly as it appears on your "
                "birth certificate?"
            ),
            STEP_CURRENT_NAME: CollectionPrompt(
                "Do you go by a different name now? "
                "If yes, tell me. If not, just say no or skip."
            ),
            STEP_GENDER: CollectionPrompt(
                "What is your gender? (optional — say skip if you prefer not to share)"
            ),
        }
        return questions.get(step, CollectionPrompt("Something went wrong. Please try again."))

    def _confirmation_prompt(self, state: CollectionState) -> CollectionPrompt:
        """Return the confirmation message for a pending parsed value."""
        pending = state.pending_confirmation
        kind = pending.get("kind")

        if kind == "dob":
            d = pending["value"]
            return CollectionPrompt(
                f"I read your date of birth as {d['day']:02d}/{d['month']:02d}/{d['year']}. "
                "Is that correct? (yes / no)",
                is_confirmation_request=True,
            )

        if kind == "birth_time_approximate":
            value = pending["value"]
            ws = pending["window_start"]
            we = pending["window_end"]
            return CollectionPrompt(
                f"I'll treat \"{value}\" as an approximate time window of "
                f"{ws}–{we}. Is that right? (yes / no)",
                is_confirmation_request=True,
            )

        if kind == "birth_time_exact":
            normalised = pending["normalised"]
            return CollectionPrompt(
                f"I read your birth time as {normalised}. Is that correct? (yes / no)",
                is_confirmation_request=True,
            )

        if kind == "birth_location":
            city = pending["city"]
            country = pending["country"]
            return CollectionPrompt(
                f"Birth location: {city}, {country}. Is that right? (yes / no)",
                is_confirmation_request=True,
            )

        return CollectionPrompt("Can you confirm? (yes / no)", is_confirmation_request=True)

    # ── Confirmation handler ──────────────────────────────────────────────────

    def _handle_confirmation(
        self, state: CollectionState, raw: str
    ) -> tuple[CollectionState, CollectionPrompt]:
        """Process a yes/no confirmation response."""
        answer = raw.lower().strip()
        pending = state.pending_confirmation
        kind = pending.get("kind")

        confirmed = answer in {"yes", "y", "correct", "right", "yep", "yeah", "sure"}
        denied = answer in {"no", "n", "nope", "wrong", "incorrect"}

        if confirmed:
            state.pending_confirmation = None
            if kind == "dob":
                state.data["dob"] = pending["value"]
                state = self._advance_step(state, STEP_BIRTH_TIME)
            elif kind in ("birth_time_approximate", "birth_time_exact"):
                state.data["birth_time"] = pending["birth_time_obj"]
                state = self._advance_step(state, STEP_BIRTH_LOCATION)
            elif kind == "birth_location":
                state.data["birth_location"] = {
                    "city": pending["city"],
                    "country": pending["country"],
                }
                state = self._advance_step(state, STEP_FULL_BIRTH_NAME)
            return state, self.current_prompt(state)

        if denied:
            state.pending_confirmation = None
            # Re-ask the original step
            if kind == "dob":
                return state, CollectionPrompt(
                    "No problem. Please tell me your date of birth again."
                )
            if kind in ("birth_time_approximate", "birth_time_exact"):
                return state, CollectionPrompt(
                    "Got it. What time were you born? "
                    "(exact time, approximate like morning/evening, or unknown)"
                )
            if kind == "birth_location":
                return state, CollectionPrompt(
                    "Got it. What city and country were you born in?"
                )

        # Unrecognised confirmation answer — ask once more
        return state, CollectionPrompt(
            "Please reply yes or no.",
            is_confirmation_request=True,
        )

    # ── Per-step handlers ─────────────────────────────────────────────────────

    def _handle_query(
        self, state: CollectionState, raw: str
    ) -> tuple[CollectionState, CollectionPrompt]:
        """Accept any non-empty text as the query."""
        if not raw:
            return state, CollectionPrompt(
                "Please type your question to get started."
            )
        state.data["query"] = raw
        state = self._advance_step(state, STEP_ICHING_OPTIN)
        return state, self.current_prompt(state)

    def _handle_iching_optin(
        self, state: CollectionState, raw: str
    ) -> tuple[CollectionState, CollectionPrompt]:
        """Map yes/no to iching_opted_in boolean."""
        lower = raw.lower()
        yes_words = {"yes", "y", "yep", "yeah", "sure", "include", "add", "ok", "okay"}
        no_words = {"no", "n", "nope", "skip", "without", "not"}

        if any(w in lower for w in yes_words):
            state.data["iching_opted_in"] = True
        elif any(w in lower for w in no_words):
            state.data["iching_opted_in"] = False
        else:
            count = state.rephrase_count(STEP_ICHING_OPTIN)
            if count < MAX_REPHRASE_ATTEMPTS:
                state.increment_rephrase(STEP_ICHING_OPTIN)
                return state, CollectionPrompt(
                    "Just a yes or no — would you like to include the I Ching?"
                )
            # Default to not opted in after failed rephrase
            state.data["iching_opted_in"] = False

        state = self._advance_step(state, STEP_DOB)
        return state, self.current_prompt(state)

    def _handle_dob(
        self, state: CollectionState, raw: str
    ) -> tuple[CollectionState, CollectionPrompt]:
        """
        Parse date of birth from raw text. Confirm non-standard formats.
        """
        parsed = _parse_date(raw)

        if parsed is None:
            count = state.rephrase_count(STEP_DOB)
            if count < MAX_REPHRASE_ATTEMPTS:
                state.increment_rephrase(STEP_DOB)
                return state, CollectionPrompt(
                    "I couldn't read that as a date. "
                    "Please try again — for example: 15 March 1990 or 15/03/1990."
                )
            # Still unresolvable — null and continue
            state.data["dob"] = None
            state = self._advance_step(state, STEP_BIRTH_TIME)
            return state, self.current_prompt(state)

        # Always confirm — the format may have been ambiguous
        state.pending_confirmation = {"kind": "dob", "value": parsed}
        return state, self._confirmation_prompt(state)

    def _handle_birth_time(
        self, state: CollectionState, raw: str
    ) -> tuple[CollectionState, CollectionPrompt]:
        """
        Classify birth time input. Confirm exact and approximate before accepting.
        None-tier inputs (explicit not knowing) are accepted immediately.
        """
        lower = raw.lower().strip()

        # ── Explicit none ─────────────────────────────────────────────────────
        none_phrases = {
            "don't know", "dont know", "do not know", "unknown", "not sure",
            "no idea", "can't remember", "cant remember", "skip", "none",
            "i don't know", "i dont know", "i do not know", "unsure",
        }
        if any(phrase in lower for phrase in none_phrases):
            state.data["birth_time"] = {
                "tier": TIER_NONE,
                "value": None,
                "window_start": None,
                "window_end": None,
            }
            state = self._advance_step(state, STEP_BIRTH_LOCATION)
            return state, self.current_prompt(state)

        # ── Hedged exact time (e.g. "I think around 3pm") ────────────────────
        hedge_words = {"think", "maybe", "not sure", "around", "approximately",
                       "roughly", "probably", "believe", "guess"}
        has_hedge = any(w in lower for w in hedge_words)

        # ── Check for an approximate natural-language expression ──────────────
        approx_match = _match_approximate_time(lower)
        if approx_match and not has_hedge:
            value_label, window_start, window_end = approx_match
            state.pending_confirmation = {
                "kind": "birth_time_approximate",
                "value": value_label,
                "window_start": window_start,
                "window_end": window_end,
                "birth_time_obj": {
                    "tier": TIER_APPROXIMATE,
                    "value": value_label,
                    "window_start": window_start,
                    "window_end": window_end,
                },
            }
            return state, self._confirmation_prompt(state)

        # ── Try to parse an exact clock time ─────────────────────────────────
        exact_time = _parse_exact_time(lower)
        if exact_time:
            if has_hedge:
                # Hedged specific time → approximate tier, 2-hour window centred on stated time
                ws, we = _two_hour_window(exact_time)
                state.pending_confirmation = {
                    "kind": "birth_time_approximate",
                    "value": exact_time,
                    "window_start": ws,
                    "window_end": we,
                    "birth_time_obj": {
                        "tier": TIER_APPROXIMATE,
                        "value": exact_time,
                        "window_start": ws,
                        "window_end": we,
                    },
                }
            else:
                state.pending_confirmation = {
                    "kind": "birth_time_exact",
                    "normalised": exact_time,
                    "birth_time_obj": {
                        "tier": TIER_EXACT,
                        "value": exact_time,
                        "window_start": None,
                        "window_end": None,
                    },
                }
            return state, self._confirmation_prompt(state)

        # ── Unrecognised ──────────────────────────────────────────────────────
        count = state.rephrase_count(STEP_BIRTH_TIME)
        if count < MAX_REPHRASE_ATTEMPTS:
            state.increment_rephrase(STEP_BIRTH_TIME)
            return state, CollectionPrompt(
                "I didn't catch that. You can say something like \"10:30 AM\", "
                "\"morning\", \"evening\", or \"I don't know\"."
            )

        # Give up — null tier
        state.data["birth_time"] = {
            "tier": TIER_NONE,
            "value": None,
            "window_start": None,
            "window_end": None,
        }
        state = self._advance_step(state, STEP_BIRTH_LOCATION)
        return state, self.current_prompt(state)

    def _handle_birth_location(
        self, state: CollectionState, raw: str
    ) -> tuple[CollectionState, CollectionPrompt]:
        """
        Parse city and country from a free-text location string.
        If only a city is detected, ask for the country.
        """
        city, country = _parse_location(raw)

        if city and not country:
            # Remember the city and ask for country
            state.data["_partial_city"] = city
            state.step = STEP_BIRTH_LOCATION_COUNTRY
            return state, CollectionPrompt(
                f"Got {city!r} — what country is that in?"
            )

        if city and country:
            state.pending_confirmation = {
                "kind": "birth_location",
                "city": city,
                "country": country,
            }
            return state, self._confirmation_prompt(state)

        # Unrecognised location
        count = state.rephrase_count(STEP_BIRTH_LOCATION)
        if count < MAX_REPHRASE_ATTEMPTS:
            state.increment_rephrase(STEP_BIRTH_LOCATION)
            return state, CollectionPrompt(
                "Please give me a city and country — for example: "
                "\"Mumbai, India\" or \"London, UK\"."
            )

        state.data["birth_location"] = None
        state = self._advance_step(state, STEP_FULL_BIRTH_NAME)
        return state, self.current_prompt(state)

    def _handle_birth_location_country(
        self, state: CollectionState, raw: str
    ) -> tuple[CollectionState, CollectionPrompt]:
        """Accept the country that was missing from the location step."""
        city = state.data.pop("_partial_city", "")
        country = raw.strip().title()

        if not country:
            state.data["birth_location"] = None
            state = self._advance_step(state, STEP_FULL_BIRTH_NAME)
            return state, self.current_prompt(state)

        state.pending_confirmation = {
            "kind": "birth_location",
            "city": city,
            "country": country,
        }
        state.step = STEP_BIRTH_LOCATION  # so confirmation advance targets the right step
        return state, self._confirmation_prompt(state)

    def _handle_full_birth_name(
        self, state: CollectionState, raw: str
    ) -> tuple[CollectionState, CollectionPrompt]:
        """Accept any non-empty name as the full birth name."""
        if not raw:
            count = state.rephrase_count(STEP_FULL_BIRTH_NAME)
            if count < MAX_REPHRASE_ATTEMPTS:
                state.increment_rephrase(STEP_FULL_BIRTH_NAME)
                return state, CollectionPrompt(
                    "Please provide your full birth name as it appears on your "
                    "birth certificate."
                )
            state.data["full_birth_name"] = None
        else:
            state.data["full_birth_name"] = raw

        state = self._advance_step(state, STEP_CURRENT_NAME)
        return state, self.current_prompt(state)

    def _handle_current_name(
        self, state: CollectionState, raw: str
    ) -> tuple[CollectionState, CollectionPrompt]:
        """Accept a current name or record null if the user skips."""
        skip_words = {"no", "n", "skip", "same", "none", "nope"}
        skip_phrases = {"not different"}
        lower = raw.lower().strip()
        tokens = set(re.split(r"\s+", lower))

        is_skip = (
            not raw
            or tokens & skip_words
            or any(p in lower for p in skip_phrases)
        )

        if is_skip:
            state.data["current_name"] = None
        else:
            state.data["current_name"] = raw.strip()

        state = self._advance_step(state, STEP_GENDER)
        return state, self.current_prompt(state)

    def _handle_gender(
        self, state: CollectionState, raw: str
    ) -> tuple[CollectionState, CollectionPrompt]:
        """Accept gender or record null if skipped."""
        skip_phrases = {"skip", "prefer not", "rather not", "no", "none", "n/a", ""}
        lower = raw.lower().strip()

        if lower in skip_phrases:
            state.data["gender"] = None
        else:
            state.data["gender"] = raw.strip()

        state.step = STEP_COMPLETE
        return state, CollectionPrompt(
            "Thank you — I have everything I need. Generating your reading now.",
            is_complete=True,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _advance_step(state: CollectionState, next_step: str) -> CollectionState:
        """Move state to the next step."""
        state.step = next_step
        return state


# ── Parsing helpers (module-level, pure functions) ────────────────────────────


def _parse_date(raw: str) -> Optional[dict]:
    """
    Attempt to parse a date of birth from any reasonable format.

    Returns {"day": int, "month": int, "year": int} or None.
    Never guesses silently — caller must confirm before accepting.
    """
    raw = raw.strip()

    # Numeric patterns: DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD, DD.MM.YYYY
    numeric_patterns = [
        r"^(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})$",   # DD/MM/YYYY or MM/DD/YYYY
        r"^(\d{4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})$",   # YYYY-MM-DD
        r"^(\d{1,2})\s+(\d{1,2})\s+(\d{4})$",            # DD MM YYYY
    ]

    # Pattern 1: DD/MM/YYYY (we always treat first number as day)
    m = re.match(r"^(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})$", raw)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valid_date(day, month, year):
            return {"day": day, "month": month, "year": year}

    # Pattern 2: YYYY-MM-DD (ISO)
    m = re.match(r"^(\d{4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})$", raw)
    if m:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valid_date(day, month, year):
            return {"day": day, "month": month, "year": year}

    # Natural language: "15 March 1990", "March 15, 1990", "15th March 1990"
    month_names = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
    }

    # "15 March 1990" or "15th March 1990"
    m = re.match(
        r"^(\d{1,2})(?:st|nd|rd|th)?\s+([a-zA-Z]+)\s+(\d{4})$", raw, re.IGNORECASE
    )
    if m:
        day = int(m.group(1))
        month = month_names.get(m.group(2).lower())
        year = int(m.group(3))
        if month and _valid_date(day, month, year):
            return {"day": day, "month": month, "year": year}

    # "March 15, 1990" or "March 15 1990"
    m = re.match(
        r"^([a-zA-Z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})$", raw, re.IGNORECASE
    )
    if m:
        month = month_names.get(m.group(1).lower())
        day = int(m.group(2))
        year = int(m.group(3))
        if month and _valid_date(day, month, year):
            return {"day": day, "month": month, "year": year}

    return None


def _valid_date(day: int, month: int, year: int) -> bool:
    """Return True if day/month/year form a valid calendar date."""
    try:
        date(year, month, day)
        return True
    except ValueError:
        return False


def _match_approximate_time(lower: str) -> Optional[tuple[str, str, str]]:
    """
    Match a natural-language time expression against the S-02 window table.

    Returns (matched_phrase, window_start, window_end) or None.
    """
    for phrase_set, ws, we in APPROXIMATE_TIME_WINDOWS:
        for phrase in phrase_set:
            if phrase in lower:
                return phrase, ws, we
    return None


def _parse_exact_time(lower: str) -> Optional[str]:
    """
    Parse a clock time from a string and return it normalised as HH:MM (24h).

    Returns None if no recognisable time is found.
    """
    # HH:MM with optional AM/PM
    m = re.search(r"\b(\d{1,2}):(\d{2})\s*(am|pm)?\b", lower)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        ampm = m.group(3)
        hour = _apply_ampm(hour, ampm)
        if hour is not None and 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"

    # "3pm", "10am", "3 pm"
    m = re.search(r"\b(\d{1,2})\s*(am|pm)\b", lower)
    if m:
        hour = int(m.group(1))
        ampm = m.group(2)
        hour = _apply_ampm(hour, ampm)
        if hour is not None and 0 <= hour <= 23:
            return f"{hour:02d}:00"

    return None


def _apply_ampm(hour: int, ampm: Optional[str]) -> Optional[int]:
    """Convert a 12-hour clock value to 24-hour."""
    if ampm is None:
        return hour if 0 <= hour <= 23 else None
    ampm = ampm.lower()
    if ampm == "am":
        if hour == 12:
            return 0
        return hour if 1 <= hour <= 12 else None
    if ampm == "pm":
        if hour == 12:
            return 12
        return hour + 12 if 1 <= hour <= 11 else None
    return None


def _two_hour_window(normalised_time: str) -> tuple[str, str]:
    """
    Return a ±1 hour window around a normalised HH:MM time.

    Used for hedged exact times (spec: centre of a 2-hour window).
    """
    h, m = map(int, normalised_time.split(":"))
    start_h = (h - 1) % 24
    end_h = (h + 1) % 24
    return f"{start_h:02d}:{m:02d}", f"{end_h:02d}:{m:02d}"


def _parse_location(raw: str) -> tuple[Optional[str], Optional[str]]:
    """
    Extract city and country from a free-text location string.

    Returns (city, country) — either may be None.
    Handles: "Mumbai, India", "London UK", "Paris - France".
    """
    raw = raw.strip()
    if not raw:
        return None, None

    # Split on comma, dash, or " - "
    for sep in (",", " - ", "/"):
        if sep in raw:
            parts = [p.strip().title() for p in raw.split(sep, 1)]
            if len(parts) == 2 and parts[0] and parts[1]:
                return parts[0], parts[1]

    # Two words separated by space (e.g. "London UK")
    parts = raw.rsplit(None, 1)
    if len(parts) == 2:
        return parts[0].strip().title(), parts[1].strip().title()

    # Single token — assume city, country unknown
    return raw.title(), None
