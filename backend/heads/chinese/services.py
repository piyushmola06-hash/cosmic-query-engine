"""
S-08 — Chinese Astrology Head Engine

Computes Chinese astrological findings at two levels:
  - Base reading (all tiers): zodiac animal/element, yin/yang, current year/month
    energy, clash year, ben ming nian, year/month/day pillars.
  - Four Pillars (tier-dependent): hour pillar from double-hour system.

MANDATORY: Chinese calendar conversion is applied before any computation.
Gregorian year is never used directly for zodiac determination.

Done condition (from spec):
  Chinese calendar conversion always applied. Clash year always detected and
  surfaced. Ben ming nian detected and flagged. Hour pillar ambiguity resolved
  by day master strength consistency check. tendency_window_weeks never null.
  Explainability trail always contains clash year section.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional

try:
    from lunardate import LunarDate
    _LUNARDATE_AVAILABLE = True
except ImportError:
    _LUNARDATE_AVAILABLE = False

# ── Heavenly Stems (天干) ─────────────────────────────────────────────────────

HEAVENLY_STEMS: list[str] = [
    'Jiǎ', 'Yǐ', 'Bǐng', 'Dīng', 'Wù', 'Jǐ', 'Gēng', 'Xīn', 'Rén', 'Guǐ',
]

STEM_ELEMENTS: list[str] = [
    'Wood', 'Wood', 'Fire', 'Fire', 'Earth', 'Earth',
    'Metal', 'Metal', 'Water', 'Water',
]

STEM_POLARITY: list[str] = [
    'yang', 'yin', 'yang', 'yin', 'yang', 'yin',
    'yang', 'yin', 'yang', 'yin',
]

# ── Earthly Branches (地支) ───────────────────────────────────────────────────

EARTHLY_BRANCHES: list[str] = [
    'Zǐ', 'Chǒu', 'Yín', 'Mǎo', 'Chén', 'Sì',
    'Wǔ', 'Wèi', 'Shēn', 'Yǒu', 'Xū', 'Hài',
]

BRANCH_ANIMALS: list[str] = [
    'Rat', 'Ox', 'Tiger', 'Rabbit', 'Dragon', 'Snake',
    'Horse', 'Goat', 'Monkey', 'Rooster', 'Dog', 'Pig',
]

BRANCH_ELEMENTS: list[str] = [
    'Water', 'Earth', 'Wood', 'Wood', 'Earth', 'Fire',
    'Fire', 'Earth', 'Metal', 'Metal', 'Earth', 'Water',
]

# ── Clash pairs (index pairs in BRANCH_ANIMALS) ───────────────────────────────
# Rat(0)/Horse(6), Ox(1)/Goat(7), Tiger(2)/Monkey(8),
# Rabbit(3)/Rooster(9), Dragon(4)/Dog(10), Snake(5)/Pig(11)
CLASH_PAIRS: list[frozenset] = [
    frozenset({'Rat', 'Horse'}),
    frozenset({'Ox', 'Goat'}),
    frozenset({'Tiger', 'Monkey'}),
    frozenset({'Rabbit', 'Rooster'}),
    frozenset({'Dragon', 'Dog'}),
    frozenset({'Snake', 'Pig'}),
]

# ── Double-hour system ────────────────────────────────────────────────────────
# Each entry: (start_hour_inclusive, end_hour_inclusive, branch_index)
# Rat hour spans 23:00–00:59 so it wraps; handled specially.
DOUBLE_HOURS: list[tuple[int, int, int]] = [
    (23, 23, 0),   # Rat starts at 23:xx (midnight wrap handled below)
    (0,  0,  0),   # Rat 00:xx
    (1,  2,  1),   # Ox
    (3,  4,  2),   # Tiger
    (5,  6,  3),   # Rabbit
    (7,  8,  4),   # Dragon
    (9,  10, 5),   # Snake
    (11, 12, 6),   # Horse
    (13, 14, 7),   # Goat
    (15, 16, 8),   # Monkey
    (17, 18, 9),   # Rooster
    (19, 20, 10),  # Dog
    (21, 22, 11),  # Pig
]

# ── Day master strength heuristic ─────────────────────────────────────────────
# Simplified: day stem element vs season (month branch element).
# Season supports day master element → strong; opposes → weak; else neutral.
_ELEMENT_CYCLE = ['Wood', 'Fire', 'Earth', 'Metal', 'Water']

# Which elements support which (sheng cycle: Wood→Fire→Earth→Metal→Water→Wood)
_SUPPORTS: dict[str, str] = {
    'Wood': 'Fire', 'Fire': 'Earth', 'Earth': 'Metal',
    'Metal': 'Water', 'Water': 'Wood',
}
# Which elements control which (ke cycle: Wood→Earth, Earth→Water, Water→Fire, Fire→Metal, Metal→Wood)
_CONTROLS: dict[str, str] = {
    'Wood': 'Earth', 'Earth': 'Water', 'Water': 'Fire',
    'Fire': 'Metal', 'Metal': 'Wood',
}

# Query domain keywords
_CAREER_KW = frozenset({'career', 'job', 'work', 'business', 'money', 'finance', 'professional'})
_RELATIONSHIP_KW = frozenset({'relationship', 'love', 'marriage', 'partner', 'family', 'romantic'})
_HEALTH_KW = frozenset({'health', 'illness', 'wellness', 'body', 'mental'})


# ── Pillar calculation helpers ────────────────────────────────────────────────

def _stem_branch_from_index(stem_idx: int, branch_idx: int) -> dict:
    """Build a pillar dict from stem and branch indices (0-based)."""
    stem_idx = stem_idx % 10
    branch_idx = branch_idx % 12
    return {
        'heavenly_stem': HEAVENLY_STEMS[stem_idx],
        'earthly_branch': EARTHLY_BRANCHES[branch_idx],
        'element': STEM_ELEMENTS[stem_idx],
        'animal': BRANCH_ANIMALS[branch_idx],
    }


def _year_pillar(lunar_year: int) -> dict:
    """
    Compute year pillar from Chinese lunar year.
    Stem cycle: (year - 4) % 10, Branch cycle: (year - 4) % 12.
    Year 4 CE is the reference (Jiǎ-Zǐ cycle start).
    """
    stem_idx = (lunar_year - 4) % 10
    branch_idx = (lunar_year - 4) % 12
    return _stem_branch_from_index(stem_idx, branch_idx)


def _month_pillar(lunar_year: int, lunar_month: int) -> dict:
    """
    Compute month pillar.
    Branch: lunar month 1 = Yín (index 2), cycles through 12.
    Stem: determined by year stem group × 2 + month offset.
    """
    branch_idx = (lunar_month + 1) % 12  # month 1 → Yín (2), month 11 → Zǐ (0)
    year_stem_idx = (lunar_year - 4) % 10
    # Month stem start index for year: year_stem_group * 2 (mod 10)
    year_stem_group = year_stem_idx % 5
    month_stem_start = (year_stem_group * 2) % 10
    stem_idx = (month_stem_start + lunar_month - 1) % 10
    return _stem_branch_from_index(stem_idx, branch_idx)


def _day_pillar(solar_date: date) -> dict:
    """
    Compute day pillar.
    Reference: Jan 1 1900 = Jiǎ-Zǐ (stem 0, branch 0).
    Days elapsed from reference → stem and branch indices.
    """
    ref = date(1900, 1, 1)
    days = (solar_date - ref).days
    stem_idx = days % 10
    branch_idx = days % 12
    return _stem_branch_from_index(stem_idx, branch_idx)


def _hour_pillar(day_stem_idx: int, hour: int) -> dict:
    """
    Compute hour pillar from day stem index and hour (0–23).
    Branch: mapped from double-hour.
    Stem: day stem group × 2 + branch_idx (mod 10).
    """
    branch_idx = _hour_to_branch_idx(hour)
    day_stem_group = day_stem_idx % 5
    hour_stem_start = (day_stem_group * 2) % 10
    stem_idx = (hour_stem_start + branch_idx) % 10
    return _stem_branch_from_index(stem_idx, branch_idx)


def _hour_to_branch_idx(hour: int) -> int:
    """Map a 24-hour clock hour to a double-hour branch index (0–11)."""
    if hour == 23:
        return 0   # Rat
    return (hour + 1) // 2


def _hhmm_to_hour(hhmm: str) -> int:
    """Parse 'HH:MM' → integer hour."""
    return int(hhmm.split(':')[0])


def _day_master_strength(day_element: str, month_branch_idx: int) -> str:
    """
    Simplified day master strength assessment.
    Season (month branch element) supporting the day master → strong.
    Season controlling the day master → weak. Otherwise → neutral.
    """
    season_element = BRANCH_ELEMENTS[month_branch_idx % 12]
    if _SUPPORTS.get(season_element) == day_element:
        return 'strong'
    if _CONTROLS.get(season_element) == day_element:
        return 'weak'
    if season_element == day_element:
        return 'strong'
    return 'neutral'


def _dominant_lacking(day_element: str, pillars: list[dict]) -> tuple[Optional[str], Optional[str]]:
    """
    Count element occurrences across the given pillars.
    Returns (dominant_element, lacking_element).
    """
    counts: dict[str, int] = {e: 0 for e in _ELEMENT_CYCLE}
    for p in pillars:
        el = p.get('element')
        if el in counts:
            counts[el] += 1
    max_count = max(counts.values())
    min_count = min(counts.values())
    dominant = max(counts, key=lambda k: counts[k]) if max_count > 0 else None
    lacking = min(counts, key=lambda k: counts[k]) if min_count < max_count else None
    return dominant, lacking


# ── Lunar date helpers ────────────────────────────────────────────────────────

def _to_lunar(solar_year: int, solar_month: int, solar_day: int) -> Optional[LunarDate]:
    """Convert Gregorian date to LunarDate. Returns None on failure."""
    if not _LUNARDATE_AVAILABLE:
        return None
    try:
        return LunarDate.fromSolarDate(solar_year, solar_month, solar_day)
    except Exception:
        return None


def _animal_from_lunar_year(lunar_year: int) -> str:
    return BRANCH_ANIMALS[(lunar_year - 4) % 12]


def _element_from_lunar_year(lunar_year: int) -> str:
    stem_idx = (lunar_year - 4) % 10
    return STEM_ELEMENTS[stem_idx]


def _yin_yang_from_lunar_year(lunar_year: int) -> str:
    stem_idx = (lunar_year - 4) % 10
    return STEM_POLARITY[stem_idx]


def _weeks_until(target: date, today: date) -> float:
    days = (target - today).days
    if days < 0:
        days = 0
    return round(days / 7, 1)


def _next_chinese_new_year(today: date) -> date:
    """Approximate next Chinese New Year (first new moon after Jan 21)."""
    # Try current year then next year
    for year in (today.year, today.year + 1):
        if _LUNARDATE_AVAILABLE:
            try:
                # LunarDate(year, 1, 1) → first day of lunar year 'year'
                # Convert to solar to get CNY date
                cny_lunar = LunarDate(year, 1, 1)
                cny_solar = cny_lunar.toSolarDate()
                cny = date(cny_solar.year, cny_solar.month, cny_solar.day)
                if cny > today:
                    return cny
            except Exception:
                pass
    # Fallback: Jan 25 of next year
    return date(today.year + 1, 1, 25)


def _next_chinese_month_start(today: date) -> date:
    """Approximate start of next Chinese lunar month."""
    if _LUNARDATE_AVAILABLE:
        try:
            lunar_today = LunarDate.fromSolarDate(today.year, today.month, today.day)
            # Move to day 1 of next lunar month
            if lunar_today.month == 12:
                next_lunar = LunarDate(lunar_today.year + 1, 1, 1)
            else:
                next_lunar = LunarDate(lunar_today.year, lunar_today.month + 1, 1)
            sol = next_lunar.toSolarDate()
            return date(sol.year, sol.month, sol.day)
        except Exception:
            pass
    # Fallback: ~29.5 days from today
    return today + timedelta(days=30)


# ── Relationship to natal ─────────────────────────────────────────────────────

def _relationship_to_natal(current_animal: str, natal_animal: str) -> str:
    """Describe the energetic relationship of the current year to the natal year."""
    current_idx = BRANCH_ANIMALS.index(current_animal)
    natal_idx = BRANCH_ANIMALS.index(natal_animal)
    diff = (current_idx - natal_idx) % 12

    if diff == 0:
        return 'ben ming nian (return year)'
    for pair in CLASH_PAIRS:
        if current_animal in pair and natal_animal in pair:
            return 'clash'
    if diff == 4 or diff == 8:
        return 'harmonious trine'
    if diff == 3 or diff == 9:
        return 'compatible'
    if diff == 6:
        return 'opposing'
    return 'neutral'


# ── Head engine ───────────────────────────────────────────────────────────────

class ChineseAstrologyHeadEngine:
    """
    S-08 Chinese Astrology Head Engine.

    Converts DOB to Chinese lunisolar date before all computation.
    Gregorian year is never used directly for zodiac determination.
    """

    def compute(
        self,
        dob: dict,
        birth_time: dict,
        birth_location: dict,
        query: str,
        today: Optional[date] = None,
    ) -> dict:
        """
        Compute Chinese astrology findings.

        Args:
            dob: {"day": int, "month": int, "year": int}
            birth_time: {"tier": str, "normalised_time": str|None,
                         "window_start": str|None, "window_end": str|None}
            birth_location: {"city": str, "country": str}
            query: User's question.
            today: Override for testing.

        Returns:
            S-08 contract output dict.
        """
        if today is None:
            today = date.today()

        tier = birth_time.get('tier', 'none')
        normalised_time = birth_time.get('normalised_time')
        window_start = birth_time.get('window_start')
        window_end = birth_time.get('window_end')

        solar_day = dob['day']
        solar_month = dob['month']
        solar_year = dob['year']
        solar_dob = date(solar_year, solar_month, solar_day)

        available_findings: list[str] = []
        unavailable_findings: list[str] = []
        confidence_issues: list[str] = []
        trail_sections: list[dict] = []

        # ── Chinese calendar conversion (mandatory) ───────────────────────────
        lunar = _to_lunar(solar_year, solar_month, solar_day)
        library_fallback = False

        if lunar is not None:
            lunar_year = lunar.year
            lunar_month = lunar.month
            zodiac_year_certain = True
        else:
            # Spec failure behaviour: fall back to Gregorian year, flag
            lunar_year = solar_year
            lunar_month = solar_month
            zodiac_year_certain = False
            library_fallback = True
            confidence_issues.append(
                "Chinese calendar library unavailable — Gregorian year used as fallback. "
                "Zodiac animal may be incorrect for dates near Chinese New Year."
            )

        natal_animal = _animal_from_lunar_year(lunar_year)
        natal_element = _element_from_lunar_year(lunar_year)
        yin_yang = _yin_yang_from_lunar_year(lunar_year)

        available_findings.extend(['zodiac_animal', 'zodiac_element', 'yin_yang'])
        trail_sections.append({
            'title': 'Zodiac Animal',
            'content': (
                f"Chinese year {lunar_year} ({natal_animal}, {natal_element}, {yin_yang}). "
                f"{'Converted from solar ' + str(solar_year) + ' (before Chinese New Year).' if lunar_year != solar_year else 'Converted from solar ' + str(solar_year) + '.'}"
                + (" Gregorian fallback applied." if library_fallback else "")
            ),
            'available': True,
        })

        # ── Today's Chinese date (for current energies) ───────────────────────
        today_lunar = _to_lunar(today.year, today.month, today.day)
        if today_lunar is not None:
            today_lunar_year = today_lunar.year
            today_lunar_month = today_lunar.month
        else:
            today_lunar_year = today.year
            today_lunar_month = today.month

        current_animal = _animal_from_lunar_year(today_lunar_year)
        current_element = _element_from_lunar_year(today_lunar_year)
        relationship = _relationship_to_natal(current_animal, natal_animal)

        current_month_branch_idx = (today_lunar_month + 1) % 12
        current_month_animal = BRANCH_ANIMALS[current_month_branch_idx]
        current_month_element = BRANCH_ELEMENTS[current_month_branch_idx]

        current_year_energy = {
            'animal': current_animal,
            'element': current_element,
            'relationship_to_natal': relationship,
        }
        current_month_energy = {
            'animal': current_month_animal,
            'element': current_month_element,
        }
        available_findings.extend(['current_year_energy', 'current_month_energy'])

        # ── Clash year detection ──────────────────────────────────────────────
        clash_year = (
            natal_animal != current_animal
            and any(
                natal_animal in pair and current_animal in pair
                for pair in CLASH_PAIRS
            )
        )
        clash_reason = (
            f"{natal_animal} clashes with {current_animal} year." if clash_year else None
        )
        available_findings.append('clash_year')
        trail_sections.append({
            'title': 'Clash Year',
            'content': (
                clash_reason
                if clash_year
                else f"No clash. {natal_animal} and {current_animal} are not opposing animals."
            ),
            'available': True,
        })

        # ── Ben ming nian ─────────────────────────────────────────────────────
        ben_ming_nian = current_animal == natal_animal

        # ── Four Pillars ──────────────────────────────────────────────────────
        year_p = _year_pillar(lunar_year)
        month_p = _month_pillar(lunar_year, lunar_month)
        day_p = _day_pillar(solar_dob)

        day_stem_idx = (solar_dob - date(1900, 1, 1)).days % 10
        day_element = STEM_ELEMENTS[day_stem_idx]
        month_branch_idx = (lunar_month + 1) % 12

        hour_pillar: Optional[dict] = None
        day_master: Optional[str] = HEAVENLY_STEMS[day_stem_idx]
        day_master_strength: Optional[str] = None
        dominant_element: Optional[str] = None
        lacking_element: Optional[str] = None
        four_pillars_available = True

        if tier == 'exact' and normalised_time:
            hour = _hhmm_to_hour(normalised_time)
            hour_pillar = _hour_pillar(day_stem_idx, hour)
            day_master_strength = _day_master_strength(day_element, month_branch_idx)
            all_pillars = [year_p, month_p, day_p, hour_pillar]
            dominant_element, lacking_element = _dominant_lacking(day_element, all_pillars)

        elif tier == 'approximate' and window_start and window_end:
            hour_start = _hhmm_to_hour(window_start)
            hour_end = _hhmm_to_hour(window_end)
            branch_start = _hour_to_branch_idx(hour_start)
            branch_end = _hour_to_branch_idx(hour_end)

            if branch_start == branch_end:
                # Window within single double-hour
                hour_pillar = _hour_pillar(day_stem_idx, hour_start)
                day_master_strength = _day_master_strength(day_element, month_branch_idx)
            else:
                # Window spans two double-hours — check day master strength consistency
                strength_a = _day_master_strength(day_element, branch_start)
                strength_b = _day_master_strength(day_element, branch_end)
                if strength_a == strength_b:
                    hour_pillar = _hour_pillar(day_stem_idx, hour_start)
                    day_master_strength = strength_a
                else:
                    # Ambiguous — omit hour pillar
                    hour_pillar = None
                    day_master_strength = None

            if hour_pillar:
                all_pillars = [year_p, month_p, day_p, hour_pillar]
                dominant_element, lacking_element = _dominant_lacking(day_element, all_pillars)

        else:
            # None tier — three pillars only
            hour_pillar = None
            day_master_strength = _day_master_strength(day_element, month_branch_idx)
            all_pillars = [year_p, month_p, day_p]
            dominant_element, lacking_element = _dominant_lacking(day_element, all_pillars)

        hour_out = (
            hour_pillar
            if hour_pillar
            else {'heavenly_stem': None, 'earthly_branch': None, 'element': None, 'animal': None}
        )

        four_pillars = {
            'available': four_pillars_available,
            'year_pillar': year_p,
            'month_pillar': month_p,
            'day_pillar': day_p,
            'hour_pillar': hour_out,
            'day_master': day_master,
            'day_master_strength': day_master_strength,
            'dominant_element': dominant_element,
            'lacking_element': lacking_element,
        }
        available_findings.append('four_pillars')
        trail_sections.append({
            'title': 'Four Pillars',
            'content': (
                f"Year: {year_p['heavenly_stem']}-{year_p['earthly_branch']} ({year_p['element']}, {year_p['animal']}). "
                f"Month: {month_p['heavenly_stem']}-{month_p['earthly_branch']}. "
                f"Day: {day_p['heavenly_stem']}-{day_p['earthly_branch']} (day master: {day_master}, {day_master_strength or 'strength unknown'}). "
                + (
                    f"Hour: {hour_pillar['heavenly_stem']}-{hour_pillar['earthly_branch']}."
                    if hour_pillar
                    else "Hour pillar unavailable (birth time unknown or ambiguous)."
                )
            ),
            'available': True,
        })

        # ── Luck pillar (simplified — based on day master and decade) ────────
        # Spec requires luck pillar for exact tier. Simplified: 10-year cycles from age 8.
        current_age = (
            today.year - solar_year
            - (1 if (today.month, today.day) < (solar_month, solar_day) else 0)
        )
        luck_cycle_num = max(0, (current_age - 8) // 10)
        luck_stem_idx = (day_stem_idx + luck_cycle_num + 1) % 10
        luck_branch_idx = (month_branch_idx + luck_cycle_num + 1) % 12
        luck_age_start = 8 + luck_cycle_num * 10
        luck_age_end = luck_age_start + 9
        current_luck_pillar = {
            'heavenly_stem': HEAVENLY_STEMS[luck_stem_idx],
            'earthly_branch': EARTHLY_BRANCHES[luck_branch_idx],
            'element': STEM_ELEMENTS[luck_stem_idx],
            'age_start': luck_age_start,
            'age_end': luck_age_end,
            'active': True,
        }
        available_findings.append('current_luck_pillar')

        # ── Query relevance ───────────────────────────────────────────────────
        query_relevant: list[dict] = []
        query_lower = (query or '').lower()
        query_tokens = set(re.split(r'\W+', query_lower))

        # Clash year always surfaces when true (spec requirement)
        if clash_year:
            query_relevant.append({
                'finding': 'clash_year',
                'value': True,
                'note': clash_reason,
            })

        # Ben ming nian always surfaces when true (spec requirement)
        if ben_ming_nian:
            query_relevant.append({
                'finding': 'current_year_energy',
                'value': current_year_energy,
                'note': (
                    f"Ben ming nian — {current_animal} year matches your natal {natal_animal} year. "
                    "A year of heightened sensitivity and transition."
                ),
            })

        # Domain-specific findings
        if query_tokens & _CAREER_KW:
            query_relevant.append({'finding': 'four_pillars', 'value': {
                'day_master': day_master,
                'day_master_strength': day_master_strength,
                'dominant_element': dominant_element,
            }})
            query_relevant.append({'finding': 'current_luck_pillar', 'value': current_luck_pillar})
        elif query_tokens & _RELATIONSHIP_KW:
            query_relevant.append({'finding': 'zodiac_animal', 'value': natal_animal})
            query_relevant.append({'finding': 'current_year_energy', 'value': current_year_energy})
        elif query_tokens & _HEALTH_KW:
            query_relevant.append({'finding': 'four_pillars', 'value': {
                'dominant_element': dominant_element,
                'lacking_element': lacking_element,
            }})
        else:
            query_relevant.append({'finding': 'zodiac_animal', 'value': natal_animal})
            query_relevant.append({'finding': 'current_year_energy', 'value': current_year_energy})

        # Deduplicate
        seen: set[str] = set()
        deduped: list[dict] = []
        for item in query_relevant:
            if item['finding'] not in seen:
                seen.add(item['finding'])
                deduped.append(item)
        query_relevant = deduped

        # ── Tendency window ───────────────────────────────────────────────────
        next_cny = _next_chinese_new_year(today)
        next_month_start = _next_chinese_month_start(today)
        tendency_window = {
            'min': _weeks_until(next_month_start, today),
            'max': _weeks_until(next_cny, today),
        }

        # ── Confidence ────────────────────────────────────────────────────────
        if tier == 'approximate' and not hour_pillar:
            confidence_issues.append(
                "Birth time window spans two double-hours with different day master strength — "
                "hour pillar omitted."
            )
        if tier in ('approximate', 'none'):
            confidence_issues.append(
                f"Birth time tier '{tier}' — hour pillar "
                + ("resolved within single double-hour." if hour_pillar else "unavailable.")
            )

        if confidence_issues:
            confidence_flag = True
            confidence_reason = ' '.join(confidence_issues)
        else:
            confidence_flag = False
            confidence_reason = None

        trail_sections.append({
            'title': 'Current Energies',
            'content': (
                f"Current year: {current_animal} ({current_element}), "
                f"relationship to natal: {relationship}. "
                f"Current month: {current_month_animal} ({current_month_element}). "
                + (f"Clash year active. {clash_reason}" if clash_year else "No clash year.")
                + (" Ben ming nian year." if ben_ming_nian else "")
            ),
            'available': True,
        })

        findings = {
            'zodiac_animal': natal_animal,
            'zodiac_element': natal_element,
            'zodiac_year_certain': zodiac_year_certain,
            'yin_yang': yin_yang,
            'four_pillars': four_pillars,
            'current_luck_pillar': current_luck_pillar,
            'current_year_energy': current_year_energy,
            'current_month_energy': current_month_energy,
            'clash_year': clash_year,
            'clash_reason': clash_reason,
            'query_relevant_findings': query_relevant,
            'tendency_window_weeks': tendency_window,
        }

        return {
            'head': 'chinese',
            'available_findings': available_findings,
            'unavailable_findings': unavailable_findings,
            'findings': findings,
            'confidence_flag': confidence_flag,
            'confidence_reason': confidence_reason,
            'explainability_trail': {
                'label': 'Chinese astrology',
                'sections': trail_sections,
            },
        }
