"""
Tests for S-11 — Synthesis Layer.

All LLM calls are mocked — zero real API calls are made.

Covers:
  - Convergence detection: timing overlap, domain alignment, caution alignment
  - Divergence detection: timing gap, direction conflict
  - Universal signals surface when true, absent when false
  - Composite tendency window correctly averaged
  - All null windows → tendency_window null
  - Null head findings excluded gracefully
  - Empty working set → summary null, synthesis_notes set
  - Output shape matches S-11 contract exactly
  - Word "journey" never in summary (self-review enforced)
  - Summary never opens with "Based on your birth chart" (self-review flagged)
  - Self-review checklist enforced (word count, bullet list, journey, opener)
  - System prompt contains anti-platitude and anti-optimism rules
"""

import json
from unittest.mock import MagicMock

from django.test import TestCase

from synthesis.services import (
    SynthesisLayer,
    _SYSTEM_PROMPT,
    _truncate_at_sentence_boundary,
)


# ── Test data builders ────────────────────────────────────────────────────────

def _mock_client(summary: str = "The combined readings point clearly to a period of consolidation rather than expansion, with the timing window of roughly four to ten weeks confirmed by multiple systems.") -> MagicMock:
    """Return a mock Anthropic client that returns the given summary."""
    mock_content = MagicMock()
    mock_content.text = json.dumps({"summary": summary})
    mock_response = MagicMock()
    mock_response.content = [mock_content]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    return mock_client


def _engine(summary: str | None = None) -> SynthesisLayer:
    client = _mock_client(summary) if summary else _mock_client()
    return SynthesisLayer(anthropic_client=client)


def _numerology_head(
    min_weeks: float = 4.0,
    max_weeks: float = 12.0,
    qrf: list | None = None,
) -> dict:
    """Build a minimal numerology head output."""
    return {
        "head": "numerology",
        "findings": {
            "life_path": 7,
            "personal_year": 5,
            "query_relevant_findings": qrf if qrf is not None else [
                {"finding": "personal_year", "value": 5, "note": "Year of change."}
            ],
            "tendency_window_weeks": {"min": min_weeks, "max": max_weeks},
        },
        "confidence_flag": False,
        "confidence_reason": None,
    }


def _iching_head(
    hexagram_number: int = 59,
    tendency_direction: str = "forward",
    min_weeks: float = 2.0,
    max_weeks: float = 8.0,
    qrf: list | None = None,
) -> dict:
    """Build a minimal I Ching head output."""
    return {
        "head": "iching",
        "findings": {
            "hexagram_number": hexagram_number,
            "hexagram_name_english": "Dispersion",
            "tendency_direction": tendency_direction,
            "query_application": "The I Ching counsels dispersal of rigid structures.",
            "query_relevant_findings": qrf if qrf is not None else [
                "Dispersion: dissolve the rigidity before attempting to rebuild."
            ],
            "tendency_window_weeks": {"min": min_weeks, "max": max_weeks},
        },
        "confidence_flag": False,
        "confidence_reason": None,
    }


def _chinese_head(
    clash_year: bool = False,
    tendency_direction: str | None = None,
    min_weeks: float = 3.0,
    max_weeks: float = 10.0,
    qrf: list | None = None,
) -> dict:
    """Build a minimal Chinese head output."""
    findings: dict = {
        "zodiac_animal": "Rabbit",
        "clash_year": clash_year,
        "clash_reason": "Rabbit clashes with Rooster year." if clash_year else None,
        "query_relevant_findings": qrf if qrf is not None else [
            {"finding": "zodiac_animal", "value": "Rabbit", "note": "Current year challenges natal energy."}
        ],
        "tendency_window_weeks": {"min": min_weeks, "max": max_weeks},
    }
    if tendency_direction is not None:
        findings["tendency_direction"] = tendency_direction
    return {
        "head": "chinese",
        "findings": findings,
        "confidence_flag": False,
        "confidence_reason": None,
    }


def _philosophy_head(
    convergence: str | None = None,
    divergence: str | None = None,
    qrf: list | None = None,
) -> dict:
    """Build a minimal philosophy head output (tendency_window always null)."""
    return {
        "head": "philosophy",
        "findings": {
            "query_theme": "Career decision at a crossroads.",
            "query_category": "career",
            "frameworks": {
                "stoicism": {"applied_finding": "What is not in your control is the outcome, only the decision."},
                "vedanta": {"applied_finding": "The witness-self observes the choice without being defined by it."},
                "karma": {"applied_finding": "Present choices shape agami karma most powerfully now."},
            },
            "convergence": convergence,
            "divergence": divergence,
            "query_relevant_findings": qrf if qrf is not None else [
                "All three frameworks converge on taking deliberate present action."
            ],
            "tendency_window_weeks": None,
        },
        "confidence_flag": False,
        "confidence_reason": None,
    }


def _no_universal_signals() -> dict:
    return {
        "personal_year_9": False,
        "clash_year": False,
        "ben_ming_nian": False,
        "clash_reason": None,
        "ben_ming_nian_reason": None,
    }


def _universal_signals(
    personal_year_9: bool = False,
    clash_year: bool = False,
    ben_ming_nian: bool = False,
    clash_reason: str | None = None,
    ben_ming_nian_reason: str | None = None,
) -> dict:
    return {
        "personal_year_9": personal_year_9,
        "clash_year": clash_year,
        "ben_ming_nian": ben_ming_nian,
        "clash_reason": clash_reason,
        "ben_ming_nian_reason": ben_ming_nian_reason,
    }


# ── Convergence detection ─────────────────────────────────────────────────────

class TestConvergenceDetection(TestCase):
    """Convergence signals detected from structured head findings."""

    def test_timing_overlap_detected(self):
        """Two heads with overlapping windows → timing convergence signal."""
        # numerology: 4–12, iching: 2–8 → overlap at 4–8
        layer = _engine()
        result = layer.synthesise(
            query="Career question",
            query_category="career",
            active_heads=["numerology", "iching"],
            head_findings={
                "numerology": _numerology_head(min_weeks=4, max_weeks=12),
                "iching": _iching_head(min_weeks=2, max_weeks=8),
            },
            universal_signals=_no_universal_signals(),
        )
        timing_signals = [s for s in result["convergence_signals"] if "timing" in s.lower() or "overlap" in s.lower()]
        self.assertTrue(
            any("align" in s.lower() or "overlap" in s.lower() for s in result["convergence_signals"]),
            f"Expected timing convergence signal, got: {result['convergence_signals']}",
        )

    def test_timing_overlap_content(self):
        """Timing convergence signal names both contributing heads."""
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="career",
            active_heads=["numerology", "iching"],
            head_findings={
                "numerology": _numerology_head(min_weeks=4, max_weeks=12),
                "iching": _iching_head(min_weeks=2, max_weeks=8),
            },
            universal_signals=_no_universal_signals(),
        )
        timing_signal = next(
            (s for s in result["convergence_signals"] if "Timing alignment" in s), None
        )
        self.assertIsNotNone(timing_signal, "Timing alignment signal missing")
        self.assertIn("numerology", timing_signal)
        self.assertIn("iching", timing_signal)

    def test_domain_alignment_two_heads(self):
        """Two or more contributing heads → domain alignment signal."""
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="career",
            active_heads=["numerology", "iching"],
            head_findings={
                "numerology": _numerology_head(),
                "iching": _iching_head(),
            },
            universal_signals=_no_universal_signals(),
        )
        domain_signals = [s for s in result["convergence_signals"] if "domain" in s.lower()]
        self.assertTrue(len(domain_signals) >= 1, "Expected domain alignment signal")

    def test_caution_alignment_two_caution_heads(self):
        """Two heads signalling caution → caution convergence signal."""
        layer = _engine()
        result = layer.synthesise(
            query="Should I take this risk?",
            query_category="career",
            active_heads=["iching", "chinese"],
            head_findings={
                "iching": _iching_head(tendency_direction="retreat"),
                "chinese": _chinese_head(clash_year=True),
            },
            universal_signals=_no_universal_signals(),
        )
        caution_signals = [s for s in result["convergence_signals"] if "caution" in s.lower()]
        self.assertTrue(
            len(caution_signals) >= 1,
            f"Expected caution alignment signal, got: {result['convergence_signals']}",
        )

    def test_caution_alignment_names_heads(self):
        """Caution alignment signal names both caution heads."""
        layer = _engine()
        result = layer.synthesise(
            query="Should I invest now?",
            query_category="finances",
            active_heads=["iching", "chinese"],
            head_findings={
                "iching": _iching_head(tendency_direction="retreat"),
                "chinese": _chinese_head(clash_year=True),
            },
            universal_signals=_no_universal_signals(),
        )
        caution_signal = next(
            (s for s in result["convergence_signals"] if "caution" in s.lower()), None
        )
        self.assertIsNotNone(caution_signal)
        self.assertIn("iching", caution_signal.lower())
        self.assertIn("chinese", caution_signal.lower())

    def test_philosophy_convergence_included_when_non_null(self):
        """Philosophy convergence field non-null → included as convergence signal."""
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="direction",
            active_heads=["philosophy"],
            head_findings={
                "philosophy": _philosophy_head(
                    convergence="All three frameworks agree on present action over strategic delay."
                )
            },
            universal_signals=_no_universal_signals(),
        )
        phil_signals = [s for s in result["convergence_signals"] if "hilosoph" in s]
        self.assertTrue(len(phil_signals) >= 1)
        self.assertIn("All three frameworks agree", phil_signals[0])

    def test_no_convergence_signals_single_head(self):
        """Single head with no overlapping second — no timing or caution convergence."""
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="general",
            active_heads=["philosophy"],
            head_findings={"philosophy": _philosophy_head()},
            universal_signals=_no_universal_signals(),
        )
        timing = [s for s in result["convergence_signals"] if "Timing alignment" in s]
        caution = [s for s in result["convergence_signals"] if "Caution alignment" in s]
        self.assertEqual(len(timing), 0, "Should not have timing signal with single head")
        self.assertEqual(len(caution), 0, "Should not have caution signal with single head")


# ── Divergence detection ──────────────────────────────────────────────────────

class TestDivergenceDetection(TestCase):
    """Divergence signals detected from structured head findings."""

    def test_timing_divergence_non_overlapping_windows(self):
        """Two heads with non-overlapping windows → timing divergence signal."""
        # numerology: 10–20 weeks, iching: 2–8 weeks → no overlap
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="career",
            active_heads=["numerology", "iching"],
            head_findings={
                "numerology": _numerology_head(min_weeks=10, max_weeks=20),
                "iching": _iching_head(min_weeks=2, max_weeks=8),
            },
            universal_signals=_no_universal_signals(),
        )
        timing_div = [s for s in result["divergence_signals"] if "Timing divergence" in s]
        self.assertTrue(
            len(timing_div) >= 1,
            f"Expected timing divergence signal, got: {result['divergence_signals']}",
        )

    def test_timing_divergence_names_heads_and_ranges(self):
        """Timing divergence signal includes head names and week ranges."""
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="career",
            active_heads=["numerology", "iching"],
            head_findings={
                "numerology": _numerology_head(min_weeks=10, max_weeks=20),
                "iching": _iching_head(min_weeks=2, max_weeks=8),
            },
            universal_signals=_no_universal_signals(),
        )
        div_signal = next(s for s in result["divergence_signals"] if "Timing divergence" in s)
        self.assertIn("numerology", div_signal)
        self.assertIn("iching", div_signal)
        self.assertIn("weeks", div_signal)

    def test_direction_conflict_forward_vs_caution(self):
        """I Ching forward + Chinese clash → direction divergence signal."""
        layer = _engine()
        result = layer.synthesise(
            query="Should I launch the business now?",
            query_category="career",
            active_heads=["iching", "chinese"],
            head_findings={
                "iching": _iching_head(tendency_direction="forward"),
                "chinese": _chinese_head(clash_year=True),
            },
            universal_signals=_no_universal_signals(),
        )
        dir_div = [s for s in result["divergence_signals"] if "Direction divergence" in s]
        self.assertTrue(
            len(dir_div) >= 1,
            f"Expected direction divergence signal, got: {result['divergence_signals']}",
        )

    def test_direction_conflict_names_both_sides(self):
        """Direction divergence names the forward head and the caution head."""
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="career",
            active_heads=["iching", "chinese"],
            head_findings={
                "iching": _iching_head(tendency_direction="forward"),
                "chinese": _chinese_head(clash_year=True),
            },
            universal_signals=_no_universal_signals(),
        )
        div_signal = next(
            (s for s in result["divergence_signals"] if "Direction divergence" in s), None
        )
        self.assertIsNotNone(div_signal)
        self.assertIn("iching", div_signal.lower())
        self.assertIn("chinese", div_signal.lower())

    def test_philosophy_divergence_included_when_non_null(self):
        """Philosophy divergence field non-null → included as divergence signal."""
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="direction",
            active_heads=["philosophy"],
            head_findings={
                "philosophy": _philosophy_head(
                    divergence="Stoicism counsels action; Vedanta counsels non-attachment to outcome."
                )
            },
            universal_signals=_no_universal_signals(),
        )
        phil_divs = [s for s in result["divergence_signals"] if "hilosoph" in s]
        self.assertTrue(len(phil_divs) >= 1)
        self.assertIn("Stoicism", phil_divs[0])

    def test_no_divergence_when_windows_overlap(self):
        """When all windows overlap, no timing divergence signal."""
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="career",
            active_heads=["numerology", "iching"],
            head_findings={
                "numerology": _numerology_head(min_weeks=4, max_weeks=12),
                "iching": _iching_head(min_weeks=2, max_weeks=8),
            },
            universal_signals=_no_universal_signals(),
        )
        timing_div = [s for s in result["divergence_signals"] if "Timing divergence" in s]
        self.assertEqual(len(timing_div), 0, "Should not have timing divergence when windows overlap")

    def test_divergence_signals_not_suppressed(self):
        """Divergence signals are present in output — never suppressed."""
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="career",
            active_heads=["numerology", "iching"],
            head_findings={
                "numerology": _numerology_head(min_weeks=10, max_weeks=20),
                "iching": _iching_head(min_weeks=2, max_weeks=8),
            },
            universal_signals=_no_universal_signals(),
        )
        self.assertIsInstance(result["divergence_signals"], list)
        self.assertTrue(len(result["divergence_signals"]) > 0)


# ── Universal signals ─────────────────────────────────────────────────────────

class TestUniversalSignals(TestCase):
    """Universal signals surface when true; absent when false."""

    def test_personal_year_9_surfaces_when_true(self):
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="direction",
            active_heads=["numerology"],
            head_findings={"numerology": _numerology_head()},
            universal_signals=_universal_signals(personal_year_9=True),
        )
        self.assertTrue(
            any("completion and release" in s for s in result["universal_signals_surfaced"]),
            f"personal_year_9 not surfaced: {result['universal_signals_surfaced']}",
        )

    def test_personal_year_9_absent_when_false(self):
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="direction",
            active_heads=["numerology"],
            head_findings={"numerology": _numerology_head()},
            universal_signals=_no_universal_signals(),
        )
        self.assertFalse(
            any("completion and release" in s for s in result["universal_signals_surfaced"])
        )

    def test_clash_year_surfaces_with_reason(self):
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="career",
            active_heads=["chinese"],
            head_findings={"chinese": _chinese_head()},
            universal_signals=_universal_signals(
                clash_year=True,
                clash_reason="Rabbit clashes with Rooster year.",
            ),
        )
        clash_signals = [s for s in result["universal_signals_surfaced"] if "clash" in s.lower()]
        self.assertTrue(len(clash_signals) >= 1)
        self.assertIn("Rabbit", clash_signals[0])

    def test_clash_year_absent_when_false(self):
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="career",
            active_heads=["numerology"],
            head_findings={"numerology": _numerology_head()},
            universal_signals=_no_universal_signals(),
        )
        self.assertFalse(
            any("clash" in s.lower() for s in result["universal_signals_surfaced"])
        )

    def test_ben_ming_nian_surfaces_when_true(self):
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="general",
            active_heads=["chinese"],
            head_findings={"chinese": _chinese_head()},
            universal_signals=_universal_signals(ben_ming_nian=True),
        )
        self.assertTrue(
            any("return year" in s for s in result["universal_signals_surfaced"]),
            f"ben_ming_nian not surfaced: {result['universal_signals_surfaced']}",
        )

    def test_ben_ming_nian_absent_when_false(self):
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="general",
            active_heads=["chinese"],
            head_findings={"chinese": _chinese_head()},
            universal_signals=_no_universal_signals(),
        )
        self.assertFalse(
            any("return year" in s for s in result["universal_signals_surfaced"])
        )

    def test_all_three_universal_signals_together(self):
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="general",
            active_heads=["numerology"],
            head_findings={"numerology": _numerology_head()},
            universal_signals=_universal_signals(
                personal_year_9=True,
                clash_year=True,
                clash_reason="Dog clashes with Dragon year.",
                ben_ming_nian=True,
                ben_ming_nian_reason="Your return year amplifies both challenge and growth.",
            ),
        )
        self.assertEqual(len(result["universal_signals_surfaced"]), 3)


# ── Composite tendency window ─────────────────────────────────────────────────

class TestCompositeTendencyWindow(TestCase):
    """Composite window correctly averaged from non-null head windows."""

    def test_two_head_average(self):
        """numerology (4–12) + iching (2–8) → avg_min=3, avg_max=10."""
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="career",
            active_heads=["numerology", "iching"],
            head_findings={
                "numerology": _numerology_head(min_weeks=4, max_weeks=12),
                "iching": _iching_head(min_weeks=2, max_weeks=8),
            },
            universal_signals=_no_universal_signals(),
        )
        tw = result["tendency_window"]
        self.assertIsNotNone(tw)
        self.assertEqual(tw["composite_min_weeks"], 3)
        self.assertEqual(tw["composite_max_weeks"], 10)

    def test_single_head_window_unchanged(self):
        """Single head with window (6–18) → composite equals that window."""
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="direction",
            active_heads=["iching"],
            head_findings={"iching": _iching_head(min_weeks=6, max_weeks=18)},
            universal_signals=_no_universal_signals(),
        )
        tw = result["tendency_window"]
        self.assertIsNotNone(tw)
        self.assertEqual(tw["composite_min_weeks"], 6)
        self.assertEqual(tw["composite_max_weeks"], 18)

    def test_three_head_average(self):
        """Three heads: numerology(4,12), iching(2,8), chinese(3,9) → avg=(3,10)."""
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="career",
            active_heads=["numerology", "iching", "chinese"],
            head_findings={
                "numerology": _numerology_head(min_weeks=4, max_weeks=12),
                "iching": _iching_head(min_weeks=2, max_weeks=8),
                "chinese": _chinese_head(min_weeks=3, max_weeks=9),
            },
            universal_signals=_no_universal_signals(),
        )
        tw = result["tendency_window"]
        self.assertIsNotNone(tw)
        # avg_min = round((4+2+3)/3) = round(3.0) = 3
        # avg_max = round((12+8+9)/3) = round(9.67) = 10
        self.assertEqual(tw["composite_min_weeks"], 3)
        self.assertEqual(tw["composite_max_weeks"], 10)

    def test_philosophy_null_window_excluded_from_average(self):
        """Philosophy (null window) + numerology (4–12) → composite from numerology only."""
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="direction",
            active_heads=["philosophy", "numerology"],
            head_findings={
                "philosophy": _philosophy_head(),  # tendency_window_weeks = null
                "numerology": _numerology_head(min_weeks=4, max_weeks=12),
            },
            universal_signals=_no_universal_signals(),
        )
        tw = result["tendency_window"]
        self.assertIsNotNone(tw)
        self.assertEqual(tw["composite_min_weeks"], 4)
        self.assertEqual(tw["composite_max_weeks"], 12)
        self.assertNotIn("philosophy", tw["contributing_heads"])
        self.assertIn("numerology", tw["contributing_heads"])

    def test_all_null_windows_returns_null_tendency(self):
        """All active heads have null windows → tendency_window is null."""
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="direction",
            active_heads=["philosophy"],
            head_findings={"philosophy": _philosophy_head()},
            universal_signals=_no_universal_signals(),
        )
        self.assertIsNone(result["tendency_window"])

    def test_tendency_window_expressed_as_plain_language(self):
        """expressed_as contains 'weeks' and the numeric range."""
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="career",
            active_heads=["numerology", "iching"],
            head_findings={
                "numerology": _numerology_head(min_weeks=4, max_weeks=12),
                "iching": _iching_head(min_weeks=2, max_weeks=8),
            },
            universal_signals=_no_universal_signals(),
        )
        tw = result["tendency_window"]
        self.assertIn("weeks", tw["expressed_as"])
        self.assertIn("3", tw["expressed_as"])
        self.assertIn("10", tw["expressed_as"])

    def test_contributing_heads_listed(self):
        """contributing_heads lists the heads that provided windows."""
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="career",
            active_heads=["numerology", "iching"],
            head_findings={
                "numerology": _numerology_head(),
                "iching": _iching_head(),
            },
            universal_signals=_no_universal_signals(),
        )
        tw = result["tendency_window"]
        self.assertIn("numerology", tw["contributing_heads"])
        self.assertIn("iching", tw["contributing_heads"])

    def test_rounding_applied(self):
        """Average is rounded to nearest integer."""
        layer = _engine()
        # iching min=1, numerology min=2 → avg=1.5 → rounds to 2
        result = layer.synthesise(
            query="query",
            query_category="career",
            active_heads=["numerology", "iching"],
            head_findings={
                "numerology": _numerology_head(min_weeks=2, max_weeks=11),
                "iching": _iching_head(min_weeks=1, max_weeks=8),
            },
            universal_signals=_no_universal_signals(),
        )
        tw = result["tendency_window"]
        self.assertIsInstance(tw["composite_min_weeks"], int)
        self.assertIsInstance(tw["composite_max_weeks"], int)


# ── Null head findings ────────────────────────────────────────────────────────

class TestNullHeadFindings(TestCase):
    """Null head findings excluded gracefully with synthesis_notes."""

    def test_null_head_excluded_from_working_set(self):
        """Null head findings are excluded; remaining heads still contribute."""
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="career",
            active_heads=["numerology", "iching"],
            head_findings={
                "numerology": None,
                "iching": _iching_head(),
            },
            universal_signals=_no_universal_signals(),
        )
        # Summary should be present — iching contributed
        self.assertIsNotNone(result["summary"])

    def test_excluded_head_noted_in_synthesis_notes(self):
        """Excluded null head is noted in synthesis_notes."""
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="career",
            active_heads=["numerology", "iching"],
            head_findings={
                "numerology": None,
                "iching": _iching_head(),
            },
            universal_signals=_no_universal_signals(),
        )
        self.assertIsNotNone(result["synthesis_notes"])
        self.assertIn("numerology", result["synthesis_notes"].lower())

    def test_multiple_null_heads_all_noted(self):
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="career",
            active_heads=["numerology", "philosophy", "iching"],
            head_findings={
                "numerology": None,
                "philosophy": None,
                "iching": _iching_head(),
            },
            universal_signals=_no_universal_signals(),
        )
        self.assertIsNotNone(result["synthesis_notes"])
        notes_lower = result["synthesis_notes"].lower()
        self.assertIn("numerology", notes_lower)
        self.assertIn("philosophy", notes_lower)


# ── Empty working set ─────────────────────────────────────────────────────────

class TestEmptyWorkingSet(TestCase):
    """When all head findings are null, summary is null and synthesis_notes set."""

    def test_all_null_findings_returns_null_summary(self):
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="general",
            active_heads=["numerology", "iching"],
            head_findings={"numerology": None, "iching": None},
            universal_signals=_no_universal_signals(),
        )
        self.assertIsNone(result["summary"])

    def test_empty_working_set_synthesis_notes_set(self):
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="general",
            active_heads=["numerology"],
            head_findings={"numerology": None},
            universal_signals=_no_universal_signals(),
        )
        self.assertEqual(result["synthesis_notes"], "No findings available.")

    def test_empty_working_set_tendency_window_null(self):
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="general",
            active_heads=["numerology"],
            head_findings={"numerology": None},
            universal_signals=_no_universal_signals(),
        )
        self.assertIsNone(result["tendency_window"])

    def test_empty_active_heads_list(self):
        layer = _engine()
        result = layer.synthesise(
            query="query",
            query_category="general",
            active_heads=[],
            head_findings={},
            universal_signals=_no_universal_signals(),
        )
        self.assertIsNone(result["summary"])
        self.assertEqual(result["synthesis_notes"], "No findings available.")


# ── Output shape ──────────────────────────────────────────────────────────────

class TestOutputShape(TestCase):
    """Output shape matches S-11 contract exactly."""

    def setUp(self):
        self.layer = _engine()
        self.result = self.layer.synthesise(
            query="Should I change my career now?",
            query_category="career",
            active_heads=["numerology", "iching"],
            head_findings={
                "numerology": _numerology_head(),
                "iching": _iching_head(),
            },
            universal_signals=_no_universal_signals(),
        )

    def test_summary_is_string(self):
        self.assertIsInstance(self.result["summary"], str)
        self.assertTrue(len(self.result["summary"]) > 0)

    def test_paragraph_count_is_1_or_2(self):
        self.assertIn(self.result["paragraph_count"], [1, 2])

    def test_word_count_is_positive_integer(self):
        self.assertIsInstance(self.result["word_count"], int)
        self.assertGreater(self.result["word_count"], 0)

    def test_tendency_window_shape(self):
        tw = self.result["tendency_window"]
        self.assertIsNotNone(tw)
        self.assertIn("composite_min_weeks", tw)
        self.assertIn("composite_max_weeks", tw)
        self.assertIn("contributing_heads", tw)
        self.assertIn("expressed_as", tw)

    def test_convergence_signals_is_list(self):
        self.assertIsInstance(self.result["convergence_signals"], list)

    def test_divergence_signals_is_list(self):
        self.assertIsInstance(self.result["divergence_signals"], list)

    def test_universal_signals_surfaced_is_list(self):
        self.assertIsInstance(self.result["universal_signals_surfaced"], list)

    def test_synthesis_notes_is_string_or_none(self):
        notes = self.result["synthesis_notes"]
        self.assertTrue(notes is None or isinstance(notes, str))

    def test_all_required_keys_present(self):
        required = {
            "summary", "paragraph_count", "word_count",
            "tendency_window", "convergence_signals",
            "divergence_signals", "universal_signals_surfaced",
            "synthesis_notes",
        }
        for key in required:
            self.assertIn(key, self.result, f"Missing key: {key}")


# ── Self-review checklist ─────────────────────────────────────────────────────

class TestSelfReview(TestCase):
    """Self-review checklist enforced on LLM output."""

    def test_journey_word_replaced_in_summary(self):
        """Word 'journey' in LLM output is replaced by self-review."""
        layer = SynthesisLayer(
            anthropic_client=_mock_client(
                "This career journey requires patience and deliberate action over the next few weeks."
            )
        )
        result = layer.synthesise(
            query="Career question",
            query_category="career",
            active_heads=["iching"],
            head_findings={"iching": _iching_head()},
            universal_signals=_no_universal_signals(),
        )
        import re
        self.assertFalse(
            re.search(r"\bjourney\b", result["summary"], re.IGNORECASE),
            f"Word 'journey' found in summary: {result['summary']}",
        )

    def test_journey_replacement_noted_in_synthesis_notes(self):
        """Replacing 'journey' is noted in synthesis_notes."""
        layer = SynthesisLayer(
            anthropic_client=_mock_client(
                "This career journey is one of discovery over the next four to ten weeks."
            )
        )
        result = layer.synthesise(
            query="query",
            query_category="career",
            active_heads=["iching"],
            head_findings={"iching": _iching_head()},
            universal_signals=_no_universal_signals(),
        )
        self.assertIsNotNone(result["synthesis_notes"])
        self.assertIn("journey", result["synthesis_notes"].lower())

    def test_forbidden_opener_flagged_in_synthesis_notes(self):
        """Summary opening with 'Based on your birth chart' is flagged."""
        layer = SynthesisLayer(
            anthropic_client=_mock_client(
                "Based on your birth chart, the combined readings suggest caution "
                "over the next four to ten weeks of consolidation."
            )
        )
        result = layer.synthesise(
            query="query",
            query_category="career",
            active_heads=["iching"],
            head_findings={"iching": _iching_head()},
            universal_signals=_no_universal_signals(),
        )
        self.assertIsNotNone(result["synthesis_notes"])
        self.assertIn("forbidden", result["synthesis_notes"].lower())

    def test_word_count_ceiling_enforced(self):
        """Summary exceeding 1000 words is truncated to sentence boundary."""
        # Build a summary that exceeds 1000 words
        long_sentence = "The combined readings indicate a clear pattern of consolidation and patience. "
        long_summary = long_sentence * 100  # 1100 words (11 × 100)
        layer = SynthesisLayer(anthropic_client=_mock_client(long_summary))
        result = layer.synthesise(
            query="query",
            query_category="career",
            active_heads=["iching"],
            head_findings={"iching": _iching_head()},
            universal_signals=_no_universal_signals(),
        )
        self.assertLessEqual(
            result["word_count"], 1000,
            f"Word count {result['word_count']} exceeds ceiling of 1000",
        )

    def test_word_count_ceiling_noted_in_synthesis_notes(self):
        """Truncation due to word count ceiling is noted in synthesis_notes."""
        long_sentence = "The combined readings indicate a clear pattern of consolidation and patience. "
        long_summary = long_sentence * 100  # 11 words × 100 = 1100 words > 1000 ceiling
        layer = SynthesisLayer(anthropic_client=_mock_client(long_summary))
        result = layer.synthesise(
            query="query",
            query_category="career",
            active_heads=["iching"],
            head_findings={"iching": _iching_head()},
            universal_signals=_no_universal_signals(),
        )
        self.assertIsNotNone(result["synthesis_notes"])
        self.assertIn("truncat", result["synthesis_notes"].lower())

    def test_bullet_list_flagged_in_synthesis_notes(self):
        """Summary with bullet list structure is flagged in synthesis_notes."""
        bullet_summary = (
            "The readings reveal the following patterns over the next four to ten weeks:\n"
            "- Numerology signals a year of transition\n"
            "- I Ching counsels forward movement\n"
            "These signals suggest decisive action."
        )
        layer = SynthesisLayer(anthropic_client=_mock_client(bullet_summary))
        result = layer.synthesise(
            query="query",
            query_category="career",
            active_heads=["iching"],
            head_findings={"iching": _iching_head()},
            universal_signals=_no_universal_signals(),
        )
        self.assertIsNotNone(result["synthesis_notes"])
        self.assertIn("bullet", result["synthesis_notes"].lower())

    def test_missing_week_reference_flagged_when_window_present(self):
        """If tendency window is present but 'week' not in summary, flag it."""
        no_week_summary = (
            "The combined readings point to a period of consolidation and "
            "deliberate action, with multiple systems in alignment on the "
            "need for patience before advancing."
        )
        layer = SynthesisLayer(anthropic_client=_mock_client(no_week_summary))
        result = layer.synthesise(
            query="query",
            query_category="career",
            active_heads=["iching"],
            head_findings={"iching": _iching_head()},
            universal_signals=_no_universal_signals(),
        )
        self.assertIsNotNone(result["synthesis_notes"])
        self.assertIn("week", result["synthesis_notes"].lower())

    def test_clean_summary_has_no_synthesis_notes(self):
        """A clean summary that passes all checks has no synthesis_notes."""
        clean_summary = (
            "Multiple systems converge on a period of consolidation over "
            "roughly three to ten weeks, with the I Ching counselling dispersal "
            "of rigid structures before new ground is broken. "
            "The numerological pattern for this year supports measured action "
            "rather than forcing outcomes, making this window best used for "
            "clarifying the decision rather than acting on it prematurely."
        )
        layer = SynthesisLayer(anthropic_client=_mock_client(clean_summary))
        result = layer.synthesise(
            query="Should I change my career?",
            query_category="career",
            active_heads=["numerology", "iching"],
            head_findings={
                "numerology": _numerology_head(),
                "iching": _iching_head(),
            },
            universal_signals=_no_universal_signals(),
        )
        self.assertIsNone(
            result["synthesis_notes"],
            f"Expected no synthesis_notes for clean summary, got: {result['synthesis_notes']}",
        )


# ── LLM client injection ──────────────────────────────────────────────────────

class TestClientInjection(TestCase):
    """Injected mock client is used; no real API call is made."""

    def test_client_called_once(self):
        mock_client = _mock_client()
        layer = SynthesisLayer(anthropic_client=mock_client)
        layer.synthesise(
            query="query",
            query_category="career",
            active_heads=["iching"],
            head_findings={"iching": _iching_head()},
            universal_signals=_no_universal_signals(),
        )
        mock_client.messages.create.assert_called_once()

    def test_system_prompt_passed_to_api(self):
        mock_client = _mock_client()
        layer = SynthesisLayer(anthropic_client=mock_client)
        layer.synthesise(
            query="query",
            query_category="career",
            active_heads=["iching"],
            head_findings={"iching": _iching_head()},
            universal_signals=_no_universal_signals(),
        )
        kwargs = mock_client.messages.create.call_args[1]
        self.assertEqual(kwargs["system"], _SYSTEM_PROMPT)

    def test_query_in_user_message(self):
        mock_client = _mock_client()
        layer = SynthesisLayer(anthropic_client=mock_client)
        layer.synthesise(
            query="Should I leave my job this year?",
            query_category="career",
            active_heads=["iching"],
            head_findings={"iching": _iching_head()},
            universal_signals=_no_universal_signals(),
        )
        kwargs = mock_client.messages.create.call_args[1]
        user_content = kwargs["messages"][0]["content"]
        self.assertIn("Should I leave my job this year?", user_content)

    def test_universal_signals_in_user_message(self):
        mock_client = _mock_client()
        layer = SynthesisLayer(anthropic_client=mock_client)
        layer.synthesise(
            query="query",
            query_category="career",
            active_heads=["iching"],
            head_findings={"iching": _iching_head()},
            universal_signals=_universal_signals(personal_year_9=True),
        )
        kwargs = mock_client.messages.create.call_args[1]
        user_content = kwargs["messages"][0]["content"]
        self.assertIn("UNIVERSAL SIGNALS", user_content)

    def test_no_llm_call_when_working_set_empty(self):
        """When working set is empty, LLM must not be called."""
        mock_client = _mock_client()
        layer = SynthesisLayer(anthropic_client=mock_client)
        layer.synthesise(
            query="query",
            query_category="career",
            active_heads=["numerology"],
            head_findings={"numerology": None},
            universal_signals=_no_universal_signals(),
        )
        mock_client.messages.create.assert_not_called()


# ── System prompt content ─────────────────────────────────────────────────────

class TestSystemPromptContent(TestCase):
    """System prompt contains required anti-platitude and anti-optimism rules."""

    def test_anti_platitude_rules_present(self):
        for phrase in [
            "Everything happens for a reason",
            "Trust the process",
        ]:
            self.assertIn(phrase, _SYSTEM_PROMPT, f"Missing anti-platitude: '{phrase}'")

    def test_anti_optimism_rules_present(self):
        for phrase in [
            "Things will improve",
            "hidden opportunity",
        ]:
            self.assertIn(phrase, _SYSTEM_PROMPT, f"Missing anti-optimism: '{phrase}'")

    def test_no_journey_rule_present(self):
        self.assertIn("journey", _SYSTEM_PROMPT.lower())

    def test_prose_only_rule_present(self):
        self.assertIn("prose", _SYSTEM_PROMPT.lower())

    def test_no_disclaimer_rule_present(self):
        self.assertIn("disclaimer", _SYSTEM_PROMPT.lower())

    def test_convergence_spine_rule_present(self):
        self.assertIn("structural spine", _SYSTEM_PROMPT)

    def test_divergence_honest_rule_present(self):
        self.assertIn("honestly", _SYSTEM_PROMPT)


# ── Truncate utility ──────────────────────────────────────────────────────────

class TestTruncateUtility(TestCase):
    """_truncate_at_sentence_boundary helper."""

    def test_short_text_unchanged(self):
        text = "The sky is blue. The moon is bright."
        result = _truncate_at_sentence_boundary(text, 100)
        self.assertEqual(result, text)

    def test_truncates_at_sentence_boundary(self):
        text = "First sentence here. Second sentence follows. Third one ends."
        result = _truncate_at_sentence_boundary(text, 4)  # "First sentence here." = 3 words
        # 3 words fit; "Second" would push to 4+3=7 > 4
        self.assertEqual(result, "First sentence here.")

    def test_result_ends_with_sentence(self):
        sentences = ["Word " * 10 + "end one.", "Word " * 10 + "end two.", "Word " * 10 + "end three."]
        text = " ".join(sentences)
        result = _truncate_at_sentence_boundary(text, 15)
        self.assertTrue(result.endswith("."))
