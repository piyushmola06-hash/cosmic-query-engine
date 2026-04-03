"""
Tests for S-13 — Explainability Trail Renderer.

Done condition verified:
  - Trail renders only on explicit request
  - All active heads in fixed order
  - Unavailable sections always shown with reason
  - Null trails skipped with note
"""

from django.test import TestCase

from synthesis.trail import TrailRenderer


# ── Helpers ───────────────────────────────────────────────────────────────────

def _renderer() -> TrailRenderer:
    return TrailRenderer()


def _section(title: str, content: str, available: bool = True,
             unavailable_reason: str | None = None) -> dict:
    s = {"title": title, "content": content, "available": available}
    if not available:
        s["unavailable_reason"] = unavailable_reason
    return s


def _numerology_trail() -> dict:
    return {
        "label": "Numerology",
        "sections": [
            _section("Life Path", "Life path 7, derived from digit sum."),
            _section("Personal Year / Month", "Personal year 5, month 3."),
            _section("Expression Number", "Expression number 3 (Pythagorean)."),
        ],
    }


def _iching_trail() -> dict:
    return {
        "label": "I Ching",
        "sections": [
            _section("Hexagram Cast", "Seed hash → hexagram 59: Dispersion."),
            _section("Query Application", "Dispersion counsels dissolving rigidity."),
        ],
    }


def _chinese_trail() -> dict:
    return {
        "label": "Chinese Astrology",
        "sections": [
            _section("Zodiac Animal", "Rabbit, Water element."),
            _section("Current Year", "Year of the Dragon — mild clash."),
        ],
    }


def _vedic_trail() -> dict:
    return {
        "label": "Vedic Astrology",
        "sections": [
            _section("Moon Sign (Rashi)", "Scorpio (Vrischika)."),
            _section("Current Dasha", "Venus Mahadasha, Saturn Antardasha."),
        ],
    }


def _western_trail() -> dict:
    return {
        "label": "Western Astrology",
        "sections": [
            _section("Sun Sign", "Pisces."),
            _section("Outer Planet Transits", "Saturn conjunct natal Moon."),
        ],
    }


def _philosophy_trail() -> dict:
    return {
        "label": "Philosophy",
        "sections": [
            _section("Stoicism", "Focus only on the decision, not the outcome."),
            _section("Vedanta", "The witness-self observes without attachment."),
        ],
    }


# ── Gate: user_requested = false ─────────────────────────────────────────────

class TestUserRequestedGate(TestCase):
    """Trail is never rendered when user_requested = False."""

    def test_not_requested_rendered_false(self):
        result = _renderer().render(
            active_heads=["numerology"],
            head_trails={"numerology": _numerology_trail()},
            user_requested=False,
        )
        self.assertFalse(result["rendered"])

    def test_not_requested_trail_null(self):
        result = _renderer().render(
            active_heads=["numerology", "iching"],
            head_trails={
                "numerology": _numerology_trail(),
                "iching": _iching_trail(),
            },
            user_requested=False,
        )
        self.assertIsNone(result["trail"])

    def test_not_requested_even_with_all_heads_active(self):
        result = _renderer().render(
            active_heads=["vedic", "western", "numerology", "chinese", "philosophy", "iching"],
            head_trails={
                "vedic": _vedic_trail(),
                "western": _western_trail(),
                "numerology": _numerology_trail(),
                "chinese": _chinese_trail(),
                "philosophy": _philosophy_trail(),
                "iching": _iching_trail(),
            },
            user_requested=False,
        )
        self.assertFalse(result["rendered"])
        self.assertIsNone(result["trail"])


# ── Rendered when requested ───────────────────────────────────────────────────

class TestRenderedWhenRequested(TestCase):
    """Trail is rendered when user_requested = True."""

    def test_requested_rendered_true(self):
        result = _renderer().render(
            active_heads=["numerology"],
            head_trails={"numerology": _numerology_trail()},
            user_requested=True,
        )
        self.assertTrue(result["rendered"])

    def test_requested_trail_is_list(self):
        result = _renderer().render(
            active_heads=["numerology"],
            head_trails={"numerology": _numerology_trail()},
            user_requested=True,
        )
        self.assertIsInstance(result["trail"], list)

    def test_requested_trail_contains_active_head(self):
        result = _renderer().render(
            active_heads=["numerology"],
            head_trails={"numerology": _numerology_trail()},
            user_requested=True,
        )
        labels = [e["head_label"] for e in result["trail"]]
        self.assertIn("Numerology", labels)

    def test_requested_trail_sections_populated(self):
        result = _renderer().render(
            active_heads=["numerology"],
            head_trails={"numerology": _numerology_trail()},
            user_requested=True,
        )
        entry = result["trail"][0]
        self.assertIsInstance(entry["sections"], list)
        self.assertGreater(len(entry["sections"]), 0)


# ── Fixed head order ──────────────────────────────────────────────────────────

class TestFixedHeadOrder(TestCase):
    """Head display order is always fixed regardless of active_heads ordering."""

    def test_order_numerology_before_iching(self):
        """Numerology (order 3) always before I Ching (order 6)."""
        result = _renderer().render(
            active_heads=["iching", "numerology"],  # deliberately reversed
            head_trails={
                "iching": _iching_trail(),
                "numerology": _numerology_trail(),
            },
            user_requested=True,
        )
        orders = [e["head_order"] for e in result["trail"]]
        self.assertEqual(orders, sorted(orders))

    def test_order_vedic_first_iching_last(self):
        """Vedic (1) before Western (2) before Numerology (3) before I Ching (6)."""
        result = _renderer().render(
            active_heads=["iching", "numerology", "vedic", "western"],
            head_trails={
                "vedic": _vedic_trail(),
                "western": _western_trail(),
                "numerology": _numerology_trail(),
                "iching": _iching_trail(),
            },
            user_requested=True,
        )
        orders = [e["head_order"] for e in result["trail"]]
        self.assertEqual(orders, sorted(orders))

    def test_order_all_six_heads(self):
        """All six heads in canonical order 1–6."""
        result = _renderer().render(
            active_heads=["philosophy", "chinese", "iching", "numerology", "western", "vedic"],
            head_trails={
                "vedic": _vedic_trail(),
                "western": _western_trail(),
                "numerology": _numerology_trail(),
                "chinese": _chinese_trail(),
                "philosophy": _philosophy_trail(),
                "iching": _iching_trail(),
            },
            user_requested=True,
        )
        orders = [e["head_order"] for e in result["trail"]]
        self.assertEqual(orders, [1, 2, 3, 4, 5, 6])

    def test_head_order_value_matches_position(self):
        """head_order on each entry reflects canonical position, not list index."""
        result = _renderer().render(
            active_heads=["numerology", "iching"],
            head_trails={
                "numerology": _numerology_trail(),
                "iching": _iching_trail(),
            },
            user_requested=True,
        )
        by_label = {e["head_label"]: e["head_order"] for e in result["trail"]}
        self.assertEqual(by_label["Numerology"], 3)
        self.assertEqual(by_label["I Ching"], 6)


# ── All active heads appear ───────────────────────────────────────────────────

class TestAllActiveHeadsAppear(TestCase):
    """Every active head appears in trail output, none skipped silently."""

    def test_two_heads_both_present(self):
        result = _renderer().render(
            active_heads=["numerology", "chinese"],
            head_trails={
                "numerology": _numerology_trail(),
                "chinese": _chinese_trail(),
            },
            user_requested=True,
        )
        labels = [e["head_label"] for e in result["trail"]]
        self.assertIn("Numerology", labels)
        self.assertIn("Chinese Astrology", labels)

    def test_five_heads_all_present(self):
        result = _renderer().render(
            active_heads=["vedic", "western", "numerology", "chinese", "philosophy"],
            head_trails={
                "vedic": _vedic_trail(),
                "western": _western_trail(),
                "numerology": _numerology_trail(),
                "chinese": _chinese_trail(),
                "philosophy": _philosophy_trail(),
            },
            user_requested=True,
        )
        self.assertEqual(len(result["trail"]), 5)

    def test_inactive_head_not_in_trail(self):
        """A head not in active_heads must not appear in trail."""
        result = _renderer().render(
            active_heads=["numerology"],
            head_trails={
                "numerology": _numerology_trail(),
                "iching": _iching_trail(),  # present in dict but not active
            },
            user_requested=True,
        )
        labels = [e["head_label"] for e in result["trail"]]
        self.assertNotIn("I Ching", labels)


# ── I Ching appears only when active ─────────────────────────────────────────

class TestIChingActiveControl(TestCase):

    def test_iching_active_appears_in_trail(self):
        result = _renderer().render(
            active_heads=["numerology", "iching"],
            head_trails={
                "numerology": _numerology_trail(),
                "iching": _iching_trail(),
            },
            user_requested=True,
        )
        labels = [e["head_label"] for e in result["trail"]]
        self.assertIn("I Ching", labels)

    def test_iching_not_active_absent_from_trail(self):
        result = _renderer().render(
            active_heads=["numerology"],
            head_trails={
                "numerology": _numerology_trail(),
            },
            user_requested=True,
        )
        labels = [e["head_label"] for e in result["trail"]]
        self.assertNotIn("I Ching", labels)


# ── Null trail handling ───────────────────────────────────────────────────────

class TestNullTrailHandling(TestCase):
    """Null head trail → included with label and unavailability note."""

    def test_null_trail_head_still_appears(self):
        result = _renderer().render(
            active_heads=["numerology"],
            head_trails={"numerology": None},
            user_requested=True,
        )
        labels = [e["head_label"] for e in result["trail"]]
        self.assertIn("Numerology", labels)

    def test_null_trail_section_available_false(self):
        result = _renderer().render(
            active_heads=["numerology"],
            head_trails={"numerology": None},
            user_requested=True,
        )
        entry = result["trail"][0]
        self.assertTrue(
            any(not s["available"] for s in entry["sections"]),
            "Expected at least one unavailable section for null trail",
        )

    def test_null_trail_unavailable_reason_set(self):
        result = _renderer().render(
            active_heads=["numerology"],
            head_trails={"numerology": None},
            user_requested=True,
        )
        entry = result["trail"][0]
        unavail = [s for s in entry["sections"] if not s["available"]]
        self.assertTrue(len(unavail) > 0)
        self.assertIsNotNone(unavail[0]["unavailable_reason"])
        self.assertTrue(unavail[0]["unavailable_reason"].strip())

    def test_null_trail_does_not_crash(self):
        """Multiple heads, one null — renders without exception."""
        result = _renderer().render(
            active_heads=["numerology", "chinese"],
            head_trails={
                "numerology": None,
                "chinese": _chinese_trail(),
            },
            user_requested=True,
        )
        self.assertTrue(result["rendered"])
        self.assertEqual(len(result["trail"]), 2)


# ── Unavailable sections ──────────────────────────────────────────────────────

class TestUnavailableSections(TestCase):
    """Unavailable sections are shown with reason — never hidden."""

    def test_unavailable_section_present_in_output(self):
        trail = {
            "label": "Vedic Astrology",
            "sections": [
                _section("Moon Sign", "Scorpio."),
                {
                    "title": "House Placements",
                    "content": "",
                    "available": False,
                    "unavailable_reason": "Birth time not provided.",
                },
            ],
        }
        result = _renderer().render(
            active_heads=["vedic"],
            head_trails={"vedic": trail},
            user_requested=True,
        )
        sections = result["trail"][0]["sections"]
        unavail = [s for s in sections if not s["available"]]
        self.assertTrue(len(unavail) >= 1, "Unavailable section missing from output")

    def test_unavailable_section_reason_preserved(self):
        trail = {
            "label": "Vedic Astrology",
            "sections": [
                {
                    "title": "Ascendant",
                    "content": "",
                    "available": False,
                    "unavailable_reason": "Birth time not provided.",
                },
            ],
        }
        result = _renderer().render(
            active_heads=["vedic"],
            head_trails={"vedic": trail},
            user_requested=True,
        )
        section = result["trail"][0]["sections"][0]
        self.assertEqual(section["unavailable_reason"], "Birth time not provided.")

    def test_available_sections_not_suppressed(self):
        trail = {
            "label": "Numerology",
            "sections": [
                _section("Life Path", "Life path 7."),
                {
                    "title": "Expression Number",
                    "content": "",
                    "available": False,
                    "unavailable_reason": "Name missing.",
                },
            ],
        }
        result = _renderer().render(
            active_heads=["numerology"],
            head_trails={"numerology": trail},
            user_requested=True,
        )
        sections = result["trail"][0]["sections"]
        avail = [s for s in sections if s["available"]]
        self.assertTrue(len(avail) >= 1)


# ── Section shape ─────────────────────────────────────────────────────────────

class TestSectionShape(TestCase):
    """Every section has required keys: title, content, available, unavailable_reason."""

    def test_section_has_required_keys(self):
        result = _renderer().render(
            active_heads=["numerology"],
            head_trails={"numerology": _numerology_trail()},
            user_requested=True,
        )
        for entry in result["trail"]:
            for section in entry["sections"]:
                self.assertIn("title", section)
                self.assertIn("content", section)
                self.assertIn("available", section)
                self.assertIn("unavailable_reason", section)

    def test_available_section_unavailable_reason_null(self):
        result = _renderer().render(
            active_heads=["numerology"],
            head_trails={"numerology": _numerology_trail()},
            user_requested=True,
        )
        for entry in result["trail"]:
            for section in entry["sections"]:
                if section["available"]:
                    self.assertIsNone(section["unavailable_reason"])


# ── Domain language preserved ─────────────────────────────────────────────────

class TestDomainLanguagePreserved(TestCase):
    """Section content is not normalised — domain-specific language preserved."""

    def test_vedic_content_unchanged(self):
        trail = {
            "label": "Vedic Astrology",
            "sections": [
                _section("Moon Sign (Rashi)", "Vrischika rashi — Scorpio."),
            ],
        }
        result = _renderer().render(
            active_heads=["vedic"],
            head_trails={"vedic": trail},
            user_requested=True,
        )
        content = result["trail"][0]["sections"][0]["content"]
        self.assertEqual(content, "Vrischika rashi — Scorpio.")

    def test_iching_content_unchanged(self):
        trail = {
            "label": "I Ching",
            "sections": [
                _section("Hexagram Cast", "Hexagram 59: Huàn — Dispersion (渙)."),
            ],
        }
        result = _renderer().render(
            active_heads=["iching"],
            head_trails={"iching": trail},
            user_requested=True,
        )
        content = result["trail"][0]["sections"][0]["content"]
        self.assertEqual(content, "Hexagram 59: Huàn — Dispersion (渙).")


# ── Malformed trail handling ──────────────────────────────────────────────────

class TestMalformedTrail(TestCase):
    """Malformed trail objects are handled gracefully — never crash."""

    def test_non_dict_trail_handled(self):
        result = _renderer().render(
            active_heads=["numerology"],
            head_trails={"numerology": "not a dict"},
            user_requested=True,
        )
        self.assertTrue(result["rendered"])
        self.assertEqual(len(result["trail"]), 1)
        entry = result["trail"][0]
        self.assertFalse(entry["sections"][0]["available"])

    def test_trail_missing_sections_key_handled(self):
        result = _renderer().render(
            active_heads=["numerology"],
            head_trails={"numerology": {"label": "Numerology"}},  # no sections
            user_requested=True,
        )
        self.assertTrue(result["rendered"])
        entry = result["trail"][0]
        self.assertFalse(entry["sections"][0]["available"])

    def test_trail_empty_sections_list_handled(self):
        result = _renderer().render(
            active_heads=["numerology"],
            head_trails={"numerology": {"label": "Numerology", "sections": []}},
            user_requested=True,
        )
        self.assertTrue(result["rendered"])
        entry = result["trail"][0]
        self.assertFalse(entry["sections"][0]["available"])


# ── Output shape ──────────────────────────────────────────────────────────────

class TestOutputShape(TestCase):
    """Output always contains rendered and trail keys."""

    def test_output_has_rendered_key(self):
        result = _renderer().render(
            active_heads=["numerology"],
            head_trails={"numerology": _numerology_trail()},
            user_requested=True,
        )
        self.assertIn("rendered", result)

    def test_output_has_trail_key(self):
        result = _renderer().render(
            active_heads=["numerology"],
            head_trails={"numerology": _numerology_trail()},
            user_requested=False,
        )
        self.assertIn("trail", result)

    def test_trail_entry_has_required_keys(self):
        result = _renderer().render(
            active_heads=["numerology"],
            head_trails={"numerology": _numerology_trail()},
            user_requested=True,
        )
        entry = result["trail"][0]
        self.assertIn("head_label", entry)
        self.assertIn("head_order", entry)
        self.assertIn("sections", entry)

    def test_empty_active_heads_trail_empty_list(self):
        result = _renderer().render(
            active_heads=[],
            head_trails={},
            user_requested=True,
        )
        self.assertTrue(result["rendered"])
        self.assertEqual(result["trail"], [])
