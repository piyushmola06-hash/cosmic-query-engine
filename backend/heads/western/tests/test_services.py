"""
Tests for S-06 — Western Astrology Head Engine.

Done condition:
  All three tiers produce valid output. Cusp handling correct for all tiers.
  S-03 moon_sign_certain inherited correctly — never recomputed.
  Tendency window in weeks or null.
"""

from datetime import date

from django.test import SimpleTestCase

try:
    import swisseph as swe
    _SWE_AVAILABLE = True
except ImportError:
    _SWE_AVAILABLE = False

from heads.western.services import (
    ASPECTS,
    ASPECT_ORB,
    MAX_ASPECTS,
    SIGNS,
    WesternHeadEngine,
    _angular_separation,
    _aspect_orb,
    _EPH_PATH,
    compute_aspects,
    compute_houses,
    compute_planetary_positions,
    compute_sun_sign,
    compute_tendency_window,
    detect_chart_pattern,
    longitude_to_sign,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

_DOB_ARIES = {"day": 5, "month": 4, "year": 1990}       # Sun in Aries (mid-sign)
_DOB_PISCES_CUSP = {"day": 20, "month": 3, "year": 1990}  # Near Pisces/Aries cusp
_DOB_1990 = {"day": 15, "month": 3, "year": 1990}        # Sun near Pisces
_BIRTH_TIME_EXACT = {"tier": "exact", "normalised_time": "10:30", "window_start": None, "window_end": None}
_BIRTH_TIME_APPROX = {"tier": "approximate", "normalised_time": None, "window_start": "08:00", "window_end": "12:00"}
_BIRTH_TIME_NONE = {"tier": "none", "normalised_time": None, "window_start": None, "window_end": None}
_LOCATION_LONDON = {"city": "London", "country": "UK"}
_LOCATION_UNKNOWN = {"city": "Atlantis", "country": "Mythland"}
_LOCATION_EXTREME = {"city": "Longyearbyen", "country": "Norway"}  # 78°N — triggers Placidus fallback
_MOON_S03 = {"moon_sign": "Scorpio", "moon_sign_certain": True, "transition_occurred": False}
_MOON_UNCERTAIN = {"moon_sign": "Libra", "moon_sign_certain": False, "transition_occurred": True}
_TODAY = date(2026, 4, 3)
_QUERY_CAREER = "What does my career look like?"
_QUERY_RELATIONSHIP = "Will I find love soon?"
_QUERY_GENERIC = "What should I focus on?"


def _engine() -> WesternHeadEngine:
    return WesternHeadEngine()


def _result_exact(
    dob: dict = _DOB_ARIES,
    moon: dict = _MOON_S03,
    query: str = _QUERY_CAREER,
    location: dict = _LOCATION_LONDON,
) -> dict:
    return _engine().compute(
        dob=dob, birth_time=_BIRTH_TIME_EXACT,
        birth_location=location, gender="male",
        moon=moon, query=query, today=_TODAY,
    )


def _result_approx(query: str = _QUERY_CAREER) -> dict:
    return _engine().compute(
        dob=_DOB_ARIES, birth_time=_BIRTH_TIME_APPROX,
        birth_location=_LOCATION_LONDON, gender=None,
        moon=_MOON_S03, query=query, today=_TODAY,
    )


def _result_none(query: str = _QUERY_CAREER) -> dict:
    return _engine().compute(
        dob=_DOB_ARIES, birth_time=_BIRTH_TIME_NONE,
        birth_location=_LOCATION_LONDON, gender=None,
        moon=_MOON_S03, query=query, today=_TODAY,
    )


# ── Pure math helpers ─────────────────────────────────────────────────────────

class TestLongitudeToSign(SimpleTestCase):
    """Tropical longitude → sign name."""

    def test_aries_start(self) -> None:
        self.assertEqual(longitude_to_sign(0.0), "Aries")

    def test_aries_mid(self) -> None:
        self.assertEqual(longitude_to_sign(15.0), "Aries")

    def test_taurus(self) -> None:
        self.assertEqual(longitude_to_sign(30.0), "Taurus")

    def test_scorpio(self) -> None:
        self.assertEqual(longitude_to_sign(219.0), "Scorpio")

    def test_pisces(self) -> None:
        self.assertEqual(longitude_to_sign(350.0), "Pisces")

    def test_wraps_at_360(self) -> None:
        self.assertEqual(longitude_to_sign(360.0), "Aries")

    def test_all_12_signs_covered(self) -> None:
        signs = {longitude_to_sign(i * 30.0) for i in range(12)}
        self.assertEqual(signs, set(SIGNS))


class TestAngularSeparation(SimpleTestCase):
    """_angular_separation always returns value in [0, 180]."""

    def test_same_longitude(self) -> None:
        self.assertAlmostEqual(_angular_separation(45.0, 45.0), 0.0)

    def test_opposition(self) -> None:
        self.assertAlmostEqual(_angular_separation(0.0, 180.0), 180.0)

    def test_trine(self) -> None:
        self.assertAlmostEqual(_angular_separation(0.0, 120.0), 120.0)

    def test_wraparound(self) -> None:
        # 350° to 10° = 20°, not 340°
        self.assertAlmostEqual(_angular_separation(350.0, 10.0), 20.0)

    def test_always_in_range(self) -> None:
        for a in range(0, 360, 15):
            for b in range(0, 360, 15):
                sep = _angular_separation(float(a), float(b))
                self.assertGreaterEqual(sep, 0.0)
                self.assertLessEqual(sep, 180.0)


class TestAspectOrb(SimpleTestCase):
    """Aspect orb detection within ASPECT_ORB tolerance."""

    def test_exact_conjunction(self) -> None:
        orb = _aspect_orb(45.0, 45.0, 0.0)
        self.assertIsNotNone(orb)
        self.assertAlmostEqual(orb, 0.0)

    def test_conjunction_within_orb(self) -> None:
        orb = _aspect_orb(45.0, 50.0, 0.0)
        self.assertIsNotNone(orb)
        self.assertAlmostEqual(orb, 5.0)

    def test_conjunction_outside_orb(self) -> None:
        orb = _aspect_orb(45.0, 55.0, 0.0)
        self.assertIsNone(orb)

    def test_exact_trine(self) -> None:
        orb = _aspect_orb(0.0, 120.0, 120.0)
        self.assertIsNotNone(orb)
        self.assertAlmostEqual(orb, 0.0)

    def test_trine_within_orb(self) -> None:
        orb = _aspect_orb(0.0, 125.0, 120.0)
        self.assertIsNotNone(orb)
        self.assertAlmostEqual(orb, 5.0)

    def test_opposition(self) -> None:
        orb = _aspect_orb(0.0, 180.0, 180.0)
        self.assertIsNotNone(orb)
        self.assertAlmostEqual(orb, 0.0)

    def test_no_aspect_between_angles(self) -> None:
        # 45° separation doesn't match any standard aspect within 8°
        orb = _aspect_orb(0.0, 45.0, 90.0)  # 45° away from square
        self.assertIsNone(orb)


# ── Sun sign tests ────────────────────────────────────────────────────────────

class TestSunSign(SimpleTestCase):
    """Sun sign and cusp handling."""

    def setUp(self) -> None:
        if not _SWE_AVAILABLE:
            self.skipTest("pyswisseph not installed")
        swe.set_ephe_path(_EPH_PATH)

    def test_aries_mid_sign_certain(self) -> None:
        """April 5 is solidly in Aries."""
        jd = swe.julday(1990, 4, 5, 12.0)
        sign, certain = compute_sun_sign(_DOB_ARIES, 12.0, jd)
        self.assertEqual(sign, "Aries")
        self.assertTrue(certain)

    def test_cusp_date_flagged_uncertain(self) -> None:
        """March 20 is near Pisces/Aries cusp."""
        jd = swe.julday(1990, 3, 20, 12.0)
        sign, certain = compute_sun_sign(_DOB_PISCES_CUSP, 12.0, jd)
        # Should be flagged uncertain (near boundary)
        self.assertFalse(certain)

    def test_sun_in_scorpio_for_november_date(self) -> None:
        dob = {"day": 5, "month": 11, "year": 1990}
        jd = swe.julday(1990, 11, 5, 12.0)
        sign, _ = compute_sun_sign(dob, 12.0, jd)
        self.assertEqual(sign, "Scorpio")

    def test_sun_sign_is_valid_sign(self) -> None:
        for dob in [_DOB_ARIES, _DOB_1990, _DOB_PISCES_CUSP]:
            jd = swe.julday(dob["year"], dob["month"], dob["day"], 12.0)
            sign, _ = compute_sun_sign(dob, 12.0, jd)
            self.assertIn(sign, SIGNS)

    def test_tropical_vs_sidereal_sun_differ(self) -> None:
        """
        Tropical sun sign (Western) and sidereal (Vedic) differ for the same DOB.
        For 1990-04-05, tropical sun is ~15° Aries;
        sidereal sun (Lahiri ~23.7° ayanamsha) is ~351° Pisces.
        """
        jd = swe.julday(1990, 4, 5, 12.0)
        # Tropical
        result_tropical, _ = swe.calc_ut(jd, swe.SUN)
        tropical_lon = result_tropical[0] % 360.0
        tropical_sign = longitude_to_sign(tropical_lon)
        self.assertEqual(tropical_sign, "Aries")
        # Sidereal
        swe.set_sid_mode(swe.SIDM_LAHIRI)
        result_sidereal, _ = swe.calc_ut(jd, swe.SUN, swe.FLG_SIDEREAL)
        sidereal_lon = result_sidereal[0] % 360.0
        sidereal_sign = longitude_to_sign(sidereal_lon)
        self.assertEqual(sidereal_sign, "Pisces")
        # Western (tropical) and Vedic (sidereal) disagree — this is correct
        self.assertNotEqual(tropical_sign, sidereal_sign)


# ── Moon sign inheritance tests ───────────────────────────────────────────────

class TestMoonSignInheritance(SimpleTestCase):
    """Moon sign is inherited from S-03, never recomputed."""

    def test_moon_sign_matches_s03_input(self) -> None:
        result = _result_exact(moon=_MOON_S03)
        self.assertEqual(result["findings"]["moon_sign"], "Scorpio")

    def test_moon_sign_certain_matches_s03(self) -> None:
        result = _result_exact(moon=_MOON_S03)
        self.assertTrue(result["findings"]["moon_sign_certain"])

    def test_uncertain_moon_inherited_correctly(self) -> None:
        result = _result_exact(moon=_MOON_UNCERTAIN)
        self.assertEqual(result["findings"]["moon_sign"], "Libra")
        self.assertFalse(result["findings"]["moon_sign_certain"])

    def test_different_moon_input_different_output(self) -> None:
        """Moon sign output changes when S-03 input changes — proving it's inherited."""
        moon_a = {"moon_sign": "Aries", "moon_sign_certain": True, "transition_occurred": False}
        moon_b = {"moon_sign": "Capricorn", "moon_sign_certain": True, "transition_occurred": False}
        result_a = _result_exact(moon=moon_a)
        result_b = _result_exact(moon=moon_b)
        self.assertEqual(result_a["findings"]["moon_sign"], "Aries")
        self.assertEqual(result_b["findings"]["moon_sign"], "Capricorn")

    def test_moon_sign_trail_section_says_from_s03(self) -> None:
        """Trail must clarify moon sign came from S-03."""
        sections = {
            s["title"]: s
            for s in _result_exact()["explainability_trail"]["sections"]
        }
        self.assertIn("Moon Sign", sections)
        self.assertIn("S-03", sections["Moon Sign"]["content"])


# ── Aspect computation tests ──────────────────────────────────────────────────

class TestAspectComputation(SimpleTestCase):
    """Aspect detection with orb tolerance."""

    def test_conjunction_detected(self) -> None:
        positions = {"Sun": 10.0, "Mercury": 14.0}  # 4° conjunction
        aspects = compute_aspects(positions)
        self.assertTrue(any(a["aspect"] == "Conjunction" for a in aspects))

    def test_trine_detected(self) -> None:
        positions = {"Sun": 0.0, "Jupiter": 122.0}  # 2° from exact trine
        aspects = compute_aspects(positions)
        self.assertTrue(any(a["aspect"] == "Trine" for a in aspects))

    def test_no_aspect_outside_orb(self) -> None:
        positions = {"Sun": 0.0, "Saturn": 45.0}  # 45° — no major aspect
        aspects = compute_aspects(positions)
        self.assertEqual(aspects, [])

    def test_max_aspects_capped_at_8(self) -> None:
        # Create many planets all conjunct — generates many aspects
        positions = {f"Planet{i}": float(i) * 2 for i in range(10)}
        aspects = compute_aspects(positions)
        self.assertLessEqual(len(aspects), MAX_ASPECTS)

    def test_sorted_by_tightest_orb(self) -> None:
        positions = {
            "Sun": 0.0,
            "Moon": 120.0,     # exact trine (0° orb)
            "Mars": 125.0,     # 5° from trine
            "Jupiter": 115.0,  # 5° from trine
        }
        aspects = compute_aspects(positions)
        orbs = [a["orb"] for a in aspects]
        self.assertEqual(orbs, sorted(orbs))

    def test_each_aspect_has_required_fields(self) -> None:
        positions = {"Sun": 0.0, "Moon": 120.0}
        aspects = compute_aspects(positions)
        for a in aspects:
            for field in ("planet1", "planet2", "aspect", "orb"):
                self.assertIn(field, a)

    def test_aspect_orb_is_within_tolerance(self) -> None:
        positions = {"Sun": 0.0, "Mercury": 7.9}  # within 8°
        aspects = compute_aspects(positions)
        for a in aspects:
            self.assertLessEqual(a["orb"], ASPECT_ORB)


# ── Chart pattern tests ───────────────────────────────────────────────────────

class TestChartPattern(SimpleTestCase):
    """Chart pattern detection from planetary distribution."""

    def test_bundle_all_within_120(self) -> None:
        positions = {f"p{i}": float(i * 10) for i in range(6)}  # all within 50°
        pattern = detect_chart_pattern(positions)
        self.assertEqual(pattern, "Bundle")

    def test_bowl_within_180(self) -> None:
        # Planets spread across 140° — gap of 220° → Bowl
        positions = {f"p{i}": float(i * 28) for i in range(6)}  # 0 to 140°
        pattern = detect_chart_pattern(positions)
        self.assertEqual(pattern, "Bowl")

    def test_splash_spread_across_chart(self) -> None:
        positions = {f"p{i}": float(i * 30) for i in range(12)}  # one per sign
        pattern = detect_chart_pattern(positions)
        self.assertEqual(pattern, "Splash")

    def test_pattern_is_string_or_none(self) -> None:
        positions = {"Sun": 0.0, "Moon": 120.0, "Mars": 240.0}
        result = detect_chart_pattern(positions)
        self.assertTrue(result is None or isinstance(result, str))

    def test_insufficient_planets_returns_none(self) -> None:
        self.assertIsNone(detect_chart_pattern({"Sun": 0.0, "Moon": 30.0}))


# ── Placidus fallback tests ───────────────────────────────────────────────────

class TestPlacidus(SimpleTestCase):
    """Placidus falls back to whole sign for extreme latitudes."""

    def setUp(self) -> None:
        if not _SWE_AVAILABLE:
            self.skipTest("pyswisseph not installed")
        swe.set_ephe_path(_EPH_PATH)

    def test_extreme_latitude_uses_whole_sign(self) -> None:
        """Longyearbyen at 78°N triggers whole sign fallback."""
        result = _result_exact(location=_LOCATION_EXTREME)
        # Should still compute successfully
        self.assertEqual(result["head"], "western")
        # Confidence flag should be set due to fallback
        self.assertTrue(result["confidence_flag"])
        # Confidence reason should mention latitude or whole sign
        reason = result.get("confidence_reason") or ""
        self.assertTrue(
            "latitude" in reason.lower() or "whole sign" in reason.lower() or "placidus" in reason.lower(),
            msg=f"Expected latitude/whole-sign mention in reason: {reason}"
        )

    def test_normal_latitude_uses_placidus(self) -> None:
        """London at 51°N uses Placidus normally."""
        result = _result_exact(location=_LOCATION_LONDON)
        f = result["findings"]
        if f["rising_sign_available"]:
            # If rising computed, it should be a valid sign
            self.assertIn(f["rising_sign"], SIGNS)

    def test_houses_returned_for_extreme_latitude(self) -> None:
        """Even at extreme latitude, houses dict is populated (whole sign)."""
        result = _result_exact(location=_LOCATION_EXTREME)
        f = result["findings"]
        if f["rising_sign_available"]:
            for house_label in ("1st", "7th", "10th"):
                self.assertIn(house_label, f["houses"])


# ── Three-tier tests ──────────────────────────────────────────────────────────

class TestExactTier(SimpleTestCase):
    """Exact tier — full computation including rising sign."""

    def test_head_is_western(self) -> None:
        self.assertEqual(_result_exact()["head"], "western")

    def test_sun_sign_present(self) -> None:
        f = _result_exact()["findings"]
        self.assertIn(f["sun_sign"], SIGNS)

    def test_moon_sign_matches_s03(self) -> None:
        self.assertEqual(_result_exact()["findings"]["moon_sign"], "Scorpio")

    def test_rising_sign_available_for_known_city(self) -> None:
        f = _result_exact(location=_LOCATION_LONDON)["findings"]
        self.assertTrue(f["rising_sign_available"])
        self.assertIn(f["rising_sign"], SIGNS)

    def test_houses_populated_for_known_city(self) -> None:
        f = _result_exact(location=_LOCATION_LONDON)["findings"]
        if f["rising_sign_available"]:
            self.assertEqual(len(f["houses"]), 12)
            for v in f["houses"].values():
                self.assertIn(v, SIGNS)

    def test_midheaven_available(self) -> None:
        f = _result_exact(location=_LOCATION_LONDON)["findings"]
        if f["rising_sign_available"]:
            self.assertTrue(f["midheaven_available"])
            self.assertIn(f["midheaven"], SIGNS)

    def test_aspects_list_present(self) -> None:
        f = _result_exact()["findings"]
        self.assertIsInstance(f["aspects"], list)
        self.assertLessEqual(len(f["aspects"]), MAX_ASPECTS)

    def test_chart_pattern_set(self) -> None:
        f = _result_exact()["findings"]
        # chart_pattern may be None if positions unavailable
        if f.get("chart_pattern") is not None:
            valid_patterns = {"Bundle", "Bowl", "Bucket", "Locomotive", "Seesaw", "Splash"}
            self.assertIn(f["chart_pattern"], valid_patterns)

    def test_planetary_signs_are_valid(self) -> None:
        f = _result_exact()["findings"]
        for field in ("mercury_sign", "venus_sign", "mars_sign",
                      "jupiter_sign", "saturn_sign"):
            val = f[field]
            if val is not None:
                self.assertIn(val, SIGNS)


class TestApproximateTier(SimpleTestCase):
    """Approximate tier — no rising sign / houses / midheaven."""

    def test_rising_sign_not_available(self) -> None:
        f = _result_approx()["findings"]
        self.assertFalse(f["rising_sign_available"])
        self.assertIsNone(f["rising_sign"])

    def test_midheaven_not_available(self) -> None:
        f = _result_approx()["findings"]
        self.assertFalse(f["midheaven_available"])
        self.assertIsNone(f["midheaven"])

    def test_houses_all_null(self) -> None:
        f = _result_approx()["findings"]
        for v in f["houses"].values():
            self.assertIsNone(v)

    def test_confidence_flag_true(self) -> None:
        self.assertTrue(_result_approx()["confidence_flag"])

    def test_confidence_reason_set(self) -> None:
        self.assertIsNotNone(_result_approx()["confidence_reason"])

    def test_sun_sign_still_present(self) -> None:
        self.assertIn(_result_approx()["findings"]["sun_sign"], SIGNS)

    def test_moon_sign_inherited(self) -> None:
        self.assertEqual(_result_approx()["findings"]["moon_sign"], "Scorpio")

    def test_rising_in_unavailable_findings(self) -> None:
        self.assertIn("rising_sign", _result_approx()["unavailable_findings"])


class TestNoneTier(SimpleTestCase):
    """None tier — same as approximate."""

    def test_rising_sign_not_available(self) -> None:
        self.assertFalse(_result_none()["findings"]["rising_sign_available"])

    def test_confidence_flag_true(self) -> None:
        self.assertTrue(_result_none()["confidence_flag"])

    def test_moon_sign_inherited(self) -> None:
        self.assertEqual(_result_none()["findings"]["moon_sign"], "Scorpio")

    def test_sun_sign_present(self) -> None:
        self.assertIn(_result_none()["findings"]["sun_sign"], SIGNS)

    def test_trail_complete_all_sections(self) -> None:
        titles = {s["title"] for s in _result_none()["explainability_trail"]["sections"]}
        for expected in (
            "Sun Sign", "Moon Sign", "Rising Sign", "Planetary Positions",
            "Houses", "Midheaven", "Aspects", "Chart Pattern",
            "Current Transits", "Query-Relevant Findings",
        ):
            self.assertIn(expected, titles)


# ── Output shape tests ────────────────────────────────────────────────────────

class TestOutputShape(SimpleTestCase):
    """Output structure matches S-06 contract."""

    def test_top_level_keys(self) -> None:
        for result in (_result_exact(), _result_approx(), _result_none()):
            for key in ("head", "available_findings", "unavailable_findings",
                        "findings", "confidence_flag", "confidence_reason",
                        "explainability_trail"):
                self.assertIn(key, result)

    def test_findings_has_all_required_keys(self) -> None:
        f = _result_exact()["findings"]
        required = (
            "sun_sign", "sun_sign_certain", "moon_sign", "moon_sign_certain",
            "rising_sign", "rising_sign_available", "mercury_sign", "venus_sign",
            "mars_sign", "jupiter_sign", "saturn_sign", "north_node_sign",
            "south_node_sign", "houses", "midheaven", "midheaven_available",
            "aspects", "current_transits", "chart_pattern",
            "query_relevant_findings", "tendency_window_weeks",
        )
        for key in required:
            self.assertIn(key, f, msg=f"Missing key: {key}")

    def test_houses_dict_has_12_entries(self) -> None:
        f = _result_exact()["findings"]
        self.assertEqual(len(f["houses"]), 12)

    def test_houses_keys_are_ordinal(self) -> None:
        expected = {"1st", "2nd", "3rd", "4th", "5th", "6th",
                    "7th", "8th", "9th", "10th", "11th", "12th"}
        self.assertEqual(set(_result_exact()["findings"]["houses"].keys()), expected)

    def test_trail_label_is_western_astrology(self) -> None:
        self.assertEqual(
            _result_exact()["explainability_trail"]["label"],
            "Western astrology",
        )

    def test_trail_sections_have_required_fields(self) -> None:
        for s in _result_exact()["explainability_trail"]["sections"]:
            self.assertIn("title", s)
            self.assertIn("content", s)
            self.assertIn("available", s)


# ── query_relevant_findings tests ─────────────────────────────────────────────

class TestQueryRelevantFindings(SimpleTestCase):
    """query_relevant_findings never empty."""

    def _qrf(self, query: str, tier: str = "none") -> list[dict]:
        if tier == "exact":
            result = _result_exact(query=query)
        elif tier == "approximate":
            result = _result_approx(query=query)
        else:
            result = _result_none(query=query)
        return result["findings"]["query_relevant_findings"]

    def test_never_empty_career(self) -> None:
        self.assertGreater(len(self._qrf("What about my career?")), 0)

    def test_never_empty_relationship(self) -> None:
        self.assertGreater(len(self._qrf("Will I find love?")), 0)

    def test_never_empty_finance(self) -> None:
        self.assertGreater(len(self._qrf("How is my financial situation?")), 0)

    def test_never_empty_health(self) -> None:
        self.assertGreater(len(self._qrf("How is my health?")), 0)

    def test_never_empty_travel(self) -> None:
        self.assertGreater(len(self._qrf("Should I travel abroad?")), 0)

    def test_never_empty_direction(self) -> None:
        self.assertGreater(len(self._qrf("What direction should my life go?")), 0)

    def test_never_empty_generic(self) -> None:
        self.assertGreater(len(self._qrf("")), 0)

    def test_never_empty_all_tiers(self) -> None:
        for tier in ("exact", "approximate", "none"):
            qrf = self._qrf("What should I focus on?", tier=tier)
            self.assertGreater(len(qrf), 0, msg=f"Empty for tier={tier}")

    def test_each_entry_has_required_fields(self) -> None:
        for item in self._qrf("What about my career?"):
            self.assertIn("finding", item)
            self.assertIn("value", item)
            self.assertIn("note", item)

    def test_career_includes_saturn(self) -> None:
        findings = [i["finding"] for i in self._qrf("What does my career look like?")]
        self.assertIn("saturn", findings)

    def test_relationship_includes_venus(self) -> None:
        findings = [i["finding"] for i in self._qrf("Will I find love?")]
        self.assertIn("venus", findings)


# ── Tendency window tests ─────────────────────────────────────────────────────

class TestTendencyWindow(SimpleTestCase):
    """Tendency window is in weeks {min, max} or null."""

    def _tw(self, result: dict) -> object:
        return result["findings"]["tendency_window_weeks"]

    def test_tendency_window_is_dict_or_none(self) -> None:
        for result in (_result_exact(), _result_approx(), _result_none()):
            tw = self._tw(result)
            self.assertTrue(tw is None or isinstance(tw, dict))

    def test_tendency_window_has_min_max_when_set(self) -> None:
        for result in (_result_exact(), _result_approx(), _result_none()):
            tw = self._tw(result)
            if tw is not None:
                self.assertIn("min", tw)
                self.assertIn("max", tw)

    def test_tendency_window_min_lte_max(self) -> None:
        for result in (_result_exact(), _result_approx(), _result_none()):
            tw = self._tw(result)
            if tw is not None:
                self.assertLessEqual(tw["min"], tw["max"])

    def test_tendency_window_positive_when_set(self) -> None:
        for result in (_result_exact(), _result_approx(), _result_none()):
            tw = self._tw(result)
            if tw is not None:
                self.assertGreater(tw["min"], 0)
                self.assertGreater(tw["max"], 0)

    def test_tendency_window_within_26_weeks(self) -> None:
        """Max weeks should not exceed 6-month window."""
        for result in (_result_exact(), _result_approx(), _result_none()):
            tw = self._tw(result)
            if tw is not None:
                self.assertLessEqual(tw["max"], 26.0)


# ── Confidence flag tests ─────────────────────────────────────────────────────

class TestConfidenceFlag(SimpleTestCase):
    """Confidence flag correctly set per tier."""

    def test_approximate_tier_flag_true(self) -> None:
        self.assertTrue(_result_approx()["confidence_flag"])

    def test_none_tier_flag_true(self) -> None:
        self.assertTrue(_result_none()["confidence_flag"])

    def test_unknown_location_sets_flag(self) -> None:
        result = _result_exact(location=_LOCATION_UNKNOWN)
        self.assertTrue(result["confidence_flag"])

    def test_confidence_flag_is_bool(self) -> None:
        for result in (_result_exact(), _result_approx(), _result_none()):
            self.assertIsInstance(result["confidence_flag"], bool)

    def test_approximate_confidence_reason_mentions_tier(self) -> None:
        reason = _result_approx()["confidence_reason"] or ""
        self.assertIn("approximate", reason.lower())


# ── Unavailable findings tests ────────────────────────────────────────────────

class TestUnavailableFindings(SimpleTestCase):
    """Unavailable findings listed; trail sections explain."""

    def test_rising_in_unavailable_for_approximate(self) -> None:
        self.assertIn("rising_sign", _result_approx()["unavailable_findings"])

    def test_rising_in_unavailable_for_none(self) -> None:
        self.assertIn("rising_sign", _result_none()["unavailable_findings"])

    def test_rising_in_unavailable_for_unknown_city(self) -> None:
        result = _result_exact(location=_LOCATION_UNKNOWN)
        self.assertIn("rising_sign", result["unavailable_findings"])

    def test_rising_trail_section_unavailable_for_approx(self) -> None:
        sections = {s["title"]: s for s in _result_approx()["explainability_trail"]["sections"]}
        self.assertIn("Rising Sign", sections)
        self.assertFalse(sections["Rising Sign"]["available"])

    def test_unavailable_sections_have_non_empty_content(self) -> None:
        for s in _result_approx()["explainability_trail"]["sections"]:
            if not s["available"]:
                self.assertGreater(len(s["content"]), 0)


# ── Cusp handling tests ───────────────────────────────────────────────────────

class TestCuspHandling(SimpleTestCase):
    """Sun sign cusp detection is correct for all tiers."""

    def setUp(self) -> None:
        if not _SWE_AVAILABLE:
            self.skipTest("pyswisseph not installed")
        swe.set_ephe_path(_EPH_PATH)

    def test_cusp_date_uncertain_for_none_tier(self) -> None:
        """March 20 (cusp) with none tier → uncertain."""
        result = _engine().compute(
            dob=_DOB_PISCES_CUSP, birth_time=_BIRTH_TIME_NONE,
            birth_location=_LOCATION_LONDON, gender=None,
            moon=_MOON_S03, query=_QUERY_GENERIC, today=_TODAY,
        )
        self.assertFalse(result["findings"]["sun_sign_certain"])

    def test_mid_sign_date_certain(self) -> None:
        """April 5 (mid-Aries) → certain."""
        result = _result_exact(dob=_DOB_ARIES)
        self.assertTrue(result["findings"]["sun_sign_certain"])

    def test_cusp_trail_mentions_cusp(self) -> None:
        """Trail section mentions cusp uncertainty when flagged."""
        result = _engine().compute(
            dob=_DOB_PISCES_CUSP, birth_time=_BIRTH_TIME_NONE,
            birth_location=_LOCATION_LONDON, gender=None,
            moon=_MOON_S03, query=_QUERY_GENERIC, today=_TODAY,
        )
        sun_section = next(
            s for s in result["explainability_trail"]["sections"]
            if s["title"] == "Sun Sign"
        )
        content_lower = sun_section["content"].lower()
        self.assertIn("cusp", content_lower)

    def test_confidence_flag_set_for_cusp_with_none_tier(self) -> None:
        result = _engine().compute(
            dob=_DOB_PISCES_CUSP, birth_time=_BIRTH_TIME_NONE,
            birth_location=_LOCATION_LONDON, gender=None,
            moon=_MOON_S03, query=_QUERY_GENERIC, today=_TODAY,
        )
        self.assertTrue(result["confidence_flag"])


# ── Planetary positions: tropical vs sidereal distinction ────────────────────

class TestTropicalVsSidereal(SimpleTestCase):
    """Western uses tropical, Vedic uses sidereal — same DOB produces different results."""

    def setUp(self) -> None:
        if not _SWE_AVAILABLE:
            self.skipTest("pyswisseph not installed")

    def test_western_sun_sign_is_tropical(self) -> None:
        """Western engine does NOT apply ayanamsha — result is tropical."""
        result = _result_exact(dob=_DOB_1990)
        western_sun = result["findings"]["sun_sign"]
        # Verify by computing tropical directly
        swe.set_ephe_path(_EPH_PATH)
        jd = swe.julday(1990, 3, 15, 12.0)
        result_raw, _ = swe.calc_ut(jd, swe.SUN)  # tropical, no FLG_SIDEREAL
        expected_sign = longitude_to_sign(result_raw[0] % 360.0)
        self.assertEqual(western_sun, expected_sign)

    def test_north_south_node_are_opposite_signs(self) -> None:
        """South Node is always 6 signs (180°) from North Node."""
        f = _result_exact()["findings"]
        nn = f["north_node_sign"]
        sn = f["south_node_sign"]
        if nn and sn and nn in SIGNS and sn in SIGNS:
            nn_idx = SIGNS.index(nn)
            sn_idx = SIGNS.index(sn)
            diff = (sn_idx - nn_idx) % 12
            self.assertEqual(diff, 6,
                msg=f"North Node={nn}, South Node={sn}, diff={diff} (expected 6)")
