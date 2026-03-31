"""
Tests for S-03 — Moon Sign Ambiguity Resolution.

Done condition (from spec):
  Every combination of birth time tier × moon transition scenario produces
  valid output. Majority-day rule applied only when window genuinely overlaps.
  Exact tier never uses majority-day rule. Location always used for local time
  calculation — UTC is fallback only.

Test structure:
  TestApplyRouting          — pure routing logic via _apply_routing(), no ephemeris
  TestMoonSignResolverReal  — integration tests using real pyswisseph
"""

from django.test import TestCase

from collection.moon_sign import (
    MoonSignResolver,
    _apply_routing,
    _hhmm_end_to_hours,
    _hhmm_to_hours,
    _hours_to_hhmm,
    _longitude_to_sign_name,
)
from collection.constants import TIER_APPROXIMATE, TIER_EXACT, TIER_NONE

# ── Shared test data ──────────────────────────────────────────────────────────

# Canonical transition scenario used across routing tests:
#   - Moon moves from Scorpio (sign_at_start) to Sagittarius (sign_at_end)
#   - Transition at 06:00 local
#   - Scorpio: 6 hours (minority), Sagittarius: 18 hours (majority)

_TRANSITION_SCENARIO = dict(
    sign_at_start="Scorpio",
    sign_at_end="Sagittarius",
    transition_hour=6.0,
    majority_sign="Sagittarius",
    minority_sign="Scorpio",
    majority_hours=18.0,
    utc_fallback=False,
    unusual_double_transition=False,
)

_NO_TRANSITION_SCENARIO = dict(
    sign_at_start="Scorpio",
    sign_at_end="Scorpio",
    transition_hour=None,
    majority_sign=None,
    minority_sign=None,
    majority_hours=None,
    utc_fallback=False,
    unusual_double_transition=False,
)


# ── Required output keys (S-03 contract) ─────────────────────────────────────

REQUIRED_KEYS = {
    "moon_sign",
    "moon_sign_certain",
    "transition_occurred",
    "transition_time_local",
    "majority_sign",
    "minority_sign",
    "majority_hours",
    "confidence_flag",
    "confidence_reason",
}


def _assert_output_shape(test_case: TestCase, result: dict) -> None:
    """Assert that result contains all required S-03 output keys."""
    for key in REQUIRED_KEYS:
        test_case.assertIn(key, result, f"Output missing required key: {key!r}")


# ─────────────────────────────────────────────────────────────────────────────
# TestApplyRouting — pure routing logic, no ephemeris required
# ─────────────────────────────────────────────────────────────────────────────


class TestApplyRouting(TestCase):
    """
    Tests _apply_routing() directly with controlled inputs.

    These tests are deterministic and do not touch pyswisseph.
    They verify every tier × transition combination specified in S-03.
    """

    # ── No transition ─────────────────────────────────────────────────────────

    def test_no_transition_certain_no_flag(self) -> None:
        """No transition → moon_sign_certain, confidence_flag False."""
        result = _apply_routing(
            **_NO_TRANSITION_SCENARIO,
            tier=TIER_NONE,
            normalised_time=None,
            window_start=None,
            window_end=None,
        )
        _assert_output_shape(self, result)
        self.assertEqual(result["moon_sign"], "Scorpio")
        self.assertTrue(result["moon_sign_certain"])
        self.assertFalse(result["transition_occurred"])
        self.assertIsNone(result["transition_time_local"])
        self.assertFalse(result["confidence_flag"])
        self.assertIsNone(result["confidence_reason"])

    def test_no_transition_utc_fallback_flags(self) -> None:
        """No transition but UTC fallback → confidence_flag True, reason set."""
        result = _apply_routing(
            **{**_NO_TRANSITION_SCENARIO, "utc_fallback": True},
            tier=TIER_NONE,
            normalised_time=None,
            window_start=None,
            window_end=None,
        )
        self.assertTrue(result["confidence_flag"])
        self.assertIsNotNone(result["confidence_reason"])
        self.assertIn("UTC", result["confidence_reason"])

    # ── Exact tier ────────────────────────────────────────────────────────────

    def test_exact_born_before_transition(self) -> None:
        """Exact tier, born before transition → first sign, certain."""
        # Transition at 06:00, born at 03:00 → Scorpio
        result = _apply_routing(
            **_TRANSITION_SCENARIO,
            tier=TIER_EXACT,
            normalised_time="03:00",
            window_start=None,
            window_end=None,
        )
        _assert_output_shape(self, result)
        self.assertEqual(result["moon_sign"], "Scorpio")
        self.assertTrue(result["moon_sign_certain"])
        self.assertTrue(result["transition_occurred"])
        self.assertFalse(result["confidence_flag"])

    def test_exact_born_after_transition(self) -> None:
        """Exact tier, born after transition → second sign, certain."""
        # Transition at 06:00, born at 18:00 → Sagittarius
        result = _apply_routing(
            **_TRANSITION_SCENARIO,
            tier=TIER_EXACT,
            normalised_time="18:00",
            window_start=None,
            window_end=None,
        )
        _assert_output_shape(self, result)
        self.assertEqual(result["moon_sign"], "Sagittarius")
        self.assertTrue(result["moon_sign_certain"])
        self.assertFalse(result["confidence_flag"])

    def test_exact_born_at_transition_boundary(self) -> None:
        """Exact tier, normalised_time equals transition_hour → second sign (≥ rule)."""
        result = _apply_routing(
            **_TRANSITION_SCENARIO,
            tier=TIER_EXACT,
            normalised_time="06:00",   # equal to transition_hour=6.0
            window_start=None,
            window_end=None,
        )
        self.assertEqual(result["moon_sign"], "Sagittarius")
        self.assertTrue(result["moon_sign_certain"])

    def test_exact_never_uses_majority_rule(self) -> None:
        """Exact tier always produces certain result regardless of transition."""
        result = _apply_routing(
            **_TRANSITION_SCENARIO,
            tier=TIER_EXACT,
            normalised_time="10:00",
            window_start=None,
            window_end=None,
        )
        self.assertTrue(result["moon_sign_certain"])

    # ── Approximate tier ──────────────────────────────────────────────────────

    def test_approximate_window_entirely_before_transition(self) -> None:
        """Approximate window ends before transition → first sign, certain."""
        # Transition at 06:00, window 02:00–04:00 → entirely before → Scorpio, certain
        result = _apply_routing(
            **_TRANSITION_SCENARIO,
            tier=TIER_APPROXIMATE,
            normalised_time=None,
            window_start="02:00",
            window_end="04:00",
        )
        _assert_output_shape(self, result)
        self.assertEqual(result["moon_sign"], "Scorpio")
        self.assertTrue(result["moon_sign_certain"])
        self.assertFalse(result["confidence_flag"])

    def test_approximate_window_entirely_after_transition(self) -> None:
        """Approximate window starts after transition → second sign, certain."""
        # Transition at 06:00, window 12:00–15:00 → entirely after → Sagittarius, certain
        result = _apply_routing(
            **_TRANSITION_SCENARIO,
            tier=TIER_APPROXIMATE,
            normalised_time=None,
            window_start="12:00",
            window_end="15:00",
        )
        _assert_output_shape(self, result)
        self.assertEqual(result["moon_sign"], "Sagittarius")
        self.assertTrue(result["moon_sign_certain"])
        self.assertFalse(result["confidence_flag"])

    def test_approximate_window_overlaps_transition_majority_rule(self) -> None:
        """Approximate window overlaps transition → majority-day rule, flagged."""
        # Transition at 06:00, window 04:00–09:00 → overlaps → majority = Sagittarius
        result = _apply_routing(
            **_TRANSITION_SCENARIO,
            tier=TIER_APPROXIMATE,
            normalised_time=None,
            window_start="04:00",
            window_end="09:00",
        )
        _assert_output_shape(self, result)
        self.assertEqual(result["moon_sign"], "Sagittarius")   # majority sign
        self.assertFalse(result["moon_sign_certain"])
        self.assertTrue(result["confidence_flag"])
        self.assertIsNotNone(result["confidence_reason"])

    def test_approximate_window_ending_exactly_at_transition(self) -> None:
        """Window ending exactly at transition hour is 'entirely before' (not overlapping)."""
        # window_end = 06:00 = transition_hour → entirely_before (we <= transition)
        result = _apply_routing(
            **_TRANSITION_SCENARIO,
            tier=TIER_APPROXIMATE,
            normalised_time=None,
            window_start="03:00",
            window_end="06:00",
        )
        self.assertTrue(result["moon_sign_certain"])
        self.assertEqual(result["moon_sign"], "Scorpio")

    def test_approximate_window_night_band_to_midnight(self) -> None:
        """Night band window (21:00–00:00) — 00:00 end treated as 24.0."""
        # Transition at 06:00, window 21:00–00:00 (=24) → entirely after → Sagittarius
        result = _apply_routing(
            **_TRANSITION_SCENARIO,
            tier=TIER_APPROXIMATE,
            normalised_time=None,
            window_start="21:00",
            window_end="00:00",  # midnight = end of day = 24.0
        )
        self.assertTrue(result["moon_sign_certain"])
        self.assertEqual(result["moon_sign"], "Sagittarius")

    # ── None tier ─────────────────────────────────────────────────────────────

    def test_none_tier_transition_majority_rule(self) -> None:
        """None tier + transition → majority-day rule, certain=False, flagged."""
        result = _apply_routing(
            **_TRANSITION_SCENARIO,
            tier=TIER_NONE,
            normalised_time=None,
            window_start=None,
            window_end=None,
        )
        _assert_output_shape(self, result)
        self.assertEqual(result["moon_sign"], "Sagittarius")  # majority
        self.assertFalse(result["moon_sign_certain"])
        self.assertTrue(result["transition_occurred"])
        self.assertTrue(result["confidence_flag"])
        self.assertIsNotNone(result["confidence_reason"])
        self.assertEqual(result["majority_sign"], "Sagittarius")
        self.assertEqual(result["minority_sign"], "Scorpio")
        self.assertAlmostEqual(result["majority_hours"], 18.0)

    def test_none_tier_no_transition_certain(self) -> None:
        """None tier but no transition → certain, no flag."""
        result = _apply_routing(
            **_NO_TRANSITION_SCENARIO,
            tier=TIER_NONE,
            normalised_time=None,
            window_start=None,
            window_end=None,
        )
        self.assertTrue(result["moon_sign_certain"])
        self.assertFalse(result["confidence_flag"])

    # ── Midnight transition edge case ─────────────────────────────────────────

    def test_midnight_transition_entire_day_second_sign_certain(self) -> None:
        """
        Moon changes sign at (or within 1 minute of) local midnight.
        Per spec: entire day belongs to second sign, certain.
        """
        result = _apply_routing(
            sign_at_start="Scorpio",
            sign_at_end="Sagittarius",
            transition_hour=0.005,   # < 1-minute epsilon
            majority_sign="Sagittarius",
            minority_sign="Scorpio",
            majority_hours=23.995,
            tier=TIER_NONE,
            normalised_time=None,
            window_start=None,
            window_end=None,
            utc_fallback=False,
        )
        self.assertEqual(result["moon_sign"], "Sagittarius")
        self.assertTrue(result["moon_sign_certain"])
        self.assertFalse(result["confidence_flag"])

    # ── transition_time_local formatting ─────────────────────────────────────

    def test_transition_time_local_formatted_correctly(self) -> None:
        result = _apply_routing(
            **_TRANSITION_SCENARIO,
            tier=TIER_NONE,
            normalised_time=None,
            window_start=None,
            window_end=None,
        )
        self.assertEqual(result["transition_time_local"], "06:00")

    def test_transition_time_local_null_when_no_transition(self) -> None:
        result = _apply_routing(
            **_NO_TRANSITION_SCENARIO,
            tier=TIER_NONE,
            normalised_time=None,
            window_start=None,
            window_end=None,
        )
        self.assertIsNone(result["transition_time_local"])


# ─────────────────────────────────────────────────────────────────────────────
# TestMoonSignResolverReal — integration tests using live pyswisseph
# ─────────────────────────────────────────────────────────────────────────────


class TestMoonSignResolverReal(TestCase):
    """
    Integration tests that exercise MoonSignResolver.resolve() end-to-end
    with real pyswisseph calculations.

    Reference dates (UTC):
      15 March 1990 — Moon ~213° at midnight, ~226° at 23:59 (Scorpio all day).
                      No transition. Moon sign: Scorpio.
      17 March 1990 — Moon ~239° at midnight, ~252° at 23:59. Scorpio→Sagittarius.
                      Transition early morning (~00:44 UTC). Majority: Sagittarius.
    """

    def setUp(self) -> None:
        self.resolver = MoonSignResolver()
        self.no_transition_dob = {"day": 15, "month": 3, "year": 1990}
        self.transition_dob = {"day": 17, "month": 3, "year": 1990}
        self.birth_time_none = {
            "tier": TIER_NONE,
            "normalised_time": None,
            "window_start": None,
            "window_end": None,
        }

    # ── No-transition case ────────────────────────────────────────────────────

    def test_no_transition_on_15_march_1990(self) -> None:
        """15 March 1990 UTC — moon stays in Scorpio all day, no transition."""
        result = self.resolver.resolve(
            dob=self.no_transition_dob,
            birth_time=self.birth_time_none,
            birth_location=None,  # UTC fallback
        )
        _assert_output_shape(self, result)
        self.assertFalse(result["transition_occurred"])
        self.assertTrue(result["moon_sign_certain"])
        self.assertEqual(result["moon_sign"], "Scorpio")
        self.assertIsNone(result["transition_time_local"])
        self.assertIsNone(result["majority_sign"])
        # UTC fallback is flagged (no location given)
        self.assertTrue(result["confidence_flag"])

    # ── Transition + none tier ────────────────────────────────────────────────

    def test_transition_none_tier_17_march_1990(self) -> None:
        """17 March 1990 UTC — transition detected, none tier → majority-day rule."""
        result = self.resolver.resolve(
            dob=self.transition_dob,
            birth_time=self.birth_time_none,
            birth_location=None,
        )
        _assert_output_shape(self, result)
        self.assertTrue(result["transition_occurred"])
        self.assertFalse(result["moon_sign_certain"])
        self.assertTrue(result["confidence_flag"])
        # Sagittarius should be the majority sign (most of the day)
        self.assertEqual(result["moon_sign"], "Sagittarius")
        self.assertEqual(result["majority_sign"], "Sagittarius")
        self.assertEqual(result["minority_sign"], "Scorpio")
        self.assertIsNotNone(result["transition_time_local"])
        self.assertIsNotNone(result["majority_hours"])
        # Majority hours > 12 (Sagittarius occupies most of the day)
        self.assertGreater(result["majority_hours"], 12.0)

    # ── Transition + exact tier ───────────────────────────────────────────────

    def test_transition_exact_born_after_transition_17_march_1990(self) -> None:
        """
        17 March 1990 UTC — transition early morning (~00:44).
        Born at 06:00 (after transition) → Sagittarius, certain.
        """
        birth_time = {
            "tier": TIER_EXACT,
            "normalised_time": "06:00",
            "window_start": None,
            "window_end": None,
        }
        result = self.resolver.resolve(
            dob=self.transition_dob,
            birth_time=birth_time,
            birth_location=None,
        )
        _assert_output_shape(self, result)
        self.assertTrue(result["transition_occurred"])
        self.assertEqual(result["moon_sign"], "Sagittarius")
        self.assertTrue(result["moon_sign_certain"])

    def test_transition_exact_born_before_transition_17_march_1990(self) -> None:
        """
        17 March 1990 UTC — transition early morning (~00:44).
        Born at 00:30 (before transition) → Scorpio, certain.
        """
        birth_time = {
            "tier": TIER_EXACT,
            "normalised_time": "00:30",
            "window_start": None,
            "window_end": None,
        }
        result = self.resolver.resolve(
            dob=self.transition_dob,
            birth_time=birth_time,
            birth_location=None,
        )
        _assert_output_shape(self, result)
        self.assertTrue(result["transition_occurred"])
        self.assertEqual(result["moon_sign"], "Scorpio")
        self.assertTrue(result["moon_sign_certain"])

    # ── Transition + approximate tier ────────────────────────────────────────

    def test_transition_approximate_window_after_transition(self) -> None:
        """
        17 March 1990 UTC — transition at ~00:44.
        Window 06:00–09:00 is entirely after → Sagittarius, certain.
        """
        birth_time = {
            "tier": TIER_APPROXIMATE,
            "normalised_time": None,
            "window_start": "06:00",
            "window_end": "09:00",
        }
        result = self.resolver.resolve(
            dob=self.transition_dob,
            birth_time=birth_time,
            birth_location=None,
        )
        _assert_output_shape(self, result)
        self.assertEqual(result["moon_sign"], "Sagittarius")
        self.assertTrue(result["moon_sign_certain"])

    def test_transition_approximate_window_overlaps_majority_rule(self) -> None:
        """
        17 March 1990 UTC — transition time discovered from real ephemeris.
        Window constructed to straddle the actual transition → majority-day rule, flagged.
        """
        from collection.moon_sign import _hours_to_hhmm

        # Step 1: find the actual transition time via the resolver
        none_result = self.resolver.resolve(
            dob=self.transition_dob,
            birth_time=self.birth_time_none,
            birth_location=None,
        )
        self.assertTrue(none_result["transition_occurred"], "17 March 1990 must have a transition")
        t_str = none_result["transition_time_local"]
        h, m = map(int, t_str.split(":"))
        t_hours = h + m / 60.0

        # Step 2: build a ±2-hour window centred on the transition
        ws_hours = max(0.0, t_hours - 2.0)
        we_hours = min(23.5, t_hours + 2.0)
        birth_time = {
            "tier": TIER_APPROXIMATE,
            "normalised_time": None,
            "window_start": _hours_to_hhmm(ws_hours),
            "window_end": _hours_to_hhmm(we_hours),
        }

        # Step 3: verify majority-day rule is applied
        result = self.resolver.resolve(
            dob=self.transition_dob,
            birth_time=birth_time,
            birth_location=None,
        )
        _assert_output_shape(self, result)
        self.assertFalse(result["moon_sign_certain"])
        self.assertTrue(result["confidence_flag"])
        self.assertEqual(result["moon_sign"], "Sagittarius")  # majority sign

    # ── Location resolution ───────────────────────────────────────────────────

    def test_unresolvable_location_utc_fallback_flagged(self) -> None:
        """Location not in map → UTC fallback, confidence_flag True, reason mentions UTC."""
        result = self.resolver.resolve(
            dob=self.no_transition_dob,
            birth_time=self.birth_time_none,
            birth_location={"city": "Xyzzyville", "country": "Nowhere"},
        )
        _assert_output_shape(self, result)
        self.assertTrue(result["confidence_flag"])
        self.assertIsNotNone(result["confidence_reason"])
        self.assertIn("UTC", result["confidence_reason"])

    def test_known_location_used_for_calculation(self) -> None:
        """
        Mumbai (UTC+5:30) and UTC should produce different transition times
        for a date with a transition. The result is still structurally valid.
        """
        result_utc = self.resolver.resolve(
            dob=self.transition_dob,
            birth_time=self.birth_time_none,
            birth_location=None,
        )
        result_mumbai = self.resolver.resolve(
            dob=self.transition_dob,
            birth_time=self.birth_time_none,
            birth_location={"city": "Mumbai", "country": "India"},
        )
        _assert_output_shape(self, result_mumbai)
        # Both should report a transition but possibly different transition times
        self.assertTrue(result_utc["transition_occurred"])
        self.assertTrue(result_mumbai["transition_occurred"])
        # Mumbai result should NOT be flagged as UTC fallback
        # (UTC fallback reason should not appear if location resolved)
        if result_mumbai["confidence_reason"]:
            self.assertNotIn("could not be resolved", result_mumbai["confidence_reason"])

    # ── Output shape ──────────────────────────────────────────────────────────

    def test_output_has_all_required_keys_no_transition(self) -> None:
        result = self.resolver.resolve(
            dob=self.no_transition_dob,
            birth_time=self.birth_time_none,
            birth_location=None,
        )
        _assert_output_shape(self, result)

    def test_output_has_all_required_keys_with_transition(self) -> None:
        result = self.resolver.resolve(
            dob=self.transition_dob,
            birth_time=self.birth_time_none,
            birth_location=None,
        )
        _assert_output_shape(self, result)

    def test_error_does_not_crash(self) -> None:
        """Invalid DOB dict → returns valid error result, never crashes."""
        result = self.resolver.resolve(
            dob={"day": 99, "month": 99, "year": 1990},
            birth_time=self.birth_time_none,
            birth_location=None,
        )
        _assert_output_shape(self, result)
        self.assertTrue(result["confidence_flag"])
        self.assertIsNone(result["moon_sign"])


# ─────────────────────────────────────────────────────────────────────────────
# TestHelperFunctions — pure helper functions
# ─────────────────────────────────────────────────────────────────────────────


class TestHelperFunctions(TestCase):
    """Unit tests for pure module-level helpers."""

    def test_longitude_to_sign_aries(self) -> None:
        self.assertEqual(_longitude_to_sign_name(0.0), "Aries")
        self.assertEqual(_longitude_to_sign_name(29.9), "Aries")

    def test_longitude_to_sign_scorpio(self) -> None:
        self.assertEqual(_longitude_to_sign_name(210.0), "Scorpio")
        self.assertEqual(_longitude_to_sign_name(239.9), "Scorpio")

    def test_longitude_to_sign_sagittarius(self) -> None:
        self.assertEqual(_longitude_to_sign_name(240.0), "Sagittarius")
        self.assertEqual(_longitude_to_sign_name(269.9), "Sagittarius")

    def test_longitude_to_sign_pisces(self) -> None:
        self.assertEqual(_longitude_to_sign_name(330.0), "Pisces")
        self.assertEqual(_longitude_to_sign_name(359.9), "Pisces")

    def test_hhmm_to_hours(self) -> None:
        self.assertAlmostEqual(_hhmm_to_hours("10:30"), 10.5)
        self.assertAlmostEqual(_hhmm_to_hours("00:00"), 0.0)
        self.assertAlmostEqual(_hhmm_to_hours("23:59"), 23 + 59 / 60)

    def test_hhmm_end_to_hours_midnight_is_24(self) -> None:
        """window_end of '00:00' means midnight = end of day = 24.0."""
        self.assertAlmostEqual(_hhmm_end_to_hours("00:00"), 24.0)

    def test_hhmm_end_to_hours_other_times_normal(self) -> None:
        self.assertAlmostEqual(_hhmm_end_to_hours("06:00"), 6.0)
        self.assertAlmostEqual(_hhmm_end_to_hours("21:00"), 21.0)

    def test_hours_to_hhmm(self) -> None:
        self.assertEqual(_hours_to_hhmm(10.5), "10:30")
        self.assertEqual(_hours_to_hhmm(0.0), "00:00")
        self.assertEqual(_hours_to_hhmm(6.75), "06:45")
        self.assertEqual(_hours_to_hhmm(23.0 + 59 / 60), "23:59")
