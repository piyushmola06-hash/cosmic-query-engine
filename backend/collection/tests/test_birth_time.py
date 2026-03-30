"""
Tests for S-02 — Birth Time Tier Detection.

Done condition (from spec):
  Every possible birth time input produces a valid structured output with
  the correct tier. No input causes a crash or silent default. All
  approximate inputs confirmed before locking. Confidence flag correct on
  every non-exact tier.

Coverage:
  - Every phrase in the approximate window table (all 9 bands, all phrases)
  - Exact time in multiple formats: 2:30 PM, 14:30, 1430, 14.30
  - 12-hour edge cases: 12am, 12pm, midnight, noon
  - Hedged exact time → approximate tier
  - Explicit not-knowing statements → none tier
  - Invalid time value (25:00) → none tier, needs_rephrase=True
  - Unrecognised input → none tier, needs_rephrase=True
  - Confidence flag: False for exact, True for all others
  - Time range stated → approximate tier using stated window
  - Output dict matches S-02 contract keys exactly
"""

from django.test import TestCase

from collection.birth_time import BirthTimeTierDetector, BirthTimeResult
from collection.constants import TIER_APPROXIMATE, TIER_EXACT, TIER_NONE


class TestNoneTier(TestCase):
    """None input and explicit not-knowing → TIER_NONE, confidence_flag=True."""

    def setUp(self) -> None:
        self.det = BirthTimeTierDetector()

    def test_none_input(self) -> None:
        r = self.det.classify(None)
        self.assertEqual(r.tier, TIER_NONE)
        self.assertTrue(r.confidence_flag)

    def test_empty_string(self) -> None:
        r = self.det.classify("")
        self.assertEqual(r.tier, TIER_NONE)
        self.assertTrue(r.confidence_flag)

    def test_whitespace_only(self) -> None:
        r = self.det.classify("   ")
        self.assertEqual(r.tier, TIER_NONE)
        self.assertTrue(r.confidence_flag)

    def test_dont_know(self) -> None:
        r = self.det.classify("I don't know")
        self.assertEqual(r.tier, TIER_NONE)
        self.assertTrue(r.confidence_flag)
        self.assertFalse(r.needs_rephrase)

    def test_unknown(self) -> None:
        r = self.det.classify("unknown")
        self.assertEqual(r.tier, TIER_NONE)
        self.assertTrue(r.confidence_flag)

    def test_no_idea(self) -> None:
        r = self.det.classify("no idea")
        self.assertEqual(r.tier, TIER_NONE)
        self.assertTrue(r.confidence_flag)

    def test_cant_remember(self) -> None:
        r = self.det.classify("can't remember")
        self.assertEqual(r.tier, TIER_NONE)
        self.assertTrue(r.confidence_flag)

    def test_skip(self) -> None:
        r = self.det.classify("skip")
        self.assertEqual(r.tier, TIER_NONE)
        self.assertTrue(r.confidence_flag)

    def test_none_tier_normalised_time_is_null(self) -> None:
        r = self.det.classify(None)
        self.assertIsNone(r.normalised_time)
        self.assertIsNone(r.window_start)
        self.assertIsNone(r.window_end)


class TestExactTier(TestCase):
    """Recognisable clock times → TIER_EXACT, confidence_flag=False."""

    def setUp(self) -> None:
        self.det = BirthTimeTierDetector()

    # ── Multiple format coverage ──────────────────────────────────────────────

    def test_hhmm_colon_format(self) -> None:
        r = self.det.classify("14:30")
        self.assertEqual(r.tier, TIER_EXACT)
        self.assertEqual(r.normalised_time, "14:30")
        self.assertFalse(r.confidence_flag)

    def test_12hour_am_pm_format(self) -> None:
        r = self.det.classify("2:30 PM")
        self.assertEqual(r.tier, TIER_EXACT)
        self.assertEqual(r.normalised_time, "14:30")
        self.assertFalse(r.confidence_flag)

    def test_4digit_no_separator(self) -> None:
        """1430 → 14:30"""
        r = self.det.classify("1430")
        self.assertEqual(r.tier, TIER_EXACT)
        self.assertEqual(r.normalised_time, "14:30")
        self.assertFalse(r.confidence_flag)

    def test_dot_separator(self) -> None:
        """14.30 → 14:30"""
        r = self.det.classify("14.30")
        self.assertEqual(r.tier, TIER_EXACT)
        self.assertEqual(r.normalised_time, "14:30")
        self.assertFalse(r.confidence_flag)

    def test_lowercase_am(self) -> None:
        r = self.det.classify("10:30 am")
        self.assertEqual(r.tier, TIER_EXACT)
        self.assertEqual(r.normalised_time, "10:30")
        self.assertFalse(r.confidence_flag)

    def test_hour_only_with_pm(self) -> None:
        r = self.det.classify("3pm")
        self.assertEqual(r.tier, TIER_EXACT)
        self.assertEqual(r.normalised_time, "15:00")
        self.assertFalse(r.confidence_flag)

    def test_hour_only_with_am(self) -> None:
        r = self.det.classify("9am")
        self.assertEqual(r.tier, TIER_EXACT)
        self.assertEqual(r.normalised_time, "09:00")
        self.assertFalse(r.confidence_flag)

    def test_midnight_12am(self) -> None:
        """12am → 00:00"""
        r = self.det.classify("12am")
        self.assertEqual(r.tier, TIER_EXACT)
        self.assertEqual(r.normalised_time, "00:00")
        self.assertFalse(r.confidence_flag)

    def test_noon_12pm(self) -> None:
        """12pm → 12:00"""
        r = self.det.classify("12pm")
        self.assertEqual(r.tier, TIER_EXACT)
        self.assertEqual(r.normalised_time, "12:00")
        self.assertFalse(r.confidence_flag)

    def test_exact_confidence_flag_false(self) -> None:
        r = self.det.classify("08:45")
        self.assertFalse(r.confidence_flag)
        self.assertIsNone(r.confidence_reason)

    def test_exact_windows_are_null(self) -> None:
        r = self.det.classify("14:30")
        self.assertIsNone(r.window_start)
        self.assertIsNone(r.window_end)

    def test_time_in_sentence(self) -> None:
        """Time embedded in natural language."""
        r = self.det.classify("I was born at 10:30 AM")
        self.assertEqual(r.tier, TIER_EXACT)
        self.assertEqual(r.normalised_time, "10:30")


class TestApproximateTier(TestCase):
    """
    Every phrase from the S-02 window table → TIER_APPROXIMATE with correct window.
    confidence_flag must be True for all approximate results.
    """

    def setUp(self) -> None:
        self.det = BirthTimeTierDetector()

    def _assert_window(self, raw: str, expected_start: str, expected_end: str) -> None:
        r = self.det.classify(raw)
        self.assertEqual(r.tier, TIER_APPROXIMATE, f"Expected approximate for {raw!r}")
        self.assertEqual(r.window_start, expected_start, f"Wrong window_start for {raw!r}")
        self.assertEqual(r.window_end, expected_end, f"Wrong window_end for {raw!r}")
        self.assertTrue(r.confidence_flag, f"confidence_flag must be True for {raw!r}")

    # ── Band 1: dawn / early morning / before sunrise → 04:00–06:00 ─────────

    def test_dawn(self) -> None:
        self._assert_window("dawn", "04:00", "06:00")

    def test_early_morning(self) -> None:
        self._assert_window("early morning", "04:00", "06:00")

    def test_before_sunrise(self) -> None:
        self._assert_window("before sunrise", "04:00", "06:00")

    # ── Band 2: morning / in the morning → 06:00–09:00 ───────────────────────

    def test_morning(self) -> None:
        self._assert_window("morning", "06:00", "09:00")

    def test_in_the_morning(self) -> None:
        self._assert_window("in the morning", "06:00", "09:00")

    # ── Band 3: late morning / before noon → 09:00–12:00 ─────────────────────

    def test_late_morning(self) -> None:
        self._assert_window("late morning", "09:00", "12:00")

    def test_before_noon(self) -> None:
        self._assert_window("before noon", "09:00", "12:00")

    # ── Band 4: noon / around noon / midday → 11:00–13:00 ────────────────────

    def test_noon(self) -> None:
        self._assert_window("noon", "11:00", "13:00")

    def test_around_noon(self) -> None:
        self._assert_window("around noon", "11:00", "13:00")

    def test_midday(self) -> None:
        self._assert_window("midday", "11:00", "13:00")

    # ── Band 5: afternoon / in the afternoon → 12:00–15:00 ───────────────────

    def test_afternoon(self) -> None:
        self._assert_window("afternoon", "12:00", "15:00")

    def test_in_the_afternoon(self) -> None:
        self._assert_window("in the afternoon", "12:00", "15:00")

    # ── Band 6: late afternoon / evening started → 15:00–18:00 ──────────────

    def test_late_afternoon(self) -> None:
        self._assert_window("late afternoon", "15:00", "18:00")

    def test_evening_started(self) -> None:
        self._assert_window("evening started", "15:00", "18:00")

    # ── Band 7: evening / in the evening / after sunset → 18:00–21:00 ───────

    def test_evening(self) -> None:
        self._assert_window("evening", "18:00", "21:00")

    def test_in_the_evening(self) -> None:
        self._assert_window("in the evening", "18:00", "21:00")

    def test_after_sunset(self) -> None:
        self._assert_window("after sunset", "18:00", "21:00")

    # ── Band 8: night / at night → 21:00–00:00 ───────────────────────────────

    def test_night(self) -> None:
        self._assert_window("night", "21:00", "00:00")

    def test_at_night(self) -> None:
        self._assert_window("at night", "21:00", "00:00")

    # ── Band 9: late night / past midnight / early hours → 00:00–04:00 ───────

    def test_late_night(self) -> None:
        self._assert_window("late night", "00:00", "04:00")

    def test_past_midnight(self) -> None:
        self._assert_window("past midnight", "00:00", "04:00")

    def test_early_hours(self) -> None:
        self._assert_window("early hours", "00:00", "04:00")

    # ── Specificity: late morning must not match 'morning' window ─────────────

    def test_late_morning_not_matched_as_plain_morning(self) -> None:
        r = self.det.classify("late morning")
        self.assertEqual(r.window_start, "09:00")
        self.assertEqual(r.window_end, "12:00")

    def test_late_afternoon_not_matched_as_plain_afternoon(self) -> None:
        r = self.det.classify("late afternoon")
        self.assertEqual(r.window_start, "15:00")
        self.assertEqual(r.window_end, "18:00")

    def test_late_night_not_matched_as_plain_night(self) -> None:
        r = self.det.classify("late night")
        self.assertEqual(r.window_start, "00:00")
        self.assertEqual(r.window_end, "04:00")

    # ── Approximate normalised_time is null ───────────────────────────────────

    def test_approximate_normalised_time_null_for_word_inputs(self) -> None:
        r = self.det.classify("morning")
        self.assertIsNone(r.normalised_time)


class TestHedgedExactTime(TestCase):
    """
    Specific times qualified with uncertainty → TIER_APPROXIMATE, not TIER_EXACT.
    Per spec: the stated time is the centre of a 2-hour window.
    """

    def setUp(self) -> None:
        self.det = BirthTimeTierDetector()

    def test_i_think_it_was_3pm(self) -> None:
        r = self.det.classify("I think it was around 3pm but I'm not sure")
        self.assertEqual(r.tier, TIER_APPROXIMATE)
        self.assertTrue(r.confidence_flag)

    def test_maybe_10_30(self) -> None:
        r = self.det.classify("maybe 10:30")
        self.assertEqual(r.tier, TIER_APPROXIMATE)
        self.assertTrue(r.confidence_flag)

    def test_around_2pm(self) -> None:
        r = self.det.classify("around 2pm")
        self.assertEqual(r.tier, TIER_APPROXIMATE)
        # 2pm = 14:00, ±1h → 13:00–15:00
        self.assertEqual(r.window_start, "13:00")
        self.assertEqual(r.window_end, "15:00")

    def test_probably_1430(self) -> None:
        r = self.det.classify("probably 14:30")
        self.assertEqual(r.tier, TIER_APPROXIMATE)
        self.assertEqual(r.window_start, "13:30")
        self.assertEqual(r.window_end, "15:30")

    def test_hedged_normalised_time_preserved(self) -> None:
        """Normalised time is preserved for hedged inputs (centre of window)."""
        r = self.det.classify("I think 2:30 PM")
        self.assertEqual(r.normalised_time, "14:30")

    def test_hedged_confidence_flag_true(self) -> None:
        r = self.det.classify("roughly 9am")
        self.assertTrue(r.confidence_flag)


class TestInvalidTime(TestCase):
    """
    Invalid time values → TIER_NONE after one rephrase.
    Per spec: flag as invalid, ask once, then none tier.
    """

    def setUp(self) -> None:
        self.det = BirthTimeTierDetector()

    def test_hour_25_invalid(self) -> None:
        r = self.det.classify("25:00")
        self.assertEqual(r.tier, TIER_NONE)
        self.assertTrue(r.confidence_flag)
        self.assertTrue(r.needs_rephrase)

    def test_minute_60_invalid(self) -> None:
        r = self.det.classify("10:60")
        self.assertEqual(r.tier, TIER_NONE)
        self.assertTrue(r.needs_rephrase)

    def test_hour_99_invalid(self) -> None:
        r = self.det.classify("99:00")
        self.assertEqual(r.tier, TIER_NONE)
        self.assertTrue(r.needs_rephrase)

    def test_nonsense_single_digit(self) -> None:
        """Single digit without am/pm → unrecognised → needs_rephrase."""
        r = self.det.classify("3")
        self.assertEqual(r.tier, TIER_NONE)
        self.assertTrue(r.needs_rephrase)

    def test_complete_gibberish(self) -> None:
        r = self.det.classify("xyzzy banana")
        self.assertEqual(r.tier, TIER_NONE)
        self.assertTrue(r.needs_rephrase)

    def test_invalid_time_no_needs_rephrase_on_second_pass(self) -> None:
        """
        After needs_rephrase=True, the caller re-asks once. If the second
        input is also unrecognisable, none tier is accepted without further
        rephrase. The detector itself always returns needs_rephrase=True for
        invalid input — the caller is responsible for enforcing the one-ask limit.
        """
        r1 = self.det.classify("25:00")
        self.assertTrue(r1.needs_rephrase)
        # Simulate caller accepting none tier on second failure
        r2 = self.det.classify("still nonsense")
        self.assertEqual(r2.tier, TIER_NONE)


class TestTimeRange(TestCase):
    """Time range explicitly stated → TIER_APPROXIMATE using stated window."""

    def setUp(self) -> None:
        self.det = BirthTimeTierDetector()

    def test_between_2pm_and_4pm(self) -> None:
        r = self.det.classify("between 2pm and 4pm")
        self.assertEqual(r.tier, TIER_APPROXIMATE)
        self.assertEqual(r.window_start, "14:00")
        self.assertEqual(r.window_end, "16:00")

    def test_24h_range(self) -> None:
        r = self.det.classify("14:00 - 16:00")
        self.assertEqual(r.tier, TIER_APPROXIMATE)
        self.assertEqual(r.window_start, "14:00")
        self.assertEqual(r.window_end, "16:00")


class TestOutputShape(TestCase):
    """to_dict() returns the exact keys specified in the S-02 contract."""

    REQUIRED_KEYS = {
        "tier", "normalised_time", "window_start",
        "window_end", "confidence_flag", "confidence_reason",
    }

    def setUp(self) -> None:
        self.det = BirthTimeTierDetector()

    def _assert_shape(self, raw: str) -> None:
        d = self.det.classify(raw).to_dict()
        for key in self.REQUIRED_KEYS:
            self.assertIn(key, d, f"Output missing required key {key!r} for input {raw!r}")
        # needs_rephrase must NOT appear in the contract output
        self.assertNotIn("needs_rephrase", d)

    def test_exact_output_shape(self) -> None:
        self._assert_shape("14:30")

    def test_approximate_output_shape(self) -> None:
        self._assert_shape("morning")

    def test_none_output_shape(self) -> None:
        self._assert_shape("I don't know")

    def test_invalid_output_shape(self) -> None:
        self._assert_shape("25:00")


class TestConfidenceFlag(TestCase):
    """confidence_flag is False only for exact tier; True for all others."""

    def setUp(self) -> None:
        self.det = BirthTimeTierDetector()

    def test_exact_confidence_false(self) -> None:
        self.assertFalse(self.det.classify("14:30").confidence_flag)
        self.assertFalse(self.det.classify("2:30 PM").confidence_flag)
        self.assertFalse(self.det.classify("1430").confidence_flag)

    def test_approximate_confidence_true(self) -> None:
        self.assertTrue(self.det.classify("morning").confidence_flag)
        self.assertTrue(self.det.classify("evening").confidence_flag)
        self.assertTrue(self.det.classify("around 3pm").confidence_flag)

    def test_none_confidence_true(self) -> None:
        self.assertTrue(self.det.classify(None).confidence_flag)
        self.assertTrue(self.det.classify("I don't know").confidence_flag)
        self.assertTrue(self.det.classify("25:00").confidence_flag)
