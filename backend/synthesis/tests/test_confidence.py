"""
Tests for S-12 — Confidence Note Generator.

Done condition verified:
  - Note produced if and only if at least one head has confidence_flag = true
  - Always one consolidated statement
  - Severity always set when note_required = true
  - Tone never apologises or reassures
  - Note never appears when all heads at full fidelity
"""

import logging

from django.test import TestCase

from synthesis.confidence import ConfidenceNoteGenerator


# ── Helpers ───────────────────────────────────────────────────────────────────

def _gen() -> ConfidenceNoteGenerator:
    return ConfidenceNoteGenerator()


def _moon(certain: bool = True, transition: bool = False) -> dict:
    return {"moon_sign_certain": certain, "transition_occurred": transition}


def _conf(flag: bool = False, reason: str | None = None) -> dict:
    return {"flag": flag, "reason": reason}


def _all_clear(active_heads: list[str] | None = None) -> dict:
    """Build a full head_confidence dict with all flags False."""
    heads = active_heads or ["vedic", "western", "numerology", "chinese", "philosophy"]
    return {h: _conf(False) for h in heads}


# ── No flags ──────────────────────────────────────────────────────────────────

class TestNoFlags(TestCase):
    """When no heads are flagged and moon is certain → no note."""

    def test_no_flags_note_required_false(self):
        result = _gen().generate(
            active_heads=["numerology", "iching"],
            head_confidence={"numerology": _conf(False), "iching": _conf(False)},
            moon=_moon(certain=True),
        )
        self.assertFalse(result["note_required"])

    def test_no_flags_note_is_null(self):
        result = _gen().generate(
            active_heads=["numerology"],
            head_confidence={"numerology": _conf(False)},
            moon=_moon(certain=True),
        )
        self.assertIsNone(result["note"])

    def test_no_flags_affected_heads_empty(self):
        result = _gen().generate(
            active_heads=["numerology", "chinese"],
            head_confidence=_all_clear(["numerology", "chinese"]),
            moon=_moon(certain=True),
        )
        self.assertEqual(result["affected_heads"], [])

    def test_no_flags_severity_null(self):
        result = _gen().generate(
            active_heads=["numerology"],
            head_confidence={"numerology": _conf(False)},
            moon=_moon(certain=True),
        )
        self.assertIsNone(result["severity"])

    def test_missing_head_confidence_entry_treated_as_no_flag(self):
        """Missing entry for an active head → treated as flag=False per spec."""
        result = _gen().generate(
            active_heads=["numerology", "chinese"],
            head_confidence={
                "numerology": _conf(False),
                # "chinese" missing entirely
            },
            moon=_moon(certain=True),
        )
        self.assertFalse(result["note_required"])

    def test_empty_active_heads_no_note(self):
        result = _gen().generate(
            active_heads=[],
            head_confidence={},
            moon=_moon(certain=True),
        )
        self.assertFalse(result["note_required"])
        self.assertIsNone(result["note"])


# ── Moon uncertainty only ─────────────────────────────────────────────────────

class TestMoonUncertainty(TestCase):
    """Moon sign uncertain (transition on birth date, time unknown) → minor."""

    def test_moon_uncertainty_only_requires_note(self):
        result = _gen().generate(
            active_heads=["numerology"],
            head_confidence={"numerology": _conf(False)},
            moon=_moon(certain=False, transition=True),
        )
        self.assertTrue(result["note_required"])

    def test_moon_uncertainty_only_severity_minor(self):
        result = _gen().generate(
            active_heads=["numerology"],
            head_confidence={"numerology": _conf(False)},
            moon=_moon(certain=False, transition=True),
        )
        self.assertEqual(result["severity"], "minor")

    def test_moon_uncertainty_note_contains_majority_day(self):
        result = _gen().generate(
            active_heads=["numerology"],
            head_confidence={"numerology": _conf(False)},
            moon=_moon(certain=False, transition=True),
        )
        self.assertIn("majority-day", result["note"].lower())

    def test_moon_certain_no_note_triggered(self):
        """moon_sign_certain=True even with transition → no moon note."""
        result = _gen().generate(
            active_heads=["numerology"],
            head_confidence={"numerology": _conf(False)},
            moon=_moon(certain=True, transition=True),
        )
        self.assertFalse(result["note_required"])

    def test_moon_transition_false_no_note_triggered(self):
        """transition_occurred=False → no moon uncertainty note."""
        result = _gen().generate(
            active_heads=["numerology"],
            head_confidence={"numerology": _conf(False)},
            moon=_moon(certain=False, transition=False),
        )
        self.assertFalse(result["note_required"])


# ── Severity levels ───────────────────────────────────────────────────────────

class TestSeverityLevels(TestCase):
    """Severity rules from spec applied correctly."""

    def test_one_head_flagged_minor(self):
        """1 head flagged → minor."""
        result = _gen().generate(
            active_heads=["vedic"],
            head_confidence={"vedic": _conf(True, "approximate birth time provided")},
            moon=_moon(certain=True),
        )
        self.assertEqual(result["severity"], "minor")

    def test_two_heads_flagged_moderate(self):
        """2 heads flagged → moderate."""
        result = _gen().generate(
            active_heads=["vedic", "western"],
            head_confidence={
                "vedic": _conf(True, "approximate birth time"),
                "western": _conf(True, "approximate birth time"),
            },
            moon=_moon(certain=True),
        )
        self.assertEqual(result["severity"], "moderate")

    def test_three_heads_flagged_moderate(self):
        """3 heads flagged → moderate."""
        result = _gen().generate(
            active_heads=["vedic", "western", "numerology"],
            head_confidence={
                "vedic": _conf(True, "no birth time"),
                "western": _conf(True, "no birth time"),
                "numerology": _conf(True, "no birth time"),
            },
            moon=_moon(certain=True),
        )
        self.assertEqual(result["severity"], "moderate")

    def test_four_heads_flagged_significant(self):
        """4+ heads flagged → significant."""
        result = _gen().generate(
            active_heads=["vedic", "western", "numerology", "chinese"],
            head_confidence={
                "vedic": _conf(True, "no birth time"),
                "western": _conf(True, "no birth time"),
                "numerology": _conf(True),
                "chinese": _conf(True),
            },
            moon=_moon(certain=True),
        )
        self.assertEqual(result["severity"], "significant")

    def test_five_heads_flagged_significant(self):
        """5 non-philosophy heads flagged → significant."""
        result = _gen().generate(
            active_heads=["vedic", "western", "numerology", "chinese", "iching"],
            head_confidence={
                "vedic": _conf(True),
                "western": _conf(True),
                "numerology": _conf(True),
                "chinese": _conf(True),
                "iching": _conf(True),
            },
            moon=_moon(certain=True),
        )
        self.assertEqual(result["severity"], "significant")

    def test_calculation_failure_significant(self):
        """Calculation failure in reason → significant regardless of head count."""
        result = _gen().generate(
            active_heads=["vedic"],
            head_confidence={
                "vedic": _conf(True, "calculation failure: ephemeris unavailable"),
            },
            moon=_moon(certain=True),
        )
        self.assertEqual(result["severity"], "significant")

    def test_failed_keyword_triggers_significant(self):
        """'failed' keyword in reason → significant."""
        result = _gen().generate(
            active_heads=["western"],
            head_confidence={
                "western": _conf(True, "transit calculation failed"),
            },
            moon=_moon(certain=True),
        )
        self.assertEqual(result["severity"], "significant")


# ── Note content rules ────────────────────────────────────────────────────────

class TestNoteContent(TestCase):
    """Note is consolidated prose. Never a list. No apology. No reassurance."""

    def test_note_is_string_not_list(self):
        result = _gen().generate(
            active_heads=["vedic", "western"],
            head_confidence={
                "vedic": _conf(True, "birth time approximate"),
                "western": _conf(True, "birth time approximate"),
            },
            moon=_moon(certain=True),
        )
        self.assertIsInstance(result["note"], str)

    def test_note_has_no_bullet_characters(self):
        result = _gen().generate(
            active_heads=["vedic", "western", "numerology"],
            head_confidence={
                "vedic": _conf(True, "no birth time"),
                "western": _conf(True, "no birth time"),
                "numerology": _conf(True, "no birth time"),
            },
            moon=_moon(certain=True),
        )
        note = result["note"]
        self.assertNotIn("•", note)
        self.assertNotIn("\n-", note)
        self.assertNotIn("\n*", note)

    def test_note_does_not_contain_sorry(self):
        result = _gen().generate(
            active_heads=["vedic"],
            head_confidence={"vedic": _conf(True, "birth time not provided")},
            moon=_moon(certain=True),
        )
        self.assertNotIn("sorry", result["note"].lower())

    def test_note_does_not_contain_dont_worry(self):
        result = _gen().generate(
            active_heads=["western"],
            head_confidence={"western": _conf(True, "approximate time used")},
            moon=_moon(certain=True),
        )
        self.assertNotIn("don't worry", result["note"].lower())
        self.assertNotIn("dont worry", result["note"].lower())

    def test_note_does_not_contain_doesnt_affect(self):
        result = _gen().generate(
            active_heads=["chinese"],
            head_confidence={"chinese": _conf(True, "approximate birth time")},
            moon=_moon(certain=True),
        )
        self.assertNotIn("doesn't affect", result["note"].lower())
        self.assertNotIn("does not affect", result["note"].lower())

    def test_note_names_affected_head(self):
        result = _gen().generate(
            active_heads=["vedic"],
            head_confidence={"vedic": _conf(True, "birth time approximate")},
            moon=_moon(certain=True),
        )
        self.assertIn("vedic", result["note"].lower())

    def test_note_contains_reason(self):
        result = _gen().generate(
            active_heads=["numerology"],
            head_confidence={
                "numerology": _conf(True, "name characters not mappable")
            },
            moon=_moon(certain=True),
        )
        self.assertIn("name characters not mappable", result["note"].lower())

    def test_all_heads_flagged_single_note(self):
        """All active heads flagged → single consolidated note, not six."""
        result = _gen().generate(
            active_heads=["vedic", "western", "numerology", "chinese"],
            head_confidence={
                "vedic": _conf(True, "no birth time"),
                "western": _conf(True, "no birth time"),
                "numerology": _conf(True),
                "chinese": _conf(True),
            },
            moon=_moon(certain=True),
        )
        note = result["note"]
        # Must be a single string (not a list) that consolidates all heads.
        self.assertIsInstance(note, str)
        # Should not repeat "operating at reduced fidelity" six times.
        self.assertEqual(note.count("operating at reduced fidelity"), 1)

    def test_note_mentions_reduced_fidelity(self):
        result = _gen().generate(
            active_heads=["vedic"],
            head_confidence={"vedic": _conf(True, "birth time not provided")},
            moon=_moon(certain=True),
        )
        self.assertIn("reduced fidelity", result["note"].lower())


# ── Philosophy exclusion ──────────────────────────────────────────────────────

class TestPhilosophyExclusion(TestCase):
    """Philosophy confidence_flag=True → excluded from note, anomaly logged."""

    def test_philosophy_flag_true_excluded_from_affected_heads(self):
        result = _gen().generate(
            active_heads=["philosophy"],
            head_confidence={"philosophy": _conf(True, "some anomaly")},
            moon=_moon(certain=True),
        )
        self.assertNotIn("philosophy", result["affected_heads"])

    def test_philosophy_flag_true_no_note_if_only_flagged_head(self):
        """If philosophy is the only flagged head → note_required = False."""
        result = _gen().generate(
            active_heads=["philosophy"],
            head_confidence={"philosophy": _conf(True, "some anomaly")},
            moon=_moon(certain=True),
        )
        self.assertFalse(result["note_required"])
        self.assertIsNone(result["note"])

    def test_philosophy_flag_logged_as_anomaly(self):
        """Philosophy flag=True should log a warning."""
        with self.assertLogs("synthesis.confidence", level="WARNING") as cm:
            _gen().generate(
                active_heads=["philosophy"],
                head_confidence={"philosophy": _conf(True, "anomaly")},
                moon=_moon(certain=True),
            )
        self.assertTrue(
            any("philosophy" in line.lower() and "anomal" in line.lower() for line in cm.output),
            f"Expected anomaly warning, got: {cm.output}",
        )

    def test_philosophy_false_other_head_true_note_produced(self):
        """Philosophy False + another head True → note produced for other head."""
        result = _gen().generate(
            active_heads=["philosophy", "vedic"],
            head_confidence={
                "philosophy": _conf(False),
                "vedic": _conf(True, "approximate time"),
            },
            moon=_moon(certain=True),
        )
        self.assertTrue(result["note_required"])
        self.assertIn("vedic", result["affected_heads"])
        self.assertNotIn("philosophy", result["affected_heads"])


# ── I Ching not active ────────────────────────────────────────────────────────

class TestIChingNotActive(TestCase):
    """I Ching not in active_heads → excluded from scan entirely."""

    def test_iching_not_active_not_scanned(self):
        """I Ching has flag=True in head_confidence but is not active → ignored."""
        result = _gen().generate(
            active_heads=["numerology"],  # iching not active
            head_confidence={
                "numerology": _conf(False),
                "iching": _conf(True, "should be ignored"),
            },
            moon=_moon(certain=True),
        )
        self.assertFalse(result["note_required"])
        self.assertNotIn("iching", result["affected_heads"])

    def test_iching_active_scanned_normally(self):
        """I Ching active + flag=True → included normally."""
        result = _gen().generate(
            active_heads=["iching"],
            head_confidence={"iching": _conf(True, "low confidence seed")},
            moon=_moon(certain=True),
        )
        self.assertTrue(result["note_required"])
        self.assertIn("iching", result["affected_heads"])


# ── Output shape ──────────────────────────────────────────────────────────────

class TestOutputShape(TestCase):
    """Output dict always has all required keys."""

    def _check_shape(self, result: dict) -> None:
        self.assertIn("note_required", result)
        self.assertIn("note", result)
        self.assertIn("affected_heads", result)
        self.assertIn("severity", result)
        self.assertIsInstance(result["affected_heads"], list)

    def test_shape_no_flags(self):
        result = _gen().generate(
            active_heads=["numerology"],
            head_confidence={"numerology": _conf(False)},
            moon=_moon(),
        )
        self._check_shape(result)

    def test_shape_with_flag(self):
        result = _gen().generate(
            active_heads=["vedic"],
            head_confidence={"vedic": _conf(True, "reason")},
            moon=_moon(),
        )
        self._check_shape(result)

    def test_severity_set_when_note_required(self):
        result = _gen().generate(
            active_heads=["vedic"],
            head_confidence={"vedic": _conf(True, "approximate time")},
            moon=_moon(),
        )
        self.assertTrue(result["note_required"])
        self.assertIsNotNone(result["severity"])
        self.assertIn(result["severity"], ("minor", "moderate", "significant"))

    def test_note_is_none_when_not_required(self):
        result = _gen().generate(
            active_heads=["numerology"],
            head_confidence={"numerology": _conf(False)},
            moon=_moon(certain=True),
        )
        self.assertFalse(result["note_required"])
        self.assertIsNone(result["note"])
        self.assertIsNone(result["severity"])


# ── Combined flag and moon uncertainty ───────────────────────────────────────

class TestCombinedSignals(TestCase):
    """Head flag + moon uncertainty together → both named in note."""

    def test_head_flag_and_moon_uncertainty_both_in_note(self):
        result = _gen().generate(
            active_heads=["vedic"],
            head_confidence={"vedic": _conf(True, "no birth time")},
            moon=_moon(certain=False, transition=True),
        )
        self.assertTrue(result["note_required"])
        note = result["note"].lower()
        self.assertIn("vedic", note)
        self.assertIn("majority-day", note)
