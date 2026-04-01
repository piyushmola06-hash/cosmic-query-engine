"""
Tests for S-09 — Philosophy Head Engine.

All tests mock the Anthropic client entirely — no real API calls are made.

Covers:
  - Output shape matches S-09 contract exactly
  - tendency_window_weeks is always null
  - confidence_flag is always false
  - query_theme is always populated
  - All three frameworks always produce all four fields
  - convergence field present (may be null)
  - divergence field present (may be null)
  - query_relevant_findings always populated
  - Distress signal in query — practical_guidance emphasises present-moment action
  - Third-party query — query_theme notes reframing
  - Empty query — applies frameworks to seeking guidance
  - Life context provided — included in prompt construction
  - Anti-platitude prompt rules present in system prompt
"""

import json
from unittest.mock import MagicMock, patch

from django.test import TestCase

from heads.philosophy.services import (
    PhilosophyHeadEngine,
    _SYSTEM_PROMPT,
    _DISTRESS_SIGNALS,
)


# ── Mock LLM response builders ────────────────────────────────────────────────

def _make_framework(
    core_principle: str = "Core principle",
    applied_finding: str = "Applied to this specific situation",
    key_distinction: str = "Key distinction relevant here",
    practical_guidance: str = "Concrete action: do this specific thing",
) -> dict:
    return {
        "core_principle": core_principle,
        "applied_finding": applied_finding,
        "key_distinction": key_distinction,
        "practical_guidance": practical_guidance,
    }


def _make_llm_payload(
    query_theme: str = "The user's concern about career change",
    query_category: str = "career",
    convergence: str | None = "All three frameworks agree on present-moment focus",
    divergence: str | None = "Stoicism emphasises action; Vedanta emphasises non-identification",
    query_relevant_findings: list | None = None,
    stoicism_overrides: dict | None = None,
    vedanta_overrides: dict | None = None,
    karma_overrides: dict | None = None,
) -> dict:
    return {
        "query_theme": query_theme,
        "query_category": query_category,
        "frameworks": {
            "stoicism": _make_framework(**(stoicism_overrides or {})),
            "vedanta": _make_framework(**(vedanta_overrides or {})),
            "karma": _make_framework(**(karma_overrides or {})),
        },
        "convergence": convergence,
        "divergence": divergence,
        "query_relevant_findings": query_relevant_findings if query_relevant_findings is not None
            else ["Most important finding for this query", "Second finding"],
    }


def _make_mock_client(payload: dict) -> MagicMock:
    """Return a mock Anthropic client whose messages.create() returns payload."""
    mock_content = MagicMock()
    mock_content.text = json.dumps(payload)

    mock_response = MagicMock()
    mock_response.content = [mock_content]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    return mock_client


# ── Test cases ────────────────────────────────────────────────────────────────

class TestOutputShape(TestCase):
    """Output shape matches S-09 contract exactly."""

    def setUp(self):
        payload = _make_llm_payload()
        self.client = _make_mock_client(payload)
        self.engine = PhilosophyHeadEngine(anthropic_client=self.client)
        self.result = self.engine.compute("Should I change careers?")

    def test_head_is_philosophy(self):
        self.assertEqual(self.result["head"], "philosophy")

    def test_available_findings_is_list(self):
        self.assertIsInstance(self.result["available_findings"], list)
        self.assertTrue(len(self.result["available_findings"]) > 0)

    def test_unavailable_findings_is_list(self):
        self.assertIsInstance(self.result["unavailable_findings"], list)

    def test_findings_top_level_keys(self):
        findings = self.result["findings"]
        required_keys = {
            "query_theme", "query_category", "frameworks",
            "convergence", "divergence",
            "query_relevant_findings", "tendency_window_weeks",
        }
        for key in required_keys:
            self.assertIn(key, findings, f"Missing findings key: {key}")

    def test_explainability_trail_shape(self):
        trail = self.result["explainability_trail"]
        self.assertIn("label", trail)
        self.assertEqual(trail["label"], "Philosophy")
        self.assertIn("sections", trail)
        self.assertIsInstance(trail["sections"], list)

    def test_trail_sections_have_required_fields(self):
        for section in self.result["explainability_trail"]["sections"]:
            self.assertIn("title", section)
            self.assertIn("content", section)
            self.assertIn("available", section)


class TestInvariantFields(TestCase):
    """tendency_window_weeks always null; confidence_flag always false."""

    def _run(self, query, **kwargs):
        payload = _make_llm_payload(**kwargs)
        engine = PhilosophyHeadEngine(anthropic_client=_make_mock_client(payload))
        return engine.compute(query)

    def test_tendency_window_always_null(self):
        result = self._run("What career path should I take?")
        self.assertIsNone(result["findings"]["tendency_window_weeks"])

    def test_tendency_window_null_for_relationship_query(self):
        result = self._run("Should I end my marriage?",
                           query_category="relationships")
        self.assertIsNone(result["findings"]["tendency_window_weeks"])

    def test_confidence_flag_always_false(self):
        result = self._run("Am I on the right path?")
        self.assertFalse(result["confidence_flag"])

    def test_confidence_flag_false_even_for_distress(self):
        result = self._run("I feel hopeless about everything")
        self.assertFalse(result["confidence_flag"])

    def test_confidence_reason_always_none(self):
        result = self._run("Any question")
        self.assertIsNone(result["confidence_reason"])


class TestQueryTheme(TestCase):
    """query_theme is always populated."""

    def test_query_theme_populated_normal(self):
        payload = _make_llm_payload(query_theme="The user seeks clarity on a career decision")
        engine = PhilosophyHeadEngine(anthropic_client=_make_mock_client(payload))
        result = engine.compute("Should I change jobs?")
        self.assertTrue(result["findings"]["query_theme"])
        self.assertIsInstance(result["findings"]["query_theme"], str)

    def test_query_theme_populated_empty_query(self):
        payload = _make_llm_payload(
            query_theme="The user is seeking guidance without a specific question",
            query_category="general",
        )
        engine = PhilosophyHeadEngine(anthropic_client=_make_mock_client(payload))
        result = engine.compute("")
        self.assertTrue(result["findings"]["query_theme"])


class TestFrameworks(TestCase):
    """All three frameworks always produce all four required fields."""

    FRAMEWORK_NAMES = ("stoicism", "vedanta", "karma")
    FRAMEWORK_FIELDS = ("core_principle", "applied_finding", "key_distinction", "practical_guidance")

    def setUp(self):
        payload = _make_llm_payload()
        self.engine = PhilosophyHeadEngine(anthropic_client=_make_mock_client(payload))
        self.result = self.engine.compute("What should I do about my relationship?")

    def test_all_three_frameworks_present(self):
        fw = self.result["findings"]["frameworks"]
        for name in self.FRAMEWORK_NAMES:
            self.assertIn(name, fw, f"Missing framework: {name}")

    def test_all_four_fields_per_framework(self):
        fw = self.result["findings"]["frameworks"]
        for name in self.FRAMEWORK_NAMES:
            for field in self.FRAMEWORK_FIELDS:
                self.assertIn(field, fw[name], f"Framework {name} missing field: {field}")

    def test_all_framework_fields_are_strings(self):
        fw = self.result["findings"]["frameworks"]
        for name in self.FRAMEWORK_NAMES:
            for field in self.FRAMEWORK_FIELDS:
                self.assertIsInstance(
                    fw[name][field], str,
                    f"Framework {name}.{field} is not a string",
                )


class TestConvergenceDivergence(TestCase):
    """convergence and divergence fields are present (may be null)."""

    def test_convergence_present_when_set(self):
        payload = _make_llm_payload(convergence="All agree on grounded action")
        engine = PhilosophyHeadEngine(anthropic_client=_make_mock_client(payload))
        result = engine.compute("How do I handle grief?")
        self.assertIn("convergence", result["findings"])
        self.assertEqual(result["findings"]["convergence"], "All agree on grounded action")

    def test_convergence_null_when_none(self):
        payload = _make_llm_payload(convergence=None)
        engine = PhilosophyHeadEngine(anthropic_client=_make_mock_client(payload))
        result = engine.compute("How do I handle grief?")
        self.assertIsNone(result["findings"]["convergence"])

    def test_divergence_present_when_set(self):
        payload = _make_llm_payload(divergence="Stoicism and Vedanta differ here")
        engine = PhilosophyHeadEngine(anthropic_client=_make_mock_client(payload))
        result = engine.compute("Is ambition virtuous?")
        self.assertIn("divergence", result["findings"])
        self.assertEqual(result["findings"]["divergence"], "Stoicism and Vedanta differ here")

    def test_divergence_null_when_none(self):
        payload = _make_llm_payload(divergence=None)
        engine = PhilosophyHeadEngine(anthropic_client=_make_mock_client(payload))
        result = engine.compute("Is ambition virtuous?")
        self.assertIsNone(result["findings"]["divergence"])

    def test_both_null_is_valid(self):
        payload = _make_llm_payload(convergence=None, divergence=None)
        engine = PhilosophyHeadEngine(anthropic_client=_make_mock_client(payload))
        result = engine.compute("What is enough?")
        self.assertIsNone(result["findings"]["convergence"])
        self.assertIsNone(result["findings"]["divergence"])


class TestQueryRelevantFindings(TestCase):
    """query_relevant_findings always populated."""

    def test_populated_for_normal_query(self):
        payload = _make_llm_payload(
            query_relevant_findings=["Finding one specific to this query", "Finding two"]
        )
        engine = PhilosophyHeadEngine(anthropic_client=_make_mock_client(payload))
        result = engine.compute("Should I move abroad for work?")
        self.assertIsInstance(result["findings"]["query_relevant_findings"], list)
        self.assertTrue(len(result["findings"]["query_relevant_findings"]) > 0)

    def test_populated_for_distress_query(self):
        payload = _make_llm_payload(
            query_relevant_findings=["Immediate grounding step", "Witness-self recognition"]
        )
        engine = PhilosophyHeadEngine(anthropic_client=_make_mock_client(payload))
        result = engine.compute("I feel desperate and hopeless")
        self.assertTrue(len(result["findings"]["query_relevant_findings"]) > 0)


class TestDistressSignalHandling(TestCase):
    """
    Distress signal in query — the user message sent to the LLM must include
    the distress guidance instruction; practical_guidance in response emphasises
    present-moment action.
    """

    def test_distress_instruction_added_to_user_message(self):
        """The user-turn message must include distress signal instruction."""
        payload = _make_llm_payload(
            stoicism_overrides={
                "core_principle": "Dichotomy of control",
                "applied_finding": "Right now, with this specific crisis, the only action up to you is the next single step",
                "key_distinction": "Between the crisis itself and your response to it",
                "practical_guidance": "Identify the single next concrete action available in the next hour",
            },
            vedanta_overrides={
                "core_principle": "The witness-self is untouched",
                "applied_finding": "The part of you observing this distress is not destroyed by it",
                "key_distinction": "Between the experiencing self and the witnessing self",
                "practical_guidance": "Sit for two minutes and observe your distress without narrating it",
            },
            karma_overrides={
                "core_principle": "Agami karma — present choices",
                "applied_finding": "Agami karma is the most powerful force available in this moment",
                "key_distinction": "Between prarabdha (what is ripening) and agami (what you can shape now)",
                "practical_guidance": "Choose one grounded present-moment action in the next ten minutes",
            },
        )
        mock_client = _make_mock_client(payload)
        engine = PhilosophyHeadEngine(anthropic_client=mock_client)
        engine.compute("I feel desperate and I cannot cope")

        call_kwargs = mock_client.messages.create.call_args
        messages = call_kwargs[1]["messages"] if call_kwargs[1] else call_kwargs[0][2]
        user_content = messages[0]["content"]

        self.assertIn("DISTRESS SIGNAL DETECTED", user_content)

    def test_distress_result_has_present_moment_guidance(self):
        """When distress is detected, practical_guidance should reference now/present/immediate."""
        distress_guidance = "Take one grounded action in the present moment — right now"
        payload = _make_llm_payload(
            stoicism_overrides={
                "core_principle": "Dichotomy of control",
                "applied_finding": "What is up to you in this crisis",
                "key_distinction": "Crisis vs response",
                "practical_guidance": distress_guidance,
            }
        )
        engine = PhilosophyHeadEngine(anthropic_client=_make_mock_client(payload))
        result = engine.compute("I feel desperate and I cannot cope")

        stoicism_guidance = result["findings"]["frameworks"]["stoicism"]["practical_guidance"]
        lower = stoicism_guidance.lower()
        self.assertTrue(
            any(word in lower for word in ("now", "present", "moment", "immediate", "right now")),
            f"Expected present-moment language in: {stoicism_guidance}",
        )

    def test_multiple_distress_keywords_trigger_detection(self):
        """Each distress keyword individually triggers the detection flag."""
        payload = _make_llm_payload()
        mock_client = _make_mock_client(payload)
        engine = PhilosophyHeadEngine(anthropic_client=mock_client)

        distress_queries = [
            "I feel hopeless",
            "I am so anxious",
            "I am overwhelmed by this",
            "I feel desperate",
        ]
        for dq in distress_queries:
            mock_client.reset_mock()
            mock_client.messages.create.return_value = _make_mock_client(payload).messages.create.return_value
            # Re-set response
            mock_content = MagicMock()
            mock_content.text = json.dumps(payload)
            mock_response = MagicMock()
            mock_response.content = [mock_content]
            mock_client.messages.create.return_value = mock_response

            engine.compute(dq)
            call_kwargs = mock_client.messages.create.call_args
            messages = call_kwargs[1]["messages"] if call_kwargs[1] else call_kwargs[0][2]
            user_content = messages[0]["content"]
            self.assertIn(
                "DISTRESS SIGNAL DETECTED", user_content,
                f"Distress not detected for query: {dq}",
            )


class TestThirdPartyQuery(TestCase):
    """Third-party query — query_theme must note the reframing."""

    def test_third_party_reframe_noted_in_query_theme(self):
        reframe_theme = (
            "Reframed from third-party query: the user's own relationship "
            "to their partner's career indecision"
        )
        payload = _make_llm_payload(query_theme=reframe_theme)
        engine = PhilosophyHeadEngine(anthropic_client=_make_mock_client(payload))
        result = engine.compute("What should my partner do about their career?")

        query_theme = result["findings"]["query_theme"]
        # The LLM (mocked) returns a reframe-noting theme — we verify it passes through
        self.assertEqual(query_theme, reframe_theme)
        self.assertIn("reframe", query_theme.lower())

    def test_third_party_prompt_does_not_suppress_distress(self):
        """A third-party query must still pass distress through if signals present."""
        payload = _make_llm_payload()
        mock_client = _make_mock_client(payload)
        engine = PhilosophyHeadEngine(anthropic_client=mock_client)
        engine.compute("My friend feels hopeless and desperate — what should they do?")

        call_kwargs = mock_client.messages.create.call_args
        messages = call_kwargs[1]["messages"] if call_kwargs[1] else call_kwargs[0][2]
        user_content = messages[0]["content"]
        self.assertIn("DISTRESS SIGNAL DETECTED", user_content)


class TestEmptyQuery(TestCase):
    """Empty query — service applies frameworks to seeking guidance itself."""

    def test_empty_string_is_handled(self):
        payload = _make_llm_payload(
            query_theme="The act of seeking guidance itself",
            query_category="general",
        )
        engine = PhilosophyHeadEngine(anthropic_client=_make_mock_client(payload))
        result = engine.compute("")
        self.assertEqual(result["head"], "philosophy")
        self.assertFalse(result["confidence_flag"])
        self.assertIsNone(result["findings"]["tendency_window_weeks"])

    def test_none_query_is_handled(self):
        payload = _make_llm_payload(
            query_theme="The act of seeking guidance itself",
            query_category="general",
        )
        engine = PhilosophyHeadEngine(anthropic_client=_make_mock_client(payload))
        result = engine.compute(None)
        self.assertEqual(result["head"], "philosophy")

    def test_empty_query_user_message_notes_seeking_guidance(self):
        """When query is empty, the user-turn message must reference seeking guidance."""
        payload = _make_llm_payload()
        mock_client = _make_mock_client(payload)
        engine = PhilosophyHeadEngine(anthropic_client=mock_client)
        engine.compute("")

        call_kwargs = mock_client.messages.create.call_args
        messages = call_kwargs[1]["messages"] if call_kwargs[1] else call_kwargs[0][2]
        user_content = messages[0]["content"]
        self.assertIn("seeking guidance", user_content.lower())


class TestLifeContextIncluded(TestCase):
    """Life context provided — it is included in the prompt to the LLM."""

    def test_life_context_career_in_prompt(self):
        payload = _make_llm_payload()
        mock_client = _make_mock_client(payload)
        engine = PhilosophyHeadEngine(anthropic_client=mock_client)
        engine.compute(
            query="Should I quit my job?",
            life_context={
                "career": "I have been at the same company for 10 years and feel stagnant",
                "relationships": None,
                "health": None,
                "other": None,
            },
        )

        call_kwargs = mock_client.messages.create.call_args
        messages = call_kwargs[1]["messages"] if call_kwargs[1] else call_kwargs[0][2]
        user_content = messages[0]["content"]
        self.assertIn("stagnant", user_content)

    def test_all_life_context_fields_included(self):
        payload = _make_llm_payload()
        mock_client = _make_mock_client(payload)
        engine = PhilosophyHeadEngine(anthropic_client=mock_client)
        engine.compute(
            query="What is my direction?",
            life_context={
                "career": "Struggling with career direction",
                "relationships": "Recently divorced",
                "health": "Managing chronic fatigue",
                "other": "Considering monastic retreat",
            },
        )

        call_kwargs = mock_client.messages.create.call_args
        messages = call_kwargs[1]["messages"] if call_kwargs[1] else call_kwargs[0][2]
        user_content = messages[0]["content"]
        self.assertIn("career", user_content)
        self.assertIn("Recently divorced", user_content)
        self.assertIn("chronic fatigue", user_content)
        self.assertIn("monastic", user_content)

    def test_null_life_context_fields_excluded(self):
        """Fields that are None should not appear in the prompt."""
        payload = _make_llm_payload()
        mock_client = _make_mock_client(payload)
        engine = PhilosophyHeadEngine(anthropic_client=mock_client)
        engine.compute(
            query="What is my direction?",
            life_context={
                "career": "Working in finance",
                "relationships": None,
                "health": None,
                "other": None,
            },
        )

        call_kwargs = mock_client.messages.create.call_args
        messages = call_kwargs[1]["messages"] if call_kwargs[1] else call_kwargs[0][2]
        user_content = messages[0]["content"]
        self.assertIn("finance", user_content)
        # None fields should not add blank lines labelled with their key
        self.assertNotIn("relationships: None", user_content)
        self.assertNotIn("health: None", user_content)

    def test_no_life_context_still_works(self):
        payload = _make_llm_payload()
        engine = PhilosophyHeadEngine(anthropic_client=_make_mock_client(payload))
        result = engine.compute("Am I on the right path?", life_context=None)
        self.assertEqual(result["head"], "philosophy")


class TestSystemPromptAntiPlatitudeRules(TestCase):
    """Anti-platitude rules must be present in the system prompt."""

    def test_forbidden_outputs_listed(self):
        """The system prompt must name at least the core forbidden platitudes."""
        forbidden = [
            "Everything happens for a reason",
            "Trust the process",
            "Focus on what you can control",
            "Let go of what does not serve you",
        ]
        for phrase in forbidden:
            self.assertIn(
                phrase, _SYSTEM_PROMPT,
                f"Anti-platitude rule missing from system prompt: '{phrase}'",
            )

    def test_platitude_test_instruction_present(self):
        """The copy-paste test instruction must be in the system prompt."""
        # The phrase may span a line break — test the two halves separately
        self.assertIn("copy-pasted into a reading for a completely", _SYSTEM_PROMPT)
        self.assertIn("different user with a completely different query", _SYSTEM_PROMPT)

    def test_framework_definitions_present(self):
        """Core framework terms must appear in system prompt."""
        for term in ("dichotomy of control", "Brahman", "agami", "prarabdha", "sanchita"):
            self.assertIn(term, _SYSTEM_PROMPT, f"Framework term missing: '{term}'")

    def test_distress_handling_rules_in_prompt(self):
        """Distress handling instructions must be in the system prompt."""
        self.assertIn("Distress signals", _SYSTEM_PROMPT)
        self.assertIn("agami karma", _SYSTEM_PROMPT)
        self.assertIn("witness-self", _SYSTEM_PROMPT)

    def test_third_party_rule_in_prompt(self):
        """Third-party query reframe instruction must be in system prompt."""
        self.assertIn("Third-party query", _SYSTEM_PROMPT)


class TestQueryCategory(TestCase):
    """query_category is always one of the valid enum values."""

    VALID_CATEGORIES = {
        "career", "relationships", "finances", "health",
        "travel", "direction", "general",
    }

    def test_valid_category_passes_through(self):
        for cat in self.VALID_CATEGORIES:
            with self.subTest(category=cat):
                payload = _make_llm_payload(query_category=cat)
                engine = PhilosophyHeadEngine(anthropic_client=_make_mock_client(payload))
                result = engine.compute("Some query")
                self.assertEqual(result["findings"]["query_category"], cat)

    def test_unexpected_category_passes_through_as_is(self):
        """Unknown category returned by LLM passes through without crashing."""
        payload = _make_llm_payload(query_category="spiritual")
        engine = PhilosophyHeadEngine(anthropic_client=_make_mock_client(payload))
        result = engine.compute("What is enlightenment?")
        self.assertEqual(result["findings"]["query_category"], "spiritual")


class TestClientInjection(TestCase):
    """Injected mock client is used; no real API call is made."""

    def test_injected_client_is_called(self):
        payload = _make_llm_payload()
        mock_client = _make_mock_client(payload)
        engine = PhilosophyHeadEngine(anthropic_client=mock_client)
        engine.compute("Test query")
        mock_client.messages.create.assert_called_once()

    def test_model_passed_in_api_call(self):
        payload = _make_llm_payload()
        mock_client = _make_mock_client(payload)
        engine = PhilosophyHeadEngine(anthropic_client=mock_client)
        engine.compute("Test query")

        call_kwargs = mock_client.messages.create.call_args[1]
        self.assertIn("model", call_kwargs)
        self.assertIsInstance(call_kwargs["model"], str)
        self.assertTrue(len(call_kwargs["model"]) > 0)

    def test_system_prompt_passed_in_api_call(self):
        payload = _make_llm_payload()
        mock_client = _make_mock_client(payload)
        engine = PhilosophyHeadEngine(anthropic_client=mock_client)
        engine.compute("Test query")

        call_kwargs = mock_client.messages.create.call_args[1]
        self.assertIn("system", call_kwargs)
        self.assertEqual(call_kwargs["system"], _SYSTEM_PROMPT)
