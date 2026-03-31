"""
S-07 — Numerology Head Engine

Computes core numerology findings using Pythagorean as primary and Chaldean
as secondary for Expression number. No birth time or location dependency.
Always runs at full fidelity when birth name is present.

Done condition (from spec):
  All numbers computed correctly. Master numbers never reduced. Personal year
  and month always from today's date. tendency_window_weeks never null.
  Pythagorean and Chaldean both computed for expression. Personal year 9
  always surfaces.
"""

from __future__ import annotations

import calendar
import re
import unicodedata
from datetime import date
from typing import Optional

# ── Letter value mappings ─────────────────────────────────────────────────────

PYTHAGOREAN: dict[str, int] = {
    'a': 1, 'b': 2, 'c': 3, 'd': 4, 'e': 5, 'f': 6, 'g': 7, 'h': 8, 'i': 9,
    'j': 1, 'k': 2, 'l': 3, 'm': 4, 'n': 5, 'o': 6, 'p': 7, 'q': 8, 'r': 9,
    's': 1, 't': 2, 'u': 3, 'v': 4, 'w': 5, 'x': 6, 'y': 7, 'z': 8,
}

CHALDEAN: dict[str, int] = {
    'a': 1, 'b': 2, 'c': 3, 'd': 4, 'e': 5, 'f': 8, 'g': 3, 'h': 5, 'i': 1,
    'j': 1, 'k': 2, 'l': 3, 'm': 4, 'n': 5, 'o': 7, 'p': 8, 'q': 1, 'r': 2,
    's': 3, 't': 4, 'u': 6, 'v': 6, 'w': 6, 'x': 5, 'y': 1, 'z': 7,
}

MASTER_NUMBERS = frozenset({11, 22, 33})

VOWELS = frozenset('aeiou')

TITLES = frozenset({
    'mr', 'mrs', 'ms', 'miss', 'dr', 'prof', 'rev', 'sr', 'jr',
    'sir', 'lord', 'lady', 'master',
})

# Query domain keyword sets
_CAREER_KEYWORDS = frozenset({
    'career', 'job', 'work', 'business', 'money', 'finance',
    'professional', 'promotion', 'salary', 'income',
})
_RELATIONSHIP_KEYWORDS = frozenset({
    'relationship', 'love', 'marriage', 'partner', 'family',
    'friend', 'romantic', 'dating', 'spouse',
})
_HEALTH_KEYWORDS = frozenset({
    'health', 'illness', 'disease', 'wellness', 'body', 'mental', 'fitness',
})


# ── Core reduction ────────────────────────────────────────────────────────────


def _reduce(n: int) -> int:
    """Reduce to single digit, preserving master numbers 11, 22, 33."""
    while n > 9 and n not in MASTER_NUMBERS:
        n = sum(int(d) for d in str(n))
    return n


def _reduce_no_master(n: int) -> int:
    """Reduce to single digit unconditionally (used for pinnacle age calculation)."""
    while n > 9:
        n = sum(int(d) for d in str(n))
    return n


def _digit_sum(n: int) -> int:
    """Sum all digits of a positive integer."""
    return sum(int(d) for d in str(n))


# ── Name helpers ──────────────────────────────────────────────────────────────


def _normalize_name(name: str) -> Optional[str]:
    """
    Prepare a name for numerology calculation.

    Steps: NFD-normalise (decompose accents), strip diacritics, lowercase,
    replace hyphens with space, strip apostrophes and full stops, split,
    remove titles, drop non-alpha characters, discard empty tokens.

    Returns the joined result, or None when nothing remains.
    """
    # Decompose accented characters to base + combining mark
    name = unicodedata.normalize('NFD', name)
    # Strip combining marks (diacritics)
    name = ''.join(ch for ch in name if unicodedata.category(ch) != 'Mn')
    name = name.lower()
    name = name.replace('-', ' ').replace("'", '').replace('.', '')
    tokens = name.split()
    tokens = [t for t in tokens if t not in TITLES]
    tokens = [''.join(ch for ch in t if ch.isalpha()) for t in tokens]
    tokens = [t for t in tokens if t]
    return ' '.join(tokens) if tokens else None


def _has_non_latin(normalized: str) -> bool:
    """True if the normalized name contains characters outside a-z."""
    return any(ch != ' ' and not ('a' <= ch <= 'z') for ch in normalized)


def _classify_word(word: str) -> list[tuple[str, str]]:
    """
    Classify each letter in a single word as 'vowel' or 'consonant'.

    Y rule (per spec):
      - Y at position 0 of the word → consonant (starts the word)
      - Y adjacent to a standard vowel (a,e,i,o,u) → consonant
      - Y elsewhere (surrounded by consonants mid-word) → vowel
    """
    result: list[tuple[str, str]] = []
    for i, ch in enumerate(word):
        if ch == 'y':
            if i == 0:
                result.append((ch, 'consonant'))
            else:
                left = word[i - 1] if i > 0 else None
                right = word[i + 1] if i < len(word) - 1 else None
                if (left and left in VOWELS) or (right and right in VOWELS):
                    result.append((ch, 'consonant'))
                else:
                    result.append((ch, 'vowel'))
        elif ch in VOWELS:
            result.append((ch, 'vowel'))
        else:
            result.append((ch, 'consonant'))
    return result


def _name_sum(
    normalized_name: str,
    mapping: dict[str, int],
    filter_type: Optional[str] = None,
) -> int:
    """
    Sum letter values for a normalized (multi-word) name.

    filter_type: None → all letters, 'vowel' → vowels only, 'consonant' → consonants only.
    Y classification is applied per word.
    """
    total = 0
    for word in normalized_name.split():
        for ch, letter_type in _classify_word(word):
            if filter_type is None or letter_type == filter_type:
                total += mapping.get(ch, 0)
    return total


# ── DOB calculations ──────────────────────────────────────────────────────────


def _life_path(day: int, month: int, year: int) -> tuple[int, bool]:
    """
    Compute the life path number.

    Method: sum all digits of the full date string (DDMMYYYY), then reduce.
    Master numbers 11, 22, 33 are never reduced.

    Returns (life_path_number, is_master_number).
    """
    digits = [int(d) for d in f"{day:02d}{month:02d}{year}"]
    lp = _reduce(sum(digits))
    return lp, lp in MASTER_NUMBERS


def _component_reduce(component: int) -> int:
    """
    Reduce a single DOB component (day, month, or year digit-sum) using
    the standard reduce with master number preservation.
    Used for pinnacle and challenge calculations.
    """
    return _reduce(_digit_sum(component))


def _personal_year(day: int, month: int, current_year: int) -> int:
    """Personal year = sum of all digits in DD/MM/YYYY of birthday in current year."""
    digits = [int(d) for d in f"{day:02d}{month:02d}{current_year}"]
    return _reduce(sum(digits))


def _personal_month(personal_year: int, current_month: int) -> int:
    """Personal month = personal year + current month, reduced."""
    return _reduce(personal_year + current_month)


def _weeks_to_end_of_month(today: date) -> float:
    last_day = calendar.monthrange(today.year, today.month)[1]
    days = (date(today.year, today.month, last_day) - today).days
    return round(days / 7, 1)


def _weeks_to_end_of_year(today: date) -> float:
    days = (date(today.year, 12, 31) - today).days
    return round(days / 7, 1)


# ── Head engine ───────────────────────────────────────────────────────────────


class NumerologyHeadEngine:
    """
    S-07 Numerology Head Engine.

    Computes all numerology findings and returns the S-07 contract output shape.
    Pure computation — no I/O, no session state.
    """

    def compute(
        self,
        full_birth_name: Optional[str],
        current_name: Optional[str],
        dob: dict,
        query: str,
        today: Optional[date] = None,
    ) -> dict:
        """
        Compute numerology findings.

        Args:
            full_birth_name: Full name at birth.
            current_name: Currently used name, or None if same as birth name.
            dob: {"day": int, "month": int, "year": int}
            query: The user's question string.
            today: Injected date for testing (defaults to date.today()).

        Returns:
            S-07 contract output dict.
        """
        if today is None:
            today = date.today()

        day: int = dob['day']
        month: int = dob['month']
        year: int = dob['year']

        available_findings: list[str] = []
        unavailable_findings: list[str] = []
        confidence_issues: list[str] = []
        trail_sections: list[dict] = []

        # ── Life path ─────────────────────────────────────────────────────────
        lp_number, lp_master = _life_path(day, month, year)
        available_findings.append('life_path_number')
        trail_sections.append({
            'title': 'Life Path',
            'content': (
                f"Life path {lp_number}"
                f"{' (master number — not reduced)' if lp_master else ''}. "
                f"Derived from digit sum of {day:02d}/{month:02d}/{year}."
            ),
            'available': True,
        })

        # ── Personal year and month ───────────────────────────────────────────
        py_number = _personal_year(day, month, today.year)
        pm_number = _personal_month(py_number, today.month)
        available_findings.extend(['personal_year_number', 'personal_month_number'])
        trail_sections.append({
            'title': 'Personal Year / Month',
            'content': (
                f"Personal year {py_number}, personal month {pm_number} "
                f"(recomputed for {today.year}-{today.month:02d})."
            ),
            'available': True,
        })

        # ── Birthday number ───────────────────────────────────────────────────
        birthday_number = day  # unreduced, per spec
        available_findings.append('birthday_number')

        # ── Pinnacles and challenges (DOB components) ─────────────────────────
        month_r = _component_reduce(month)
        day_r = _component_reduce(day)
        year_r = _component_reduce(_digit_sum(year))

        # Pinnacle numbers
        p1_num = _reduce(month_r + day_r)
        p2_num = _reduce(day_r + year_r)
        p3_num = _reduce(p1_num + p2_num)
        p4_num = _reduce(month_r + year_r)

        # Age boundaries — use reduced (non-master) life path for arithmetic
        lp_age = _reduce_no_master(lp_number)
        p1_end = 36 - lp_age
        p2_end = p1_end + 9
        p3_end = p2_end + 9

        current_age = (
            today.year - year
            - (1 if (today.month, today.day) < (month, day) else 0)
        )

        pinnacle_cycles = [
            {
                'cycle': 1,
                'number': p1_num,
                'age_start': 0,
                'age_end': p1_end,
                'active': current_age <= p1_end,
            },
            {
                'cycle': 2,
                'number': p2_num,
                'age_start': p1_end + 1,
                'age_end': p2_end,
                'active': p1_end < current_age <= p2_end,
            },
            {
                'cycle': 3,
                'number': p3_num,
                'age_start': p2_end + 1,
                'age_end': p3_end,
                'active': p2_end < current_age <= p3_end,
            },
            {
                'cycle': 4,
                'number': p4_num,
                'age_start': p3_end + 1,
                'age_end': 'ongoing',
                'active': current_age > p3_end,
            },
        ]
        available_findings.append('pinnacle_cycles')

        active_cycle = next(p for p in pinnacle_cycles if p['active'])
        trail_sections.append({
            'title': 'Pinnacle Cycles',
            'content': (
                f"Four pinnacles: {p1_num} (ages 0–{p1_end}), "
                f"{p2_num} ({p1_end + 1}–{p2_end}), "
                f"{p3_num} ({p2_end + 1}–{p3_end}), "
                f"{p4_num} ({p3_end + 1}+). "
                f"Currently in cycle {active_cycle['cycle']} (pinnacle {active_cycle['number']})."
            ),
            'available': True,
        })

        # Challenge numbers
        c1 = abs(month_r - day_r)
        c2 = abs(day_r - year_r)
        c_main = abs(c1 - c2)
        c_final = abs(month_r - year_r)

        challenge_numbers = {
            'first': c1,
            'second': c2,
            'main': c_main,
            'final': c_final,
        }
        available_findings.append('challenge_numbers')
        trail_sections.append({
            'title': 'Challenge Numbers',
            'content': (
                f"First: {c1} (|month {month_r} − day {day_r}|), "
                f"second: {c2} (|day {day_r} − year {year_r}|), "
                f"main: {c_main} (|{c1} − {c2}|), "
                f"final: {c_final} (|month {month_r} − year {year_r}|)."
            ),
            'available': True,
        })

        # ── Name-based numbers ────────────────────────────────────────────────
        expression_pyth: Optional[int] = None
        expression_chal: Optional[int] = None
        expression_divergent: Optional[bool] = None
        soul_urge: Optional[int] = None
        personality: Optional[int] = None
        maturity: Optional[int] = None
        current_name_number: Optional[int] = None
        current_name_divergence: Optional[bool] = None

        normalized_birth: Optional[str] = None
        if full_birth_name:
            normalized_birth = _normalize_name(full_birth_name)

        if normalized_birth:
            if _has_non_latin(normalized_birth):
                confidence_issues.append(
                    "Name contains non-Latin characters — transliteration applied, "
                    "name-based numbers carry reduced certainty."
                )

            # Expression (both systems)
            pyth_sum = _name_sum(normalized_birth, PYTHAGOREAN)
            chal_sum = _name_sum(normalized_birth, CHALDEAN)
            expression_pyth = _reduce(pyth_sum)
            expression_chal = _reduce(chal_sum)
            expression_divergent = expression_pyth != expression_chal
            available_findings.append('expression_number')
            trail_sections.append({
                'title': 'Expression Number',
                'content': (
                    f"Pythagorean: {expression_pyth}, Chaldean: {expression_chal}. "
                    + (
                        "Systems diverge — both values are surfaced."
                        if expression_divergent
                        else "Both systems agree."
                    )
                ),
                'available': True,
            })

            # Soul urge (vowels only, Pythagorean)
            soul_urge = _reduce(_name_sum(normalized_birth, PYTHAGOREAN, filter_type='vowel'))
            available_findings.append('soul_urge_number')
            trail_sections.append({
                'title': 'Soul Urge',
                'content': (
                    f"Soul urge {soul_urge}. "
                    "Computed from vowels in birth name (Y treated as vowel when mid-word "
                    "and not adjacent to another vowel)."
                ),
                'available': True,
            })

            # Personality (consonants only, Pythagorean)
            personality = _reduce(_name_sum(normalized_birth, PYTHAGOREAN, filter_type='consonant'))
            available_findings.append('personality_number')
            trail_sections.append({
                'title': 'Personality',
                'content': (
                    f"Personality {personality}. "
                    "Computed from consonants in birth name (Y at word start or adjacent to "
                    "vowel counts as consonant)."
                ),
                'available': True,
            })

            # Maturity (life path + Pythagorean expression, reduced)
            maturity = _reduce(lp_number + expression_pyth)
            available_findings.append('maturity_number')
            trail_sections.append({
                'title': 'Maturity Number',
                'content': (
                    f"Maturity {maturity}. "
                    f"Life path {lp_number} + expression {expression_pyth}, reduced."
                ),
                'available': True,
            })

            # Current name number (only when current name differs from birth name)
            if current_name:
                normalized_current = _normalize_name(current_name)
                if normalized_current and normalized_current != normalized_birth:
                    curr_pyth = _reduce(_name_sum(normalized_current, PYTHAGOREAN))
                    current_name_number = curr_pyth
                    current_name_divergence = curr_pyth != expression_pyth
                    available_findings.append('current_name_number')
                    trail_sections.append({
                        'title': 'Current Name Number',
                        'content': (
                            f"Current name '{normalized_current}' "
                            f"gives Pythagorean {curr_pyth}. "
                            + (
                                "Diverges from birth name expression number."
                                if current_name_divergence
                                else "Matches birth name expression number."
                            )
                        ),
                        'available': True,
                    })
        else:
            for f_name in ['expression_number', 'soul_urge_number', 'personality_number', 'maturity_number']:
                unavailable_findings.append(f_name)
            confidence_issues.append(
                "Birth name unavailable — name-based numbers (expression, soul urge, "
                "personality, maturity) omitted."
            )
            trail_sections.append({
                'title': 'Name-Based Numbers',
                'content': (
                    "Birth name not provided. Expression, soul urge, personality, "
                    "and maturity numbers are unavailable."
                ),
                'available': False,
            })

        # ── Query relevance ───────────────────────────────────────────────────
        query_relevant: list[dict] = []
        query_lower = (query or '').lower()
        query_tokens = set(re.split(r'\W+', query_lower))

        # Personal year 9 always surfaces (spec requirement)
        if py_number == 9:
            query_relevant.append({
                'finding': 'personal_year_number',
                'value': 9,
                'note': (
                    'Personal year 9 — a year of endings, release, and completion. '
                    'Always surfaced regardless of query domain.'
                ),
            })

        # Domain findings
        if query_tokens & _CAREER_KEYWORDS:
            if expression_pyth is not None:
                query_relevant.append({
                    'finding': 'expression_number',
                    'value': {'pythagorean': expression_pyth, 'chaldean': expression_chal},
                })
            if py_number != 9:  # avoid duplicate if already added above
                query_relevant.append({'finding': 'personal_year_number', 'value': py_number})
            query_relevant.append({'finding': 'pinnacle_cycles', 'value': active_cycle})
        elif query_tokens & _RELATIONSHIP_KEYWORDS:
            if soul_urge is not None:
                query_relevant.append({'finding': 'soul_urge_number', 'value': soul_urge})
            if py_number != 9:
                query_relevant.append({'finding': 'personal_year_number', 'value': py_number})
            query_relevant.append({'finding': 'personal_month_number', 'value': pm_number})
        elif query_tokens & _HEALTH_KEYWORDS:
            if py_number != 9:
                query_relevant.append({'finding': 'personal_year_number', 'value': py_number})
            query_relevant.append({'finding': 'challenge_numbers', 'value': challenge_numbers})
        else:
            # General query — surface life path, personal year, active pinnacle
            query_relevant.append({'finding': 'life_path_number', 'value': lp_number})
            if py_number != 9:
                query_relevant.append({'finding': 'personal_year_number', 'value': py_number})
            query_relevant.append({'finding': 'pinnacle_cycles', 'value': active_cycle})

        # Deduplicate (preserve insertion order, personal year 9 note wins)
        seen_findings: set[str] = set()
        deduped: list[dict] = []
        for item in query_relevant:
            if item['finding'] not in seen_findings:
                seen_findings.add(item['finding'])
                deduped.append(item)
        query_relevant = deduped

        # ── Tendency window ───────────────────────────────────────────────────
        tendency_window = {
            'min': _weeks_to_end_of_month(today),
            'max': _weeks_to_end_of_year(today),
        }

        # ── Confidence ────────────────────────────────────────────────────────
        if confidence_issues:
            confidence_flag = True
            confidence_reason = ' '.join(confidence_issues)
        else:
            confidence_flag = False
            confidence_reason = None

        # ── Output ────────────────────────────────────────────────────────────
        expression_out = (
            {
                'pythagorean': expression_pyth,
                'chaldean': expression_chal,
                'divergent': expression_divergent,
            }
            if expression_pyth is not None
            else None
        )

        findings: dict = {
            'life_path_number': lp_number,
            'life_path_master': lp_master,
            'expression_number': expression_out,
            'soul_urge_number': soul_urge,
            'personality_number': personality,
            'birthday_number': birthday_number,
            'personal_year_number': py_number,
            'personal_month_number': pm_number,
            'maturity_number': maturity,
            'current_name_number': current_name_number,
            'current_name_divergence': current_name_divergence,
            'pinnacle_cycles': pinnacle_cycles,
            'challenge_numbers': challenge_numbers,
            'query_relevant_findings': query_relevant,
            'tendency_window_weeks': tendency_window,
        }

        return {
            'head': 'numerology',
            'available_findings': available_findings,
            'unavailable_findings': unavailable_findings,
            'findings': findings,
            'confidence_flag': confidence_flag,
            'confidence_reason': confidence_reason,
            'explainability_trail': {
                'label': 'Numerology',
                'sections': trail_sections,
            },
        }
