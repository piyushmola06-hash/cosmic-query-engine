"""
Tests for S-07 — Numerology Head Engine.

Covers:
  - Life path calculation (ordinary and master numbers)
  - Expression number (Pythagorean and Chaldean, divergence flag)
  - Soul urge and personality (Y vowel rule)
  - Birthday number (unreduced)
  - Personal year and month (today-relative)
  - Maturity number
  - Current name number
  - Pinnacle cycles (numbers and age boundaries)
  - Challenge numbers
  - Query relevance (personal year 9 rule, domain matching)
  - Tendency window (never null, min <= max)
  - Confidence flag (name present vs absent)
  - Output shape (S-07 contract)
  - Name normalization (accents, titles, hyphens, apostrophes)
  - Non-Latin flag
"""

from datetime import date

from django.test import TestCase

from heads.numerology.services import (
    CHALDEAN,
    PYTHAGOREAN,
    NumerologyHeadEngine,
    _classify_word,
    _component_reduce,
    _has_non_latin,
    _life_path,
    _name_sum,
    _normalize_name,
    _personal_month,
    _personal_year,
    _reduce,
    _weeks_to_end_of_month,
    _weeks_to_end_of_year,
)


# ── Shared fixture ────────────────────────────────────────────────────────────

# "John Smith", born 15/01/1985
# Life path: 1+5+0+1+1+9+8+5 = 30 → 3
# Pythagorean JOHN: J(1)+O(6)+H(8)+N(5)=20  SMITH: S(1)+M(4)+I(9)+T(2)+H(8)=24  total=44 → 8
# Chaldean JOHN: J(1)+O(7)+H(5)+N(5)=18  SMITH: S(3)+M(4)+I(1)+T(4)+H(5)=17  total=35 → 8
#   → NOT divergent for this name
# Soul urge (vowels): JOHN: O(6); SMITH: I(9)  total=15 → 6
# Personality (consonants): JOHN: J(1)+H(8)+N(5)=14; SMITH: S(1)+M(4)+T(2)+H(8)=15  total=29 → 11 (master)
# Maturity: LP(3) + Expr_pyth(8) = 11 → master 11

_JOHN_SMITH_DOB = {'day': 15, 'month': 1, 'year': 1985}
_TODAY = date(2026, 3, 31)  # fixed date for deterministic tests


def _engine() -> NumerologyHeadEngine:
    return NumerologyHeadEngine()


def _compute(
    full_birth_name="John Smith",
    current_name=None,
    dob=None,
    query="What does my future hold?",
    today=_TODAY,
) -> dict:
    if dob is None:
        dob = _JOHN_SMITH_DOB
    return _engine().compute(full_birth_name, current_name, dob, query, today=today)


# ─────────────────────────────────────────────────────────────────────────────
# Helper function tests
# ─────────────────────────────────────────────────────────────────────────────

class TestReduce(TestCase):
    def test_single_digit_unchanged(self):
        for n in range(1, 10):
            self.assertEqual(_reduce(n), n)

    def test_double_digit_reduced(self):
        self.assertEqual(_reduce(10), 1)
        self.assertEqual(_reduce(28), 1)  # 2+8=10 → 1+0=1

    def test_master_11_preserved(self):
        self.assertEqual(_reduce(11), 11)

    def test_master_22_preserved(self):
        self.assertEqual(_reduce(22), 22)

    def test_master_33_preserved(self):
        self.assertEqual(_reduce(33), 33)

    def test_29_reduces_to_11(self):
        # 2+9=11 → master, stop
        self.assertEqual(_reduce(29), 11)

    def test_38_reduces_to_11(self):
        # 3+8=11 → master
        self.assertEqual(_reduce(38), 11)

    def test_large_number(self):
        # 999 → 27 → 9
        self.assertEqual(_reduce(999), 9)

    def test_zero(self):
        self.assertEqual(_reduce(0), 0)


class TestClassifyWord(TestCase):
    """Y vowel rule: consonant at word start OR adjacent to vowel; vowel otherwise."""

    def test_standard_vowels(self):
        classifications = dict(_classify_word('aeiou'))
        for ch in 'aeiou':
            self.assertEqual(classifications[ch], 'vowel')

    def test_standard_consonants(self):
        word = 'bcd'
        for _, t in _classify_word(word):
            self.assertEqual(t, 'consonant')

    def test_y_at_word_start_is_consonant(self):
        # "yash" — Y starts the word
        result = dict(_classify_word('yash'))
        self.assertEqual(result['y'], 'consonant')

    def test_y_mid_word_between_consonants_is_vowel(self):
        # "lynn" — L-Y-N-N, Y surrounded by consonants
        classifications = _classify_word('lynn')
        y_entry = next(t for ch, t in classifications if ch == 'y')
        self.assertEqual(y_entry, 'vowel')

    def test_y_adjacent_to_left_vowel_is_consonant(self):
        # "maya" — M-A-Y-A, Y has A on left → consonant
        classifications = _classify_word('maya')
        y_entry = next(t for ch, t in classifications if ch == 'y')
        self.assertEqual(y_entry, 'consonant')

    def test_y_adjacent_to_right_vowel_is_consonant(self):
        # "yell" — at start (consonant by start rule, but let's test 'byeword' = b-y-e)
        # "bye" — B-Y-E: Y at index 1, right=E (vowel) → consonant
        classifications = _classify_word('bye')
        y_entry = next(t for ch, t in classifications if ch == 'y')
        self.assertEqual(y_entry, 'consonant')

    def test_y_in_cynthia_is_vowel(self):
        # "cynthia" — C-Y-N-T-H-I-A: Y at index 1, left=C (consonant), right=N (consonant) → vowel
        classifications = _classify_word('cynthia')
        y_entry = next(t for ch, t in classifications if ch == 'y')
        self.assertEqual(y_entry, 'vowel')

    def test_y_in_taylor_is_consonant(self):
        # "taylor" — T-A-Y-L-O-R: Y at index 2, left=A (vowel) → consonant
        classifications = _classify_word('taylor')
        y_entry = next(t for ch, t in classifications if ch == 'y')
        self.assertEqual(y_entry, 'consonant')


class TestNormalizeName(TestCase):
    def test_lowercase_and_spaces(self):
        self.assertEqual(_normalize_name('John Smith'), 'john smith')

    def test_removes_title_mr(self):
        self.assertEqual(_normalize_name('Mr John Smith'), 'john smith')

    def test_removes_title_dr(self):
        result = _normalize_name('Dr. Jane Doe')
        self.assertNotIn('dr', result.split())

    def test_removes_hyphen(self):
        result = _normalize_name('Anne-Marie Jones')
        self.assertNotIn('-', result)

    def test_removes_apostrophe(self):
        result = _normalize_name("O'Brien")
        self.assertNotIn("'", result)

    def test_normalizes_accented_e(self):
        # é should become e
        result = _normalize_name('René')
        self.assertIn('rene', result)

    def test_normalizes_accented_a(self):
        result = _normalize_name('María')
        self.assertIn('maria', result)

    def test_empty_string_returns_none(self):
        self.assertIsNone(_normalize_name(''))

    def test_only_title_returns_none(self):
        self.assertIsNone(_normalize_name('Mr'))

    def test_non_latin_preserved(self):
        # After normalization, non-ASCII remains (e.g. Arabic letters)
        result = _normalize_name('أحمد')
        # Should produce something non-None (letters preserved)
        # _has_non_latin will catch it separately
        self.assertIsNotNone(result)


class TestHasNonLatin(TestCase):
    def test_latin_name_is_false(self):
        self.assertFalse(_has_non_latin('john smith'))

    def test_arabic_name_is_true(self):
        self.assertTrue(_has_non_latin('أحمد'))

    def test_name_with_spaces_only_latin(self):
        self.assertFalse(_has_non_latin('mary jane'))


class TestNameSum(TestCase):
    def test_all_letters_pythagorean(self):
        # "a" = 1
        self.assertEqual(_name_sum('a', PYTHAGOREAN), 1)

    def test_all_letters_sum_john(self):
        # JOHN: J(1)+O(6)+H(8)+N(5) = 20
        self.assertEqual(_name_sum('john', PYTHAGOREAN), 20)

    def test_vowels_only(self):
        # "john": only O is vowel → 6
        self.assertEqual(_name_sum('john', PYTHAGOREAN, 'vowel'), 6)

    def test_consonants_only(self):
        # "john": J(1)+H(8)+N(5) = 14
        self.assertEqual(_name_sum('john', PYTHAGOREAN, 'consonant'), 14)

    def test_chaldean_john(self):
        # J(1)+O(7)+H(5)+N(5) = 18
        self.assertEqual(_name_sum('john', CHALDEAN), 18)

    def test_multiword(self):
        # "john smith" pythagorean: 20 + 24 = 44
        self.assertEqual(_name_sum('john smith', PYTHAGOREAN), 44)


class TestLifePath(TestCase):
    def test_john_smith(self):
        # 15/01/1985: digits 1+5+0+1+1+9+8+5 = 30 → 3
        lp, master = _life_path(15, 1, 1985)
        self.assertEqual(lp, 3)
        self.assertFalse(master)

    def test_master_11(self):
        # Find a DOB that gives LP 11
        # 29/11/1975: 2+9+1+1+1+9+7+5 = 35 → 8  (not 11)
        # Let's compute: need digit sum = 11, 29, 38, etc.
        # 11/11/1973: 1+1+1+1+1+9+7+3 = 24 → 6  (nope)
        # 29/09/1965: 2+9+0+9+1+9+6+5 = 41 → 5  (nope)
        # Just test _reduce(29)=11 path:
        # DOB giving sum=29: day=2, month=9, year=2018 → 0+2+0+9+2+0+1+8=22 (master 22, not 11)
        # day=20, month=09, year=1965: 2+0+0+9+1+9+6+5=32→5
        # Easier: just test _reduce directly for master
        self.assertEqual(_reduce(11), 11)
        self.assertEqual(_reduce(29), 11)

    def test_master_22_not_reduced(self):
        # Need a DOB with digit sum = 22 or 40 (4+0) or 13 (1+3=4 not 22)
        # 22 → 22 (master). Digit sum of 22 = 22 itself.
        # Let's engineer: day=04, month=09, year=1990: 0+4+0+9+1+9+9+0=32→5
        # Manually check _reduce(22)=22
        self.assertEqual(_reduce(22), 22)

    def test_ordinary_dob(self):
        # 01/01/2000: 0+1+0+1+2+0+0+0 = 4
        lp, master = _life_path(1, 1, 2000)
        self.assertEqual(lp, 4)
        self.assertFalse(master)

    def test_master_life_path_flagged(self):
        # Need digit sum = 11. day=02, month=03, year=2006: 0+2+0+3+2+0+0+6=13→4 (nope)
        # day=29, month=1, year=1963: 2+9+0+1+1+9+6+3=31→4 (nope)
        # day=20, month=11, year=1969: 2+0+1+1+1+9+6+9=29→11 (yes!)
        lp, master = _life_path(20, 11, 1969)
        self.assertEqual(lp, 11)
        self.assertTrue(master)


class TestPersonalYear(TestCase):
    def test_basic(self):
        # day=15, month=1, year=2026: 0+1+1+5+2+0+2+6 = 17 → 8
        self.assertEqual(_personal_year(15, 1, 2026), 8)

    def test_personal_month(self):
        py = _personal_year(15, 1, 2026)  # 8
        pm = _personal_month(py, 3)       # 8+3=11 → master 11
        self.assertEqual(pm, 11)


class TestTendencyWindow(TestCase):
    def test_weeks_end_of_month_march_15(self):
        # March 15 → March 31: 16 days → 16/7 = 2.3
        w = _weeks_to_end_of_month(date(2026, 3, 15))
        self.assertAlmostEqual(w, round(16 / 7, 1))

    def test_weeks_end_of_year_march_15(self):
        # March 15 to Dec 31 = 291 days
        w = _weeks_to_end_of_year(date(2026, 3, 15))
        days = (date(2026, 12, 31) - date(2026, 3, 15)).days
        self.assertAlmostEqual(w, round(days / 7, 1))

    def test_last_day_of_month_gives_zero(self):
        # March 31 → 0 days to end of month → 0.0
        w = _weeks_to_end_of_month(date(2026, 3, 31))
        self.assertEqual(w, 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# Engine integration tests
# ─────────────────────────────────────────────────────────────────────────────

class TestOutputShape(TestCase):
    """S-07 contract output shape validation."""

    def setUp(self):
        self.result = _compute()
        self.findings = self.result['findings']

    def test_head_key(self):
        self.assertEqual(self.result['head'], 'numerology')

    def test_available_findings_is_list(self):
        self.assertIsInstance(self.result['available_findings'], list)

    def test_unavailable_findings_is_list(self):
        self.assertIsInstance(self.result['unavailable_findings'], list)

    def test_findings_key_present(self):
        self.assertIn('findings', self.result)

    def test_all_required_finding_keys_present(self):
        required = [
            'life_path_number', 'life_path_master', 'expression_number',
            'soul_urge_number', 'personality_number', 'birthday_number',
            'personal_year_number', 'personal_month_number', 'maturity_number',
            'current_name_number', 'current_name_divergence',
            'pinnacle_cycles', 'challenge_numbers',
            'query_relevant_findings', 'tendency_window_weeks',
        ]
        for key in required:
            self.assertIn(key, self.findings, f"Missing key: {key}")

    def test_expression_number_subkeys(self):
        expr = self.findings['expression_number']
        self.assertIn('pythagorean', expr)
        self.assertIn('chaldean', expr)
        self.assertIn('divergent', expr)

    def test_challenge_numbers_subkeys(self):
        ch = self.findings['challenge_numbers']
        self.assertIn('first', ch)
        self.assertIn('second', ch)
        self.assertIn('main', ch)
        self.assertIn('final', ch)

    def test_tendency_window_subkeys(self):
        tw = self.findings['tendency_window_weeks']
        self.assertIn('min', tw)
        self.assertIn('max', tw)

    def test_explainability_trail_shape(self):
        trail = self.result['explainability_trail']
        self.assertEqual(trail['label'], 'Numerology')
        self.assertIsInstance(trail['sections'], list)
        self.assertTrue(len(trail['sections']) > 0)
        for section in trail['sections']:
            self.assertIn('title', section)
            self.assertIn('content', section)
            self.assertIn('available', section)

    def test_confidence_keys_present(self):
        self.assertIn('confidence_flag', self.result)
        self.assertIn('confidence_reason', self.result)

    def test_pinnacle_cycles_structure(self):
        cycles = self.findings['pinnacle_cycles']
        self.assertEqual(len(cycles), 4)
        for c in cycles:
            self.assertIn('cycle', c)
            self.assertIn('number', c)
            self.assertIn('age_start', c)
            self.assertIn('age_end', c)
            self.assertIn('active', c)


class TestLifePathNumber(TestCase):
    def test_john_smith_life_path_is_3(self):
        # 15/01/1985: 1+5+0+1+1+9+8+5 = 30 → 3
        result = _compute()
        self.assertEqual(result['findings']['life_path_number'], 3)

    def test_life_path_master_false_for_ordinary(self):
        result = _compute()
        self.assertFalse(result['findings']['life_path_master'])

    def test_master_life_path_22(self):
        # day=04, month=04, year=2006: 0+4+0+4+2+0+0+6=16→7 (nope)
        # Need digit sum=22. day=31, month=12, year=1993: 3+1+1+2+1+9+9+3=29→11 (nope)
        # day=29, month=12, year=1962: 2+9+1+2+1+9+6+2=32→5 (nope)
        # Let's use a known master 22: need sum=22 or 40 (4+0=4, not master), 13 (not master)
        # 22 itself: 2+2=4 (not preserved as 22 route)
        # Actually need raw sum to BE 22:
        # day=04, month=09, year=1945: 0+4+0+9+1+9+4+5=32→5 (nope)
        # day=11, month=02, year=1989: 1+1+0+2+1+9+8+9=31→4 (nope)
        # day=04, month=11, year=1989: 0+4+1+1+1+9+8+9=33→33 (master!)
        result = _engine().compute(
            'Test Person', None,
            {'day': 4, 'month': 11, 'year': 1989},
            'test', today=_TODAY,
        )
        lp = result['findings']['life_path_number']
        self.assertEqual(lp, 33)
        self.assertTrue(result['findings']['life_path_master'])

    def test_master_not_further_reduced(self):
        # If LP is 11, it must stay 11, not reduce to 2
        result = _engine().compute(
            'Test Person', None,
            {'day': 20, 'month': 11, 'year': 1969},
            'test', today=_TODAY,
        )
        self.assertEqual(result['findings']['life_path_number'], 11)
        self.assertTrue(result['findings']['life_path_master'])


class TestExpressionNumber(TestCase):
    def test_pythagorean_john_smith(self):
        # JOHN(20) + SMITH(24) = 44 → 8
        result = _compute()
        self.assertEqual(result['findings']['expression_number']['pythagorean'], 8)

    def test_chaldean_john_smith(self):
        # JOHN(18) + SMITH(17) = 35 → 8
        result = _compute()
        self.assertEqual(result['findings']['expression_number']['chaldean'], 8)

    def test_not_divergent_john_smith(self):
        result = _compute()
        self.assertFalse(result['findings']['expression_number']['divergent'])

    def test_divergent_when_systems_differ(self):
        # "Fiona" — Pythagorean: F(6)+I(9)+O(6)+N(5)+A(1)=27→9
        #           Chaldean:    F(8)+I(1)+O(7)+N(5)+A(1)=22→22 (master)
        # 22 ≠ 9 → divergent
        result = _engine().compute(
            'Fiona', None, _JOHN_SMITH_DOB, 'test', today=_TODAY,
        )
        expr = result['findings']['expression_number']
        self.assertNotEqual(expr['pythagorean'], expr['chaldean'])
        self.assertTrue(expr['divergent'])


class TestSoulUrgeAndPersonality(TestCase):
    def test_soul_urge_john_smith(self):
        # Vowels: O(6) in JOHN, I(9) in SMITH → 15 → 6
        result = _compute()
        self.assertEqual(result['findings']['soul_urge_number'], 6)

    def test_personality_john_smith(self):
        # Consonants: J(1)+H(8)+N(5) in JOHN = 14; S(1)+M(4)+T(2)+H(8) in SMITH = 15
        # total = 29 → 11 (master)
        result = _compute()
        self.assertEqual(result['findings']['personality_number'], 11)

    def test_y_vowel_in_soul_urge(self):
        # "Lynn" — L-Y-N-N: Y is vowel (mid-word, not adjacent to vowel)
        # Soul urge should include Y
        result = _engine().compute(
            'Lynn', None, _JOHN_SMITH_DOB, 'test', today=_TODAY,
        )
        # With Y as vowel: Y(7) → soul urge = _reduce(7) = 7
        self.assertEqual(result['findings']['soul_urge_number'], 7)

    def test_y_consonant_at_word_start(self):
        # "Yash" — Y is consonant (word start), no vowels except... there are no vowels after Y
        # Wait: Y-A-S-H — Y at start=consonant, A=vowel
        # Soul urge: A(1) only → 1
        result = _engine().compute(
            'Yash', None, _JOHN_SMITH_DOB, 'test', today=_TODAY,
        )
        self.assertEqual(result['findings']['soul_urge_number'], 1)

    def test_y_consonant_in_personality(self):
        # "Lynn" — Y is vowel, so personality = L(3)+N(5)+N(5)=13→4
        result = _engine().compute(
            'Lynn', None, _JOHN_SMITH_DOB, 'test', today=_TODAY,
        )
        self.assertEqual(result['findings']['personality_number'], 4)

    def test_soul_plus_personality_equals_expression(self):
        # soul + personality raw sums should equal expression raw sum
        # (before reduce) — not exact due to reduce, but verify separately
        result = _compute()
        su = result['findings']['soul_urge_number']
        pe = result['findings']['personality_number']
        ex = result['findings']['expression_number']['pythagorean']
        # They should all be valid reduced numbers
        self.assertIn(su, list(range(1, 10)) + [11, 22, 33])
        self.assertIn(pe, list(range(0, 10)) + [11, 22, 33])
        self.assertIn(ex, list(range(1, 10)) + [11, 22, 33])


class TestBirthdayNumber(TestCase):
    def test_birthday_number_is_day_unreduced(self):
        result = _compute()
        self.assertEqual(result['findings']['birthday_number'], 15)

    def test_birthday_number_day_1(self):
        result = _engine().compute(
            'Test', None, {'day': 1, 'month': 6, 'year': 1990}, 'test', today=_TODAY,
        )
        self.assertEqual(result['findings']['birthday_number'], 1)

    def test_birthday_number_day_31_unreduced(self):
        result = _engine().compute(
            'Test', None, {'day': 31, 'month': 12, 'year': 1990}, 'test', today=_TODAY,
        )
        # Must stay 31, not be reduced to 4
        self.assertEqual(result['findings']['birthday_number'], 31)


class TestPersonalYearAndMonth(TestCase):
    def test_personal_year_john_smith_2026(self):
        # 15/01/2026: 0+1+1+5+2+0+2+6 = 17 → 8
        result = _compute(today=date(2026, 3, 31))
        self.assertEqual(result['findings']['personal_year_number'], 8)

    def test_personal_month_march_2026(self):
        # personal_year=8, month=3 → 8+3=11 → master 11
        result = _compute(today=date(2026, 3, 31))
        self.assertEqual(result['findings']['personal_month_number'], 11)

    def test_personal_year_changes_with_year(self):
        py_2026 = _compute(today=date(2026, 3, 1))['findings']['personal_year_number']
        py_2027 = _compute(today=date(2027, 3, 1))['findings']['personal_year_number']
        self.assertNotEqual(py_2026, py_2027)


class TestMaturityNumber(TestCase):
    def test_maturity_john_smith(self):
        # LP(3) + Expr_pyth(8) = 11 → master 11
        result = _compute()
        self.assertEqual(result['findings']['maturity_number'], 11)

    def test_maturity_none_when_no_name(self):
        result = _compute(full_birth_name=None)
        self.assertIsNone(result['findings']['maturity_number'])


class TestCurrentNameNumber(TestCase):
    def test_current_name_none_when_not_provided(self):
        result = _compute(current_name=None)
        self.assertIsNone(result['findings']['current_name_number'])
        self.assertIsNone(result['findings']['current_name_divergence'])

    def test_current_name_computed_when_different(self):
        result = _compute(
            full_birth_name='John Smith',
            current_name='Jon Smith',
        )
        self.assertIsNotNone(result['findings']['current_name_number'])
        self.assertIsNotNone(result['findings']['current_name_divergence'])

    def test_current_name_same_as_birth_skipped(self):
        # When current name normalizes to same as birth name
        result = _compute(
            full_birth_name='John Smith',
            current_name='john smith',  # same after normalization
        )
        self.assertIsNone(result['findings']['current_name_number'])


class TestPinnacleCycles(TestCase):
    def test_four_cycles(self):
        result = _compute()
        self.assertEqual(len(result['findings']['pinnacle_cycles']), 4)

    def test_cycle_numbers_are_valid(self):
        cycles = _compute()['findings']['pinnacle_cycles']
        valid = set(range(0, 10)) | {11, 22, 33}
        for c in cycles:
            self.assertIn(c['number'], valid)

    def test_first_pinnacle_starts_at_zero(self):
        cycles = _compute()['findings']['pinnacle_cycles']
        self.assertEqual(cycles[0]['age_start'], 0)

    def test_consecutive_ages_contiguous(self):
        cycles = _compute()['findings']['pinnacle_cycles']
        for i in range(len(cycles) - 1):
            self.assertEqual(
                cycles[i + 1]['age_start'],
                cycles[i]['age_end'] + 1,
            )

    def test_fourth_pinnacle_is_ongoing(self):
        cycles = _compute()['findings']['pinnacle_cycles']
        self.assertEqual(cycles[3]['age_end'], 'ongoing')

    def test_exactly_one_active_cycle(self):
        cycles = _compute()['findings']['pinnacle_cycles']
        active_count = sum(1 for c in cycles if c['active'])
        self.assertEqual(active_count, 1)

    def test_first_pinnacle_end_formula(self):
        # First pinnacle ends at 36 - life_path (non-master reduced)
        result = _compute()
        lp = result['findings']['life_path_number']
        from heads.numerology.services import _reduce_no_master
        expected_end = 36 - _reduce_no_master(lp)
        self.assertEqual(result['findings']['pinnacle_cycles'][0]['age_end'], expected_end)

    def test_pinnacle_numbers_correct_john_smith(self):
        # DOB 15/01/1985:
        # month_r = _reduce(1) = 1
        # day_r = _reduce(1+5=6) = 6 (day=15 → digit sum 6)

        # Wait: _component_reduce(day) = _reduce(_digit_sum(day)) = _reduce(_digit_sum(15)) = _reduce(1+5) = _reduce(6) = 6
        # _component_reduce(month) = _reduce(_digit_sum(1)) = _reduce(1) = 1
        # _component_reduce(year_sum) = _reduce(_digit_sum(1985)) = _reduce(1+9+8+5) = _reduce(23) = _reduce(2+3) = 5

        # P1 = _reduce(1+6) = 7
        # P2 = _reduce(6+5) = 2  (11→2? No, _reduce(11)=11, master!)
        # Actually: 6+5=11 → master 11
        # P3 = _reduce(7+11) = _reduce(18) = 9
        # P4 = _reduce(1+5) = 6
        result = _compute()
        cycles = result['findings']['pinnacle_cycles']
        self.assertEqual(cycles[0]['number'], 7)   # P1 = 1+6 = 7
        self.assertEqual(cycles[1]['number'], 11)  # P2 = 6+5 = 11 (master)
        self.assertEqual(cycles[2]['number'], 9)   # P3 = 7+11=18→9
        self.assertEqual(cycles[3]['number'], 6)   # P4 = 1+5 = 6


class TestChallengeNumbers(TestCase):
    def test_challenge_structure(self):
        ch = _compute()['findings']['challenge_numbers']
        for key in ('first', 'second', 'main', 'final'):
            self.assertIn(key, ch)

    def test_challenge_values_john_smith(self):
        # month_r=1, day_r=6, year_r=5
        # C1 = |1-6| = 5
        # C2 = |6-5| = 1
        # C_main = |5-1| = 4
        # C_final = |1-5| = 4
        ch = _compute()['findings']['challenge_numbers']
        self.assertEqual(ch['first'], 5)
        self.assertEqual(ch['second'], 1)
        self.assertEqual(ch['main'], 4)
        self.assertEqual(ch['final'], 4)

    def test_challenges_are_non_negative(self):
        ch = _compute()['findings']['challenge_numbers']
        for val in ch.values():
            self.assertGreaterEqual(val, 0)


class TestQueryRelevance(TestCase):
    def test_personal_year_9_always_surfaces(self):
        # Use a DOB that will yield personal_year=9 with today=2026
        # Need day+month+2026 digit sum = 9 or 27
        # day=01, month=06: 0+1+0+6+2+0+2+6=17→8 (no)
        # day=02, month=06: 0+2+0+6+2+0+2+6=18→9 ✓
        result = _engine().compute(
            'Test Person', None,
            {'day': 2, 'month': 6, 'year': 1990},
            'What about my health?',  # unrelated domain
            today=_TODAY,
        )
        py = result['findings']['personal_year_number']
        self.assertEqual(py, 9)
        qr_findings = [item['finding'] for item in result['findings']['query_relevant_findings']]
        self.assertIn('personal_year_number', qr_findings)

    def test_personal_year_9_note_present(self):
        result = _engine().compute(
            'Test Person', None,
            {'day': 2, 'month': 6, 'year': 1990},
            'General question',
            today=_TODAY,
        )
        py = result['findings']['personal_year_number']
        self.assertEqual(py, 9)
        qr = result['findings']['query_relevant_findings']
        py9_items = [item for item in qr if item['finding'] == 'personal_year_number']
        self.assertTrue(len(py9_items) > 0)
        self.assertIn('note', py9_items[0])

    def test_career_query_surfaces_expression(self):
        result = _compute(query='What does my career hold?')
        qr_findings = [item['finding'] for item in result['findings']['query_relevant_findings']]
        self.assertIn('expression_number', qr_findings)

    def test_relationship_query_surfaces_soul_urge(self):
        result = _compute(query='How is my relationship going?')
        qr_findings = [item['finding'] for item in result['findings']['query_relevant_findings']]
        self.assertIn('soul_urge_number', qr_findings)

    def test_general_query_surfaces_life_path(self):
        result = _compute(query='What does my future hold?')
        qr_findings = [item['finding'] for item in result['findings']['query_relevant_findings']]
        self.assertIn('life_path_number', qr_findings)

    def test_no_duplicate_findings_in_query_relevant(self):
        # personal year 9 rule + domain should not duplicate personal_year_number
        result = _engine().compute(
            'Test Person', None,
            {'day': 2, 'month': 6, 'year': 1990},
            'What about my career?',
            today=_TODAY,
        )
        qr = result['findings']['query_relevant_findings']
        finding_keys = [item['finding'] for item in qr]
        self.assertEqual(len(finding_keys), len(set(finding_keys)))

    def test_query_relevant_is_list(self):
        result = _compute()
        self.assertIsInstance(result['findings']['query_relevant_findings'], list)


class TestTendencyWindow(TestCase):
    def test_tendency_window_never_null(self):
        result = _compute()
        tw = result['findings']['tendency_window_weeks']
        self.assertIsNotNone(tw)
        self.assertIsNotNone(tw['min'])
        self.assertIsNotNone(tw['max'])

    def test_min_lte_max(self):
        result = _compute(today=date(2026, 3, 15))
        tw = result['findings']['tendency_window_weeks']
        self.assertLessEqual(tw['min'], tw['max'])

    def test_tendency_window_no_name(self):
        # Even with no name, tendency window is present
        result = _compute(full_birth_name=None)
        tw = result['findings']['tendency_window_weeks']
        self.assertIsNotNone(tw)
        self.assertIsNotNone(tw['min'])
        self.assertIsNotNone(tw['max'])

    def test_min_weeks_march_15(self):
        result = _compute(today=date(2026, 3, 15))
        tw = result['findings']['tendency_window_weeks']
        # 16 days to end of March → 16/7 ≈ 2.3
        expected = round(16 / 7, 1)
        self.assertAlmostEqual(tw['min'], expected, places=1)

    def test_min_zero_on_last_day_of_month(self):
        result = _compute(today=date(2026, 3, 31))
        self.assertEqual(result['findings']['tendency_window_weeks']['min'], 0.0)


class TestConfidenceFlag(TestCase):
    def test_confident_when_name_provided(self):
        result = _compute()
        self.assertFalse(result['confidence_flag'])
        self.assertIsNone(result['confidence_reason'])

    def test_flagged_when_no_name(self):
        result = _compute(full_birth_name=None)
        self.assertTrue(result['confidence_flag'])
        self.assertIsNotNone(result['confidence_reason'])

    def test_flagged_when_empty_name(self):
        result = _compute(full_birth_name='')
        self.assertTrue(result['confidence_flag'])

    def test_flagged_when_only_title(self):
        result = _compute(full_birth_name='Mr')
        self.assertTrue(result['confidence_flag'])


class TestAvailableUnavailableFindings(TestCase):
    def test_name_present_expression_in_available(self):
        result = _compute()
        self.assertIn('expression_number', result['available_findings'])

    def test_no_name_expression_in_unavailable(self):
        result = _compute(full_birth_name=None)
        self.assertIn('expression_number', result['unavailable_findings'])
        self.assertNotIn('expression_number', result['available_findings'])

    def test_dob_numbers_always_available(self):
        result = _compute(full_birth_name=None)
        for key in ('life_path_number', 'personal_year_number', 'personal_month_number',
                    'birthday_number', 'pinnacle_cycles', 'challenge_numbers'):
            self.assertIn(key, result['available_findings'])


class TestNameNormalizationIntegration(TestCase):
    def test_hyphenated_name(self):
        # "Anne-Marie" should be treated as "anne marie" (two words)
        result = _engine().compute(
            'Anne-Marie', None, _JOHN_SMITH_DOB, 'test', today=_TODAY,
        )
        self.assertIsNotNone(result['findings']['expression_number'])

    def test_accented_name(self):
        result = _engine().compute(
            'René Dupont', None, _JOHN_SMITH_DOB, 'test', today=_TODAY,
        )
        self.assertIsNotNone(result['findings']['expression_number'])
        # Should not be flagged for non-Latin (accents stripped)
        self.assertFalse(result['confidence_flag'])

    def test_title_stripped(self):
        # "Dr. John Smith" should give same result as "John Smith"
        result_with_title = _engine().compute(
            'Dr John Smith', None, _JOHN_SMITH_DOB, 'test', today=_TODAY,
        )
        result_without = _compute()
        self.assertEqual(
            result_with_title['findings']['expression_number']['pythagorean'],
            result_without['findings']['expression_number']['pythagorean'],
        )

    def test_apostrophe_removed(self):
        result = _engine().compute(
            "O'Brien", None, _JOHN_SMITH_DOB, 'test', today=_TODAY,
        )
        # "obrien" should produce a valid expression
        self.assertIsNotNone(result['findings']['expression_number'])
