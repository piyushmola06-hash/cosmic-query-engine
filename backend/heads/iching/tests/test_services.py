"""
Tests for S-10 — I Ching Head Engine.

All LLM calls are mocked — zero real API calls are made.

Pre-computed hexagram numbers used throughout (SHA-256 via normalise_seed):
  "hello"  → normalised "hello"  → hexagram 59
  "HELLO"  → normalised "hello"  → hexagram 59  (normalisation test)
  "hel lo" → normalised "hello"  → hexagram 59  (space stripping test)
  "hél-lo" → normalised "hello"  → hexagram 59  (diacritic + punctuation)
  "5"      → normalised "5"      → hexagram 62  (not hexagram 5)
  "32"     → normalised "32"     → hexagram 25  (not hexagram 32)
  "1"      → normalised "1"      → hexagram 52  (not hexagram 1)
  "64"     → normalised "64"     → hexagram 45  (not hexagram 64)

Covers:
  - Same seed always produces same hexagram (determinism)
  - Seed normalisation (uppercase, punctuation, spaces, diacritics)
  - Number seed 1–64 goes through hash, not direct mapping
  - Non-Latin seed handled (transliterate/flag in trail)
  - Empty seed → random seed generated, trail notes it
  - All four tendency directions produce correct week windows
  - tendency_window_weeks never null
  - Hexagram lookup returns valid record for all 1–64
  - Output shape matches S-10 contract exactly
  - Trail shows full casting chain from seed to hexagram
  - All 64 hexagrams present in lookup table
  - Anti-platitude system prompt rules present
"""

import json
from unittest.mock import MagicMock

from django.test import TestCase

from heads.iching.hexagrams import HEXAGRAMS, HEXAGRAM_BY_NUMBER
from heads.iching.services import (
    IChingHeadEngine,
    TENDENCY_WINDOWS,
    _SYSTEM_PROMPT,
    normalise_seed,
    seed_to_hexagram_number,
)


# ── Mock helpers ──────────────────────────────────────────────────────────────

def _make_llm_payload(
    query_application: str = "This hexagram counsels specific action for this specific situation.",
    query_relevant_findings: list | None = None,
) -> dict:
    return {
        "query_application": query_application,
        "query_relevant_findings": query_relevant_findings or [
            "First finding specific to this query",
            "Second finding specific to this query",
        ],
    }


def _make_mock_client(payload: dict | None = None) -> MagicMock:
    if payload is None:
        payload = _make_llm_payload()
    mock_content = MagicMock()
    mock_content.text = json.dumps(payload)
    mock_response = MagicMock()
    mock_response.content = [mock_content]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    return mock_client


def _engine(payload: dict | None = None) -> IChingHeadEngine:
    return IChingHeadEngine(anthropic_client=_make_mock_client(payload))


# ── Determinism ───────────────────────────────────────────────────────────────

class TestDeterminism(TestCase):
    """Same seed always produces the same hexagram."""

    def test_same_seed_same_hexagram_repeated_calls(self):
        engine = _engine()
        r1 = engine.compute("hello", "What should I do about my career?")
        r2 = engine.compute("hello", "What should I do about my career?")
        self.assertEqual(r1["findings"]["hexagram_number"], r2["findings"]["hexagram_number"])

    def test_same_seed_different_query_same_hexagram(self):
        engine = _engine()
        r1 = engine.compute("hello", "Career question")
        r2 = engine.compute("hello", "Relationship question")
        self.assertEqual(r1["findings"]["hexagram_number"], r2["findings"]["hexagram_number"])

    def test_known_seed_hello_maps_to_hexagram_59(self):
        """Deterministic: 'hello' → normalised 'hello' → hexagram 59."""
        engine = _engine()
        result = engine.compute("hello", "What should I do?")
        self.assertEqual(result["findings"]["hexagram_number"], 59)

    def test_two_different_seeds_may_differ(self):
        """Different seeds may produce different hexagrams (not a contract — but hello≠water)."""
        engine = _engine()
        r_hello = engine.compute("hello", "query")
        r_water = engine.compute("water", "query")
        # We can't assert they must differ (hash collision possible), but we can
        # verify both produce valid hexagrams.
        self.assertIn(r_hello["findings"]["hexagram_number"], range(1, 65))
        self.assertIn(r_water["findings"]["hexagram_number"], range(1, 65))


# ── Seed normalisation ────────────────────────────────────────────────────────

class TestSeedNormalisation(TestCase):
    """Uppercase, spaces, punctuation, diacritics → same result as lowercase."""

    def test_uppercase_same_as_lowercase(self):
        engine = _engine()
        r_lower = engine.compute("hello", "query")
        r_upper = engine.compute("HELLO", "query")
        self.assertEqual(r_lower["findings"]["hexagram_number"], r_upper["findings"]["hexagram_number"])

    def test_spaces_stripped(self):
        engine = _engine()
        r_clean = engine.compute("hello", "query")
        r_spaces = engine.compute("hel lo", "query")
        self.assertEqual(r_clean["findings"]["hexagram_number"], r_spaces["findings"]["hexagram_number"])

    def test_punctuation_stripped(self):
        engine = _engine()
        r_clean = engine.compute("hello", "query")
        r_punct = engine.compute("hél-lo", "query")  # diacritic + hyphen stripped
        self.assertEqual(r_clean["findings"]["hexagram_number"], r_punct["findings"]["hexagram_number"])

    def test_mixed_case_spaces_punctuation(self):
        engine = _engine()
        r_clean = engine.compute("hello", "query")
        r_mixed = engine.compute("  H-E-L-L-O  ", "query")
        self.assertEqual(r_clean["findings"]["hexagram_number"], r_mixed["findings"]["hexagram_number"])

    def test_normalise_seed_function_directly(self):
        """normalise_seed() returns same string for equivalent inputs."""
        n1, _ = normalise_seed("hello")
        n2, _ = normalise_seed("HELLO")
        n3, _ = normalise_seed("hel lo")
        n4, _ = normalise_seed("hél-lo")
        self.assertEqual(n1, n2)
        self.assertEqual(n1, n3)
        self.assertEqual(n1, n4)

    def test_normalise_seed_non_latin_flag(self):
        """Non-Latin characters set non_latin=True."""
        _, latin_flag = normalise_seed("hello")
        _, non_latin_flag = normalise_seed("水")
        self.assertFalse(latin_flag)
        self.assertTrue(non_latin_flag)


# ── Number seed 1–64 goes through hash ───────────────────────────────────────

class TestNumberSeedHashing(TestCase):
    """Number seeds 1–64 go through the hash algorithm, not direct mapping."""

    def test_seed_5_does_not_map_to_hexagram_5(self):
        """Seed '5' hashes to hexagram 62, not hexagram 5."""
        engine = _engine()
        result = engine.compute("5", "query")
        self.assertEqual(result["findings"]["hexagram_number"], 62)
        self.assertNotEqual(result["findings"]["hexagram_number"], 5)

    def test_seed_32_does_not_map_to_hexagram_32(self):
        """Seed '32' hashes to hexagram 25, not hexagram 32."""
        engine = _engine()
        result = engine.compute("32", "query")
        self.assertEqual(result["findings"]["hexagram_number"], 25)
        self.assertNotEqual(result["findings"]["hexagram_number"], 32)

    def test_seed_1_does_not_map_to_hexagram_1(self):
        """Seed '1' hashes to hexagram 52, not hexagram 1."""
        engine = _engine()
        result = engine.compute("1", "query")
        self.assertEqual(result["findings"]["hexagram_number"], 52)
        self.assertNotEqual(result["findings"]["hexagram_number"], 1)

    def test_seed_64_does_not_map_to_hexagram_64(self):
        """Seed '64' hashes to hexagram 45, not hexagram 64."""
        engine = _engine()
        result = engine.compute("64", "query")
        self.assertEqual(result["findings"]["hexagram_number"], 45)
        self.assertNotEqual(result["findings"]["hexagram_number"], 64)

    def test_integer_seed_same_as_string_seed(self):
        """Numeric seed passed as integer produces same result as string."""
        engine = _engine()
        r_int = engine.compute(5, "query")
        r_str = engine.compute("5", "query")
        self.assertEqual(r_int["findings"]["hexagram_number"], r_str["findings"]["hexagram_number"])

    def test_seed_to_hexagram_number_deterministic(self):
        """seed_to_hexagram_number is deterministic for same input."""
        n1, _ = seed_to_hexagram_number("hello")
        n2, _ = seed_to_hexagram_number("hello")
        self.assertEqual(n1, n2)
        self.assertEqual(n1, 59)

    def test_seed_to_hexagram_number_range(self):
        """seed_to_hexagram_number always returns 1–64."""
        for seed in ["a", "z", "0", "99", "hello", "world", "x" * 100]:
            num, _ = seed_to_hexagram_number(seed)
            self.assertGreaterEqual(num, 1)
            self.assertLessEqual(num, 64)


# ── Non-Latin seed handling ───────────────────────────────────────────────────

class TestNonLatinSeed(TestCase):
    """Non-Latin seeds are handled without crashing; trail notes transliteration."""

    def test_cjk_seed_produces_valid_hexagram(self):
        engine = _engine()
        result = engine.compute("水", "What path should I take?")
        self.assertIn(result["findings"]["hexagram_number"], range(1, 65))

    def test_cjk_seed_deterministic(self):
        engine = _engine()
        r1 = engine.compute("水", "query")
        r2 = engine.compute("水", "query")
        self.assertEqual(r1["findings"]["hexagram_number"], r2["findings"]["hexagram_number"])

    def test_non_latin_flagged_in_trail(self):
        engine = _engine()
        result = engine.compute("水", "query")
        cast_section = next(
            s for s in result["explainability_trail"]["sections"]
            if s["title"] == "Seed + Hexagram Cast"
        )
        content_lower = cast_section["content"].lower()
        self.assertTrue(
            any(kw in content_lower for kw in ("non-latin", "transliteration", "nfkd")),
            f"Trail should note non-Latin handling, got: {cast_section['content']}",
        )

    def test_arabic_seed_does_not_crash(self):
        engine = _engine()
        result = engine.compute("مرحبا", "query")
        self.assertIn(result["findings"]["hexagram_number"], range(1, 65))

    def test_mixed_latin_non_latin_seed(self):
        """A mixed seed (Latin + CJK) uses the Latin portion for hashing."""
        engine = _engine()
        result = engine.compute("hello水", "query")
        # "hello水" → NFKD → ASCII part = "hello" → hexagram 59
        self.assertEqual(result["findings"]["hexagram_number"], 59)


# ── Empty seed ────────────────────────────────────────────────────────────────

class TestEmptySeed(TestCase):
    """Empty or None seed triggers random seed generation; trail notes it."""

    def test_empty_string_seed_generates_random(self):
        engine = _engine()
        result = engine.compute("", "query")
        self.assertIn(result["findings"]["hexagram_number"], range(1, 65))
        self.assertNotEqual(result["findings"]["seed_used"], "")

    def test_none_seed_generates_random(self):
        engine = _engine()
        result = engine.compute(None, "query")
        self.assertIn(result["findings"]["hexagram_number"], range(1, 65))

    def test_empty_seed_noted_in_trail(self):
        engine = _engine()
        result = engine.compute("", "query")
        cast_section = next(
            s for s in result["explainability_trail"]["sections"]
            if s["title"] == "Seed + Hexagram Cast"
        )
        self.assertIn("random", cast_section["content"].lower())

    def test_whitespace_only_seed_treated_as_empty(self):
        """A seed of only spaces is treated the same as empty."""
        engine = _engine()
        result = engine.compute("   ", "query")
        # After strip the seed_str is "", which triggers random generation
        # or after normalise produces empty → random
        self.assertIn(result["findings"]["hexagram_number"], range(1, 65))

    def test_two_empty_calls_may_produce_different_hexagrams(self):
        """Each empty seed generates a fresh random seed (different results possible)."""
        engine = _engine()
        results = {engine.compute("", "q")["findings"]["hexagram_number"] for _ in range(5)}
        # With random seeds there's a very high probability of getting >1 unique value
        # We only assert each result is valid
        for r in results:
            self.assertIn(r, range(1, 65))


# ── Tendency window ───────────────────────────────────────────────────────────

class TestTendencyWindow(TestCase):
    """All four directions produce correct windows; window is never null."""

    EXPECTED_WINDOWS = {
        "forward":   {"min": 2,  "max": 8},
        "pause":     {"min": 4,  "max": 16},
        "retreat":   {"min": 8,  "max": 24},
        "transform": {"min": 6,  "max": 20},
    }

    def _result_for_hexagram_number(self, number: int) -> dict:
        """Run compute with a seed that hashes to the given hexagram number."""
        # Find any seed that maps there by scanning known seeds or using the
        # hexagram data directly to patch via the normalise route.
        # Easier: call compute and patch the hexagram lookup via a known seed.
        # For reliability, we find a seed that hashes to `number` by brute-force
        # across a small set of candidates, or we test direction mappings directly.
        raise NotImplementedError("Use direct direction mapping test instead.")

    def test_forward_window(self):
        self.assertEqual(TENDENCY_WINDOWS["forward"], {"min": 2, "max": 8})

    def test_pause_window(self):
        self.assertEqual(TENDENCY_WINDOWS["pause"], {"min": 4, "max": 16})

    def test_retreat_window(self):
        self.assertEqual(TENDENCY_WINDOWS["retreat"], {"min": 8, "max": 24})

    def test_transform_window(self):
        self.assertEqual(TENDENCY_WINDOWS["transform"], {"min": 6, "max": 20})

    def test_all_four_directions_covered(self):
        self.assertEqual(set(TENDENCY_WINDOWS.keys()), {"forward", "pause", "retreat", "transform"})

    def test_tendency_window_in_output_matches_direction(self):
        """The output tendency_window_weeks matches the hexagram's direction."""
        # seed "hello" → hexagram 59 (Dispersion) → tendency_direction = "forward"
        engine = _engine()
        result = engine.compute("hello", "query")
        direction = result["findings"]["tendency_direction"]
        window = result["findings"]["tendency_window_weeks"]
        self.assertEqual(window, TENDENCY_WINDOWS[direction])

    def test_tendency_window_never_null(self):
        """tendency_window_weeks is always a dict with min and max, never None."""
        engine = _engine()
        for seed in ["hello", "world", "5", "fire", "water", "earth", "wind", "moon"]:
            result = engine.compute(seed, "query")
            window = result["findings"]["tendency_window_weeks"]
            self.assertIsNotNone(window, f"tendency_window_weeks is None for seed '{seed}'")
            self.assertIn("min", window)
            self.assertIn("max", window)
            self.assertIsInstance(window["min"], int)
            self.assertIsInstance(window["max"], int)
            self.assertLess(window["min"], window["max"])

    def test_tendency_direction_valid_values(self):
        """tendency_direction is always one of the four valid values."""
        engine = _engine()
        valid = {"forward", "pause", "retreat", "transform"}
        for seed in ["hello", "world", "5", "32", "one", "two", "three", "four"]:
            result = engine.compute(seed, "query")
            self.assertIn(result["findings"]["tendency_direction"], valid)

    def test_window_min_always_lt_max(self):
        """min is always less than max for every possible window."""
        for direction, window in TENDENCY_WINDOWS.items():
            self.assertLess(window["min"], window["max"], f"Direction {direction}: min >= max")


# ── Hexagram lookup ───────────────────────────────────────────────────────────

class TestHexagramLookup(TestCase):
    """Hexagram lookup returns valid records for all 1–64."""

    def test_all_64_hexagrams_accessible(self):
        for i in range(1, 65):
            self.assertIn(i, HEXAGRAM_BY_NUMBER, f"Hexagram {i} missing from HEXAGRAM_BY_NUMBER")

    def test_each_hexagram_has_required_fields(self):
        required = {
            "number", "name_chinese", "name_english", "image",
            "judgment", "core_theme", "polarity",
            "domain_affinities", "tendency_direction",
        }
        for i in range(1, 65):
            hexagram = HEXAGRAM_BY_NUMBER[i]
            for field in required:
                self.assertIn(field, hexagram, f"Hexagram {i} missing field '{field}'")

    def test_polarity_valid_values(self):
        valid = {"yang", "yin", "balanced"}
        for i in range(1, 65):
            p = HEXAGRAM_BY_NUMBER[i]["polarity"]
            self.assertIn(p, valid, f"Hexagram {i} polarity '{p}' not valid")

    def test_tendency_direction_valid_values(self):
        valid = {"forward", "pause", "retreat", "transform"}
        for i in range(1, 65):
            td = HEXAGRAM_BY_NUMBER[i]["tendency_direction"]
            self.assertIn(td, valid, f"Hexagram {i} tendency_direction '{td}' not valid")

    def test_domain_affinities_non_empty_list(self):
        for i in range(1, 65):
            da = HEXAGRAM_BY_NUMBER[i]["domain_affinities"]
            self.assertIsInstance(da, list, f"Hexagram {i} domain_affinities not a list")
            self.assertGreater(len(da), 0, f"Hexagram {i} domain_affinities is empty")

    def test_name_english_non_empty(self):
        for i in range(1, 65):
            name = HEXAGRAM_BY_NUMBER[i]["name_english"]
            self.assertTrue(len(name) > 0, f"Hexagram {i} name_english is empty")

    def test_name_chinese_non_empty(self):
        for i in range(1, 65):
            name = HEXAGRAM_BY_NUMBER[i]["name_chinese"]
            self.assertTrue(len(name) > 0, f"Hexagram {i} name_chinese is empty")

    def test_hexagram_numbers_sequential(self):
        """HEXAGRAMS list must contain exactly 64 entries numbered 1–64."""
        numbers = [h["number"] for h in HEXAGRAMS]
        self.assertEqual(sorted(numbers), list(range(1, 65)))


# ── All 64 hexagrams in lookup table ─────────────────────────────────────────

class TestAllHexagramsPresent(TestCase):
    """All 64 hexagrams must be in the lookup table."""

    def test_hexagrams_list_has_exactly_64_entries(self):
        self.assertEqual(len(HEXAGRAMS), 64)

    def test_hexagram_by_number_has_exactly_64_entries(self):
        self.assertEqual(len(HEXAGRAM_BY_NUMBER), 64)

    def test_no_duplicate_numbers(self):
        numbers = [h["number"] for h in HEXAGRAMS]
        self.assertEqual(len(numbers), len(set(numbers)))

    def test_all_known_hexagrams_by_name(self):
        """Spot-check key hexagrams are present and correctly named."""
        spot_checks = {
            1:  "The Creative",
            2:  "The Receptive",
            11: "Peace",
            12: "Standstill",
            29: "The Abysmal",
            30: "The Clinging",
            63: "After Completion",
            64: "Before Completion",
        }
        for number, expected_name in spot_checks.items():
            actual = HEXAGRAM_BY_NUMBER[number]["name_english"]
            self.assertEqual(actual, expected_name, f"Hexagram {number}: expected '{expected_name}', got '{actual}'")

    def test_all_four_tendency_directions_represented(self):
        """All four directions must appear in the 64 hexagrams."""
        directions = {h["tendency_direction"] for h in HEXAGRAMS}
        self.assertEqual(directions, {"forward", "pause", "retreat", "transform"})

    def test_all_three_polarities_represented(self):
        """All three polarities must appear in the 64 hexagrams."""
        polarities = {h["polarity"] for h in HEXAGRAMS}
        self.assertEqual(polarities, {"yang", "yin", "balanced"})


# ── Output shape ──────────────────────────────────────────────────────────────

class TestOutputShape(TestCase):
    """Output shape matches S-10 contract exactly."""

    def setUp(self):
        self.engine = _engine()
        self.result = self.engine.compute("hello", "Should I change careers?")

    def test_head_is_iching(self):
        self.assertEqual(self.result["head"], "iching")

    def test_available_findings_is_list(self):
        self.assertIsInstance(self.result["available_findings"], list)
        self.assertTrue(len(self.result["available_findings"]) > 0)

    def test_unavailable_findings_is_list(self):
        self.assertIsInstance(self.result["unavailable_findings"], list)

    def test_findings_all_contract_keys_present(self):
        required = {
            "seed_used", "hexagram_number", "hexagram_name_chinese",
            "hexagram_name_english", "image", "judgment", "core_theme",
            "polarity", "tendency_direction", "query_application",
            "query_relevant_findings", "tendency_window_weeks",
        }
        for key in required:
            self.assertIn(key, self.result["findings"], f"Missing findings key: {key}")

    def test_confidence_flag_always_false(self):
        self.assertFalse(self.result["confidence_flag"])

    def test_confidence_reason_always_none(self):
        self.assertIsNone(self.result["confidence_reason"])

    def test_hexagram_number_in_range(self):
        self.assertIn(self.result["findings"]["hexagram_number"], range(1, 65))

    def test_tendency_window_shape(self):
        w = self.result["findings"]["tendency_window_weeks"]
        self.assertIsInstance(w, dict)
        self.assertIn("min", w)
        self.assertIn("max", w)

    def test_query_application_is_string(self):
        self.assertIsInstance(self.result["findings"]["query_application"], str)

    def test_query_relevant_findings_is_list(self):
        self.assertIsInstance(self.result["findings"]["query_relevant_findings"], list)

    def test_explainability_trail_shape(self):
        trail = self.result["explainability_trail"]
        self.assertEqual(trail["label"], "I Ching")
        self.assertIsInstance(trail["sections"], list)

    def test_trail_sections_have_required_fields(self):
        for section in self.result["explainability_trail"]["sections"]:
            self.assertIn("title", section)
            self.assertIn("content", section)
            self.assertIn("available", section)


# ── Trail casting chain ───────────────────────────────────────────────────────

class TestTrailCastingChain(TestCase):
    """Trail must show full casting chain: seed → normalised → hash → hexagram."""

    def _cast_section(self, result: dict) -> dict:
        return next(
            s for s in result["explainability_trail"]["sections"]
            if s["title"] == "Seed + Hexagram Cast"
        )

    def test_cast_section_present(self):
        result = _engine().compute("hello", "query")
        section = self._cast_section(result)
        self.assertIsNotNone(section)

    def test_cast_section_shows_original_seed(self):
        result = _engine().compute("hello", "query")
        section = self._cast_section(result)
        self.assertIn("hello", section["content"])

    def test_cast_section_shows_normalised_seed(self):
        result = _engine().compute("HELLO WORLD", "query")
        section = self._cast_section(result)
        # normalised is "helloworld"
        self.assertIn("helloworld", section["content"])

    def test_cast_section_shows_hash_snippet(self):
        """Cast section must include the first 8 chars of the SHA-256 digest."""
        import hashlib
        normalised = "hello"
        expected_snippet = hashlib.sha256(normalised.encode()).hexdigest()[:8]
        result = _engine().compute("hello", "query")
        section = self._cast_section(result)
        self.assertIn(expected_snippet, section["content"])

    def test_cast_section_shows_hexagram_number(self):
        result = _engine().compute("hello", "query")
        section = self._cast_section(result)
        self.assertIn("59", section["content"])  # hello → hexagram 59

    def test_trail_has_six_sections(self):
        """Trail should have all six S-10 sections."""
        result = _engine().compute("hello", "query")
        titles = {s["title"] for s in result["explainability_trail"]["sections"]}
        required_titles = {
            "Seed + Hexagram Cast",
            "Hexagram Identity",
            "Image + Judgment",
            "Applied to Your Question",
            "Tendency Direction",
            "Query-Relevant Findings",
        }
        for title in required_titles:
            self.assertIn(title, titles, f"Trail missing section: '{title}'")

    def test_hexagram_identity_section_content(self):
        result = _engine().compute("hello", "query")
        section = next(s for s in result["explainability_trail"]["sections"]
                       if s["title"] == "Hexagram Identity")
        self.assertIn("59", section["content"])
        self.assertIn("渙", section["content"])  # Dispersion Chinese name

    def test_tendency_direction_section_shows_window(self):
        result = _engine().compute("hello", "query")  # hex 59, direction=forward
        section = next(s for s in result["explainability_trail"]["sections"]
                       if s["title"] == "Tendency Direction")
        # forward → 2–8 weeks
        self.assertIn("2", section["content"])
        self.assertIn("8", section["content"])


# ── LLM client injection ──────────────────────────────────────────────────────

class TestClientInjection(TestCase):
    """Injected mock client is used; no real API call is made."""

    def test_injected_client_called_once(self):
        mock_client = _make_mock_client()
        engine = IChingHeadEngine(anthropic_client=mock_client)
        engine.compute("hello", "query")
        mock_client.messages.create.assert_called_once()

    def test_system_prompt_passed_to_api(self):
        mock_client = _make_mock_client()
        engine = IChingHeadEngine(anthropic_client=mock_client)
        engine.compute("hello", "query")
        kwargs = mock_client.messages.create.call_args[1]
        self.assertEqual(kwargs["system"], _SYSTEM_PROMPT)

    def test_hexagram_details_in_user_message(self):
        mock_client = _make_mock_client()
        engine = IChingHeadEngine(anthropic_client=mock_client)
        engine.compute("hello", "Should I change careers?")
        kwargs = mock_client.messages.create.call_args[1]
        user_content = kwargs["messages"][0]["content"]
        # hello → hexagram 59 (渙 Dispersion)
        self.assertIn("59", user_content)
        self.assertIn("渙", user_content)
        self.assertIn("Should I change careers?", user_content)

    def test_model_passed_in_api_call(self):
        mock_client = _make_mock_client()
        engine = IChingHeadEngine(anthropic_client=mock_client)
        engine.compute("hello", "query")
        kwargs = mock_client.messages.create.call_args[1]
        self.assertIn("model", kwargs)
        self.assertIsInstance(kwargs["model"], str)
        self.assertTrue(len(kwargs["model"]) > 0)


# ── Anti-platitude system prompt ─────────────────────────────────────────────

class TestSystemPromptAntiPlatitudeRules(TestCase):
    """Anti-platitude rules must be present in the system prompt."""

    def test_forbidden_outputs_listed(self):
        forbidden = [
            "Everything happens for a reason",
            "Trust the process",
            "Focus on what you can control",
            "Let go of what does not serve you",
        ]
        for phrase in forbidden:
            self.assertIn(phrase, _SYSTEM_PROMPT,
                          f"Anti-platitude rule missing: '{phrase}'")

    def test_copy_paste_test_instruction_present(self):
        self.assertIn("completely different question", _SYSTEM_PROMPT)

    def test_query_specificity_rule_present(self):
        self.assertIn("specific to this query", _SYSTEM_PROMPT)

    def test_judgment_paraphrase_rule_present(self):
        self.assertIn("not paraphrase the judgment generically", _SYSTEM_PROMPT)
