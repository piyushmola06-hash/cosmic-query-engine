"""
Tests for S-08 — Chinese Astrology Head Engine.

Covers:
  - Chinese calendar conversion (pre/post CNY boundary)
  - Zodiac animal/element/yin-yang from lunar year
  - All 6 clash year pairs
  - Ben ming nian detection
  - Clash year always in query_relevant_findings when true
  - Ben ming nian always in query_relevant_findings when true
  - All three birth time tiers produce valid output
  - Hour pillar double-hour mapping
  - Approximate tier ambiguity resolution
  - Tendency window never null, min <= max
  - Output shape matches S-08 contract
  - Explainability trail always contains clash year section
"""

from datetime import date

from django.test import TestCase

from heads.chinese.services import (
    BRANCH_ANIMALS,
    CLASH_PAIRS,
    ChineseAstrologyHeadEngine,
    _animal_from_lunar_year,
    _day_pillar,
    _element_from_lunar_year,
    _hour_to_branch_idx,
    _month_pillar,
    _relationship_to_natal,
    _to_lunar,
    _yin_yang_from_lunar_year,
    _year_pillar,
)

# ── Shared helpers ────────────────────────────────────────────────────────────

_TODAY = date(2026, 4, 1)   # Snake year 2025 in Chinese calendar

# Today's lunar year: April 1 2026 is still in the 2026 Chinese New Year cycle
# CNY 2026 fell on Feb 17 2026 → so April 1 2026 = Horse year (lunar 2026)?
# Actually let me verify: CNY 2025 = Jan 29 2025 (Snake), CNY 2026 = Feb 17 2026 (Horse)
# April 1 2026 > Feb 17 2026 → Horse year 2026

_SNAKE_DOB = {'day': 15, 'month': 1, 'year': 1990}   # before CNY 1990 (Jan 27) → Snake 1989
_HORSE_DOB = {'day': 10, 'month': 2, 'year': 1990}   # after CNY 1990 → Horse 1990

_DEFAULT_BIRTH_TIME_EXACT = {
    'tier': 'exact',
    'normalised_time': '10:30',
    'window_start': None,
    'window_end': None,
}
_DEFAULT_BIRTH_TIME_NONE = {
    'tier': 'none',
    'normalised_time': None,
    'window_start': None,
    'window_end': None,
}
_DEFAULT_LOCATION = {'city': 'Mumbai', 'country': 'India'}


def _engine() -> ChineseAstrologyHeadEngine:
    return ChineseAstrologyHeadEngine()


def _compute(
    dob=None,
    birth_time=None,
    birth_location=None,
    query="What does my future hold?",
    today=_TODAY,
) -> dict:
    if dob is None:
        dob = _SNAKE_DOB
    if birth_time is None:
        birth_time = _DEFAULT_BIRTH_TIME_EXACT
    if birth_location is None:
        birth_location = _DEFAULT_LOCATION
    return _engine().compute(dob, birth_time, birth_location, query, today=today)


# ─────────────────────────────────────────────────────────────────────────────
# Chinese calendar conversion tests
# ─────────────────────────────────────────────────────────────────────────────

class TestChineseCalendarConversion(TestCase):
    """Mandatory: Gregorian year never used directly for zodiac."""

    def test_jan_15_1990_is_snake_year_1989(self):
        """Jan 15 1990 is before CNY 1990 (Jan 27) → lunar year 1989 (Snake)."""
        lunar = _to_lunar(1990, 1, 15)
        self.assertIsNotNone(lunar)
        self.assertEqual(lunar.year, 1989)
        self.assertEqual(_animal_from_lunar_year(1989), 'Snake')

    def test_feb_10_1990_is_horse_year_1990(self):
        """Feb 10 1990 is after CNY 1990 (Jan 27) → lunar year 1990 (Horse)."""
        lunar = _to_lunar(1990, 2, 10)
        self.assertIsNotNone(lunar)
        self.assertEqual(lunar.year, 1990)
        self.assertEqual(_animal_from_lunar_year(1990), 'Horse')

    def test_snake_dob_produces_snake_zodiac(self):
        result = _compute(dob=_SNAKE_DOB)
        self.assertEqual(result['findings']['zodiac_animal'], 'Snake')

    def test_horse_dob_produces_horse_zodiac(self):
        result = _compute(dob=_HORSE_DOB)
        self.assertEqual(result['findings']['zodiac_animal'], 'Horse')

    def test_zodiac_year_certain_true_with_library(self):
        result = _compute(dob=_SNAKE_DOB)
        self.assertTrue(result['findings']['zodiac_year_certain'])

    def test_cny_boundary_jan_27_1990_is_horse(self):
        """Jan 27 1990 is Chinese New Year itself — should be Horse year 1990."""
        lunar = _to_lunar(1990, 1, 27)
        self.assertIsNotNone(lunar)
        self.assertEqual(lunar.year, 1990)
        self.assertEqual(_animal_from_lunar_year(1990), 'Horse')

    def test_cny_eve_jan_26_1990_is_snake(self):
        """Jan 26 1990, day before CNY → still Snake year 1989."""
        lunar = _to_lunar(1990, 1, 26)
        self.assertIsNotNone(lunar)
        self.assertEqual(lunar.year, 1989)


# ─────────────────────────────────────────────────────────────────────────────
# Zodiac properties
# ─────────────────────────────────────────────────────────────────────────────

class TestZodiacProperties(TestCase):
    def test_all_12_animals_cycle(self):
        """12-year animal cycle starting from Rat at year index 0."""
        # Year 2020 = Rat, 2021 = Ox, ..., 2031 = Pig
        expected = [
            (2020, 'Rat'), (2021, 'Ox'), (2022, 'Tiger'), (2023, 'Rabbit'),
            (2024, 'Dragon'), (2025, 'Snake'), (2026, 'Horse'), (2027, 'Goat'),
            (2028, 'Monkey'), (2029, 'Rooster'), (2030, 'Dog'), (2031, 'Pig'),
        ]
        for year, animal in expected:
            self.assertEqual(_animal_from_lunar_year(year), animal, f"Year {year}")

    def test_yin_yang_snake_1989(self):
        # 1989 stem index: (1989-4)%10 = 1985%10 = 5 → Jǐ → yin
        self.assertEqual(_yin_yang_from_lunar_year(1989), 'yin')

    def test_yin_yang_horse_1990(self):
        # 1990 stem index: (1990-4)%10 = 1986%10 = 6 → Gēng → yang
        self.assertEqual(_yin_yang_from_lunar_year(1990), 'yang')

    def test_yin_yang_in_output(self):
        result = _compute(dob=_SNAKE_DOB)
        self.assertIn(result['findings']['yin_yang'], ('yin', 'yang'))

    def test_element_snake_1989(self):
        # 1989 stem: (1989-4)%10=5 → Jǐ → Earth
        self.assertEqual(_element_from_lunar_year(1989), 'Earth')

    def test_element_horse_1990(self):
        # 1990 stem: (1990-4)%10=6 → Gēng → Metal
        self.assertEqual(_element_from_lunar_year(1990), 'Metal')


# ─────────────────────────────────────────────────────────────────────────────
# Clash year detection
# ─────────────────────────────────────────────────────────────────────────────

class TestClashYearDetection(TestCase):
    """All 6 clash pairs must be detected. Clash always surfaces in query_relevant_findings."""

    def _make_natal_animal_dob(self, animal: str) -> dict:
        """Find a DOB that gives the specified natal animal."""
        # Animal index in 12-year cycle
        idx = BRANCH_ANIMALS.index(animal)
        # Year that gives this animal: base year 2020=Rat(0), so animal_year = 2020 + idx
        base_year = 2020 + idx
        return {'day': 15, 'month': 6, 'year': base_year}

    def _make_today_for_animal(self, animal: str) -> date:
        """Return a date where the Chinese year matches the given animal."""
        idx = BRANCH_ANIMALS.index(animal)
        # 2020=Rat, so target year = 2020 + idx (or +12 to stay in future)
        target_year = 2020 + idx
        if target_year < 2020:
            target_year += 12
        # Use mid-year to avoid CNY boundary issues
        return date(target_year, 6, 15)

    def test_rat_horse_clash(self):
        # Natal: Rat (2020), Current: Horse (2026)
        dob = self._make_natal_animal_dob('Rat')
        today = date(2026, 6, 15)  # Horse year 2026
        result = _engine().compute(dob, _DEFAULT_BIRTH_TIME_NONE, _DEFAULT_LOCATION, 'test', today=today)
        self.assertTrue(result['findings']['clash_year'])

    def test_ox_goat_clash(self):
        dob = self._make_natal_animal_dob('Ox')   # 2021
        today = date(2027, 6, 15)  # Goat year 2027
        result = _engine().compute(dob, _DEFAULT_BIRTH_TIME_NONE, _DEFAULT_LOCATION, 'test', today=today)
        self.assertTrue(result['findings']['clash_year'])

    def test_tiger_monkey_clash(self):
        dob = self._make_natal_animal_dob('Tiger')  # 2022
        today = date(2028, 6, 15)  # Monkey year 2028
        result = _engine().compute(dob, _DEFAULT_BIRTH_TIME_NONE, _DEFAULT_LOCATION, 'test', today=today)
        self.assertTrue(result['findings']['clash_year'])

    def test_rabbit_rooster_clash(self):
        dob = self._make_natal_animal_dob('Rabbit')  # 2023
        today = date(2029, 6, 15)  # Rooster year 2029
        result = _engine().compute(dob, _DEFAULT_BIRTH_TIME_NONE, _DEFAULT_LOCATION, 'test', today=today)
        self.assertTrue(result['findings']['clash_year'])

    def test_dragon_dog_clash(self):
        dob = self._make_natal_animal_dob('Dragon')  # 2024
        today = date(2030, 6, 15)  # Dog year 2030
        result = _engine().compute(dob, _DEFAULT_BIRTH_TIME_NONE, _DEFAULT_LOCATION, 'test', today=today)
        self.assertTrue(result['findings']['clash_year'])

    def test_snake_pig_clash(self):
        dob = self._make_natal_animal_dob('Snake')  # 2025
        today = date(2031, 6, 15)  # Pig year 2031
        result = _engine().compute(dob, _DEFAULT_BIRTH_TIME_NONE, _DEFAULT_LOCATION, 'test', today=today)
        self.assertTrue(result['findings']['clash_year'])

    def test_no_clash_same_animal_is_ben_ming_not_clash(self):
        # Same animal = ben ming nian, not clash
        dob = self._make_natal_animal_dob('Rat')   # Rat natal
        today = date(2032, 6, 15)  # Next Rat year
        result = _engine().compute(dob, _DEFAULT_BIRTH_TIME_NONE, _DEFAULT_LOCATION, 'test', today=today)
        self.assertFalse(result['findings']['clash_year'])
        self.assertIsNone(result['findings']['clash_reason'])

    def test_clash_always_in_query_relevant(self):
        # Rat natal, Horse current year
        dob = self._make_natal_animal_dob('Rat')
        today = date(2026, 6, 15)
        result = _engine().compute(dob, _DEFAULT_BIRTH_TIME_NONE, _DEFAULT_LOCATION, 'test', today=today)
        self.assertTrue(result['findings']['clash_year'])
        qr_findings = [item['finding'] for item in result['findings']['query_relevant_findings']]
        self.assertIn('clash_year', qr_findings)

    def test_clash_reason_populated(self):
        dob = self._make_natal_animal_dob('Rat')
        today = date(2026, 6, 15)
        result = _engine().compute(dob, _DEFAULT_BIRTH_TIME_NONE, _DEFAULT_LOCATION, 'test', today=today)
        self.assertIsNotNone(result['findings']['clash_reason'])
        self.assertIn('clash', result['findings']['clash_reason'].lower())

    def test_no_clash_reason_when_no_clash(self):
        result = _compute(dob=_SNAKE_DOB)  # Snake 1989, today is Horse 2026 — no clash
        # Snake/Pig is a clash pair, not Snake/Horse
        # Current year 2026 = Horse. Snake vs Horse: check
        snake_horse_clash = any('Snake' in p and 'Horse' in p for p in CLASH_PAIRS)
        if not snake_horse_clash:
            self.assertFalse(result['findings']['clash_year'])
            self.assertIsNone(result['findings']['clash_reason'])


# ─────────────────────────────────────────────────────────────────────────────
# Ben ming nian
# ─────────────────────────────────────────────────────────────────────────────

class TestBenMingNian(TestCase):
    def test_ben_ming_nian_when_animals_match(self):
        # Snake natal (1989), today in Snake year (2025)
        dob = _SNAKE_DOB  # Snake 1989
        today = date(2025, 6, 15)  # Snake year 2025
        result = _engine().compute(dob, _DEFAULT_BIRTH_TIME_NONE, _DEFAULT_LOCATION, 'test', today=today)
        # Verify current year is Snake
        self.assertEqual(result['findings']['zodiac_animal'], 'Snake')
        self.assertEqual(result['findings']['current_year_energy']['animal'], 'Snake')
        # Ben ming nian detection
        qr = result['findings']['query_relevant_findings']
        # current_year_energy should appear with ben ming nian note
        ben_ming_items = [
            item for item in qr
            if item['finding'] == 'current_year_energy' and 'ben ming' in item.get('note', '').lower()
        ]
        self.assertTrue(len(ben_ming_items) > 0)

    def test_no_ben_ming_nian_when_different(self):
        # Snake natal, Horse year — no ben ming nian
        result = _compute(dob=_SNAKE_DOB, today=_TODAY)  # today = Horse year
        findings = result['findings']
        self.assertNotEqual(findings['zodiac_animal'], findings['current_year_energy']['animal'])

    def test_relationship_to_natal_ben_ming(self):
        self.assertEqual(_relationship_to_natal('Snake', 'Snake'), 'ben ming nian (return year)')

    def test_relationship_to_natal_clash(self):
        self.assertEqual(_relationship_to_natal('Horse', 'Rat'), 'clash')

    def test_relationship_to_natal_neutral(self):
        result = _relationship_to_natal('Tiger', 'Snake')
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)


# ─────────────────────────────────────────────────────────────────────────────
# Birth time tiers
# ─────────────────────────────────────────────────────────────────────────────

class TestBirthTimeTiers(TestCase):
    def test_exact_tier_produces_hour_pillar(self):
        bt = {'tier': 'exact', 'normalised_time': '10:30', 'window_start': None, 'window_end': None}
        result = _engine().compute(_SNAKE_DOB, bt, _DEFAULT_LOCATION, 'test', today=_TODAY)
        hp = result['findings']['four_pillars']['hour_pillar']
        self.assertIsNotNone(hp['heavenly_stem'])
        self.assertIsNotNone(hp['earthly_branch'])
        self.assertIsNotNone(hp['animal'])

    def test_none_tier_has_null_hour_pillar(self):
        result = _compute(birth_time=_DEFAULT_BIRTH_TIME_NONE)
        hp = result['findings']['four_pillars']['hour_pillar']
        self.assertIsNone(hp['heavenly_stem'])
        self.assertIsNone(hp['animal'])

    def test_approximate_same_double_hour_resolves(self):
        # 10:00–10:45 — both in Snake hour (09:00–10:59)
        bt = {'tier': 'approximate', 'normalised_time': None,
              'window_start': '10:00', 'window_end': '10:45'}
        result = _engine().compute(_SNAKE_DOB, bt, _DEFAULT_LOCATION, 'test', today=_TODAY)
        hp = result['findings']['four_pillars']['hour_pillar']
        self.assertIsNotNone(hp['animal'])
        self.assertEqual(hp['animal'], 'Snake')

    def test_approximate_spanning_two_hours_may_omit(self):
        # 10:30–11:30 spans Snake (09–10) and Horse (11–12)
        bt = {'tier': 'approximate', 'normalised_time': None,
              'window_start': '10:30', 'window_end': '11:30'}
        result = _engine().compute(_SNAKE_DOB, bt, _DEFAULT_LOCATION, 'test', today=_TODAY)
        # Either resolved (same strength) or null — both valid
        hp = result['findings']['four_pillars']['hour_pillar']
        # Just verify it's a valid structure
        self.assertIn('animal', hp)

    def test_all_tiers_produce_valid_findings(self):
        tiers = [
            {'tier': 'exact', 'normalised_time': '14:00', 'window_start': None, 'window_end': None},
            {'tier': 'approximate', 'normalised_time': None, 'window_start': '13:00', 'window_end': '15:00'},
            {'tier': 'none', 'normalised_time': None, 'window_start': None, 'window_end': None},
        ]
        for bt in tiers:
            with self.subTest(tier=bt['tier']):
                result = _engine().compute(_SNAKE_DOB, bt, _DEFAULT_LOCATION, 'test', today=_TODAY)
                self.assertEqual(result['head'], 'chinese')
                self.assertIn('zodiac_animal', result['findings'])
                self.assertIsNotNone(result['findings']['zodiac_animal'])

    def test_exact_tier_day_master_strength_computed(self):
        bt = {'tier': 'exact', 'normalised_time': '10:30', 'window_start': None, 'window_end': None}
        result = _engine().compute(_SNAKE_DOB, bt, _DEFAULT_LOCATION, 'test', today=_TODAY)
        strength = result['findings']['four_pillars']['day_master_strength']
        self.assertIn(strength, ('strong', 'weak', 'neutral'))

    def test_none_tier_day_master_still_computed(self):
        result = _compute(birth_time=_DEFAULT_BIRTH_TIME_NONE)
        self.assertIsNotNone(result['findings']['four_pillars']['day_master'])


# ─────────────────────────────────────────────────────────────────────────────
# Double-hour system
# ─────────────────────────────────────────────────────────────────────────────

class TestDoubleHourSystem(TestCase):
    def test_rat_hour_23(self):
        self.assertEqual(_hour_to_branch_idx(23), 0)  # Rat

    def test_rat_hour_0(self):
        self.assertEqual(_hour_to_branch_idx(0), 0)   # Rat (00:xx)

    def test_ox_hour_1(self):
        self.assertEqual(_hour_to_branch_idx(1), 1)   # Ox

    def test_ox_hour_2(self):
        self.assertEqual(_hour_to_branch_idx(2), 1)   # Ox

    def test_tiger_hour_3(self):
        self.assertEqual(_hour_to_branch_idx(3), 2)   # Tiger

    def test_rabbit_hour_5(self):
        self.assertEqual(_hour_to_branch_idx(5), 3)   # Rabbit

    def test_dragon_hour_7(self):
        self.assertEqual(_hour_to_branch_idx(7), 4)   # Dragon

    def test_snake_hour_9(self):
        self.assertEqual(_hour_to_branch_idx(9), 5)   # Snake

    def test_snake_hour_10(self):
        self.assertEqual(_hour_to_branch_idx(10), 5)  # Snake

    def test_horse_hour_11(self):
        self.assertEqual(_hour_to_branch_idx(11), 6)  # Horse

    def test_goat_hour_13(self):
        self.assertEqual(_hour_to_branch_idx(13), 7)  # Goat

    def test_monkey_hour_15(self):
        self.assertEqual(_hour_to_branch_idx(15), 8)  # Monkey

    def test_rooster_hour_17(self):
        self.assertEqual(_hour_to_branch_idx(17), 9)  # Rooster

    def test_dog_hour_19(self):
        self.assertEqual(_hour_to_branch_idx(19), 10) # Dog

    def test_pig_hour_21(self):
        self.assertEqual(_hour_to_branch_idx(21), 11) # Pig

    def test_pig_hour_22(self):
        self.assertEqual(_hour_to_branch_idx(22), 11) # Pig

    def test_exact_tier_10_30_is_snake_hour(self):
        bt = {'tier': 'exact', 'normalised_time': '10:30', 'window_start': None, 'window_end': None}
        result = _engine().compute(_SNAKE_DOB, bt, _DEFAULT_LOCATION, 'test', today=_TODAY)
        self.assertEqual(result['findings']['four_pillars']['hour_pillar']['animal'], 'Snake')

    def test_exact_tier_23_00_is_rat_hour(self):
        bt = {'tier': 'exact', 'normalised_time': '23:00', 'window_start': None, 'window_end': None}
        result = _engine().compute(_SNAKE_DOB, bt, _DEFAULT_LOCATION, 'test', today=_TODAY)
        self.assertEqual(result['findings']['four_pillars']['hour_pillar']['animal'], 'Rat')


# ─────────────────────────────────────────────────────────────────────────────
# Tendency window
# ─────────────────────────────────────────────────────────────────────────────

class TestTendencyWindow(TestCase):
    def test_never_null(self):
        result = _compute()
        tw = result['findings']['tendency_window_weeks']
        self.assertIsNotNone(tw)
        self.assertIsNotNone(tw['min'])
        self.assertIsNotNone(tw['max'])

    def test_min_lte_max(self):
        result = _compute()
        tw = result['findings']['tendency_window_weeks']
        self.assertLessEqual(tw['min'], tw['max'])

    def test_both_non_negative(self):
        result = _compute()
        tw = result['findings']['tendency_window_weeks']
        self.assertGreaterEqual(tw['min'], 0)
        self.assertGreaterEqual(tw['max'], 0)

    def test_tendency_window_all_tiers(self):
        for bt in [
            {'tier': 'exact', 'normalised_time': '12:00', 'window_start': None, 'window_end': None},
            {'tier': 'none', 'normalised_time': None, 'window_start': None, 'window_end': None},
        ]:
            with self.subTest(tier=bt['tier']):
                result = _engine().compute(_SNAKE_DOB, bt, _DEFAULT_LOCATION, 'test', today=_TODAY)
                tw = result['findings']['tendency_window_weeks']
                self.assertIsNotNone(tw['min'])
                self.assertIsNotNone(tw['max'])


# ─────────────────────────────────────────────────────────────────────────────
# Output shape — S-08 contract
# ─────────────────────────────────────────────────────────────────────────────

class TestOutputShape(TestCase):
    def setUp(self):
        self.result = _compute()
        self.findings = self.result['findings']

    def test_head_key(self):
        self.assertEqual(self.result['head'], 'chinese')

    def test_available_findings_list(self):
        self.assertIsInstance(self.result['available_findings'], list)

    def test_unavailable_findings_list(self):
        self.assertIsInstance(self.result['unavailable_findings'], list)

    def test_required_finding_keys(self):
        required = [
            'zodiac_animal', 'zodiac_element', 'zodiac_year_certain', 'yin_yang',
            'four_pillars', 'current_luck_pillar', 'current_year_energy',
            'current_month_energy', 'clash_year', 'clash_reason',
            'query_relevant_findings', 'tendency_window_weeks',
        ]
        for key in required:
            self.assertIn(key, self.findings, f"Missing key: {key}")

    def test_four_pillars_subkeys(self):
        fp = self.findings['four_pillars']
        for key in ('available', 'year_pillar', 'month_pillar', 'day_pillar',
                    'hour_pillar', 'day_master', 'day_master_strength',
                    'dominant_element', 'lacking_element'):
            self.assertIn(key, fp, f"Missing four_pillars key: {key}")

    def test_pillar_subkeys(self):
        for pillar_key in ('year_pillar', 'month_pillar', 'day_pillar'):
            p = self.findings['four_pillars'][pillar_key]
            for key in ('heavenly_stem', 'earthly_branch', 'element', 'animal'):
                self.assertIn(key, p, f"Missing {pillar_key}.{key}")

    def test_current_luck_pillar_subkeys(self):
        clp = self.findings['current_luck_pillar']
        for key in ('heavenly_stem', 'earthly_branch', 'element', 'age_start', 'age_end', 'active'):
            self.assertIn(key, clp)

    def test_current_year_energy_subkeys(self):
        cye = self.findings['current_year_energy']
        for key in ('animal', 'element', 'relationship_to_natal'):
            self.assertIn(key, cye)

    def test_current_month_energy_subkeys(self):
        cme = self.findings['current_month_energy']
        for key in ('animal', 'element'):
            self.assertIn(key, cme)

    def test_tendency_window_subkeys(self):
        tw = self.findings['tendency_window_weeks']
        self.assertIn('min', tw)
        self.assertIn('max', tw)

    def test_explainability_trail_shape(self):
        trail = self.result['explainability_trail']
        self.assertEqual(trail['label'], 'Chinese astrology')
        self.assertIsInstance(trail['sections'], list)
        self.assertTrue(len(trail['sections']) > 0)
        for s in trail['sections']:
            self.assertIn('title', s)
            self.assertIn('content', s)
            self.assertIn('available', s)

    def test_explainability_trail_contains_clash_section(self):
        """Spec: trail always contains clash year section."""
        trail = self.result['explainability_trail']
        titles = [s['title'] for s in trail['sections']]
        self.assertIn('Clash Year', titles)

    def test_confidence_keys_present(self):
        self.assertIn('confidence_flag', self.result)
        self.assertIn('confidence_reason', self.result)

    def test_yin_yang_valid_value(self):
        self.assertIn(self.findings['yin_yang'], ('yin', 'yang'))

    def test_clash_year_is_boolean(self):
        self.assertIsInstance(self.findings['clash_year'], bool)

    def test_zodiac_year_certain_is_boolean(self):
        self.assertIsInstance(self.findings['zodiac_year_certain'], bool)


# ─────────────────────────────────────────────────────────────────────────────
# Pillar helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestPillarHelpers(TestCase):
    def test_year_pillar_returns_dict(self):
        p = _year_pillar(1989)
        for key in ('heavenly_stem', 'earthly_branch', 'element', 'animal'):
            self.assertIn(key, p)

    def test_year_pillar_1989_snake(self):
        p = _year_pillar(1989)
        self.assertEqual(p['animal'], 'Snake')
        self.assertEqual(p['element'], 'Earth')  # stem index 5 = Jǐ = Earth

    def test_year_pillar_1990_horse(self):
        p = _year_pillar(1990)
        self.assertEqual(p['animal'], 'Horse')

    def test_day_pillar_returns_dict(self):
        p = _day_pillar(date(1990, 1, 15))
        for key in ('heavenly_stem', 'earthly_branch', 'element', 'animal'):
            self.assertIn(key, p)

    def test_day_pillar_different_dates_differ(self):
        p1 = _day_pillar(date(1990, 1, 15))
        p2 = _day_pillar(date(1990, 1, 16))
        # Adjacent days must have different stems (60-cycle)
        self.assertNotEqual(p1['heavenly_stem'], p2['heavenly_stem'])

    def test_month_pillar_returns_dict(self):
        p = _month_pillar(1989, 12)
        for key in ('heavenly_stem', 'earthly_branch', 'element', 'animal'):
            self.assertIn(key, p)

    def test_query_relevant_is_list(self):
        result = _compute()
        self.assertIsInstance(result['findings']['query_relevant_findings'], list)
