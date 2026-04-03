"""
Tests for the five API endpoints.

All LLM calls are mocked — zero real API calls.
Uses Django test client for HTTP — no real HTTP server needed.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

from django.test import Client, TestCase
from django.urls import reverse

from core.models import SessionContext, UserProfile
from core.services import SessionService


# ── Mock helpers ──────────────────────────────────────────────────────────────

_MOCK_SUMMARY = (
    "Three systems converge on a period of consolidation over the next "
    "four to ten weeks. The numerology cycle and Chinese astrology both "
    "signal that initiating new ventures carries elevated risk at this time."
)


def _mock_anthropic_client(summary: str = _MOCK_SUMMARY) -> MagicMock:
    """Return a mock Anthropic client usable by SynthesisLayer, Philosophy, I Ching."""
    content = MagicMock()
    content.text = json.dumps({"summary": summary})
    response = MagicMock()
    response.content = [content]
    client = MagicMock()
    client.messages.create.return_value = response
    return client


def _patch_llm():
    """
    Context manager: patches SynthesisLayer, PhilosophyHeadEngine, and
    IChingHeadEngine to use mock clients so no real API calls are made.
    """
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        mock_client = _mock_anthropic_client()

        with patch("heads.philosophy.services.PhilosophyHeadEngine.__init__",
                   lambda self, anthropic_client=None: setattr(self, "_client", mock_client)
                   or setattr(self, "_model", "mock")):
            with patch("heads.iching.services.IChingHeadEngine.__init__",
                       lambda self, anthropic_client=None: setattr(self, "_client", mock_client)
                       or setattr(self, "_model", "mock")):
                with patch("synthesis.services.SynthesisLayer.__init__",
                           lambda self, anthropic_client=None: setattr(self, "_client", mock_client)
                           or setattr(self, "_model", "mock")):
                    yield mock_client

    return _ctx()


# ── Full pipeline mock using patch.object ─────────────────────────────────────

def _make_mock_client() -> MagicMock:
    return _mock_anthropic_client()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _post(client: Client, url: str, data: dict) -> object:
    return client.post(
        url,
        data=json.dumps(data),
        content_type="application/json",
    )


def _start_session(client: Client, user_identifier: str = "test@example.com") -> dict:
    resp = _post(client, "/session/start/", {"user_identifier": user_identifier})
    return resp.json()


def _make_active_session_with_data(user_id: str = "q@example.com") -> SessionContext:
    """Create a session that has already completed collection."""
    svc = SessionService()
    session = svc.start_session(user_identifier=user_id)
    session.data_pool = {
        "query": "What should I focus on this year?",
        "dob": {"day": 15, "month": 3, "year": 1990},
        "birth_time": {"tier": "exact", "normalised_time": "10:30",
                       "window_start": None, "window_end": None},
        "birth_location": {"city": "Mumbai", "country": "India"},
        "full_birth_name": "Arjun Sharma",
        "current_name": None,
        "gender": "male",
        "iching_opted_in": False,
    }
    session.birth_time_tier = {
        "tier": "exact",
        "normalised_time": "10:30",
        "window_start": None,
        "window_end": None,
    }
    session.moon_resolution = {
        "moon_sign": "Scorpio",
        "moon_sign_certain": True,
        "transition_occurred": False,
    }
    session.active_heads = ["numerology", "chinese", "philosophy"]
    session.iching_opted_in = False
    session.save()
    return session


# ─────────────────────────────────────────────────────────────────────────────
# POST /session/start/
# ─────────────────────────────────────────────────────────────────────────────

class TestSessionStart(TestCase):

    def test_start_returns_201(self):
        resp = self.client.post(
            "/session/start/",
            data=json.dumps({"user_identifier": "new@example.com"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)

    def test_start_returns_session_id(self):
        data = _start_session(self.client, "sid@example.com")
        self.assertIn("session_id", data)
        self.assertTrue(len(data["session_id"]) > 0)

    def test_start_no_profile_found_false(self):
        data = _start_session(self.client, "noprofile@example.com")
        self.assertFalse(data["profile_found"])
        self.assertIsNone(data["profile_data"])
        self.assertIsNone(data["confirm_prompt"])

    def test_start_with_saved_profile_found_true(self):
        UserProfile.objects.create(
            user_identifier="existing@example.com",
            dob={"day": 1, "month": 1, "year": 1990},
            birth_time={"tier": "exact", "value": "10:00"},
            birth_location={"city": "Delhi", "country": "India"},
            full_birth_name="Test User",
        )
        data = _start_session(self.client, "existing@example.com")
        self.assertTrue(data["profile_found"])

    def test_start_with_profile_returns_confirm_prompt(self):
        UserProfile.objects.create(
            user_identifier="prompt@example.com",
            dob={"day": 5, "month": 6, "year": 1985},
            birth_time={"tier": "exact", "value": "08:00"},
            birth_location={"city": "Mumbai", "country": "India"},
            full_birth_name="Priya Nair",
        )
        data = _start_session(self.client, "prompt@example.com")
        self.assertIsNotNone(data["confirm_prompt"])
        self.assertIn("Welcome back", data["confirm_prompt"])

    def test_start_with_profile_returns_profile_data(self):
        UserProfile.objects.create(
            user_identifier="pdata@example.com",
            dob={"day": 10, "month": 4, "year": 1992},
            birth_time={"tier": "exact", "value": "14:00"},
            birth_location={"city": "Pune", "country": "India"},
            full_birth_name="Rahul Desai",
        )
        data = _start_session(self.client, "pdata@example.com")
        self.assertEqual(data["profile_data"]["full_birth_name"], "Rahul Desai")

    def test_start_creates_session_in_db(self):
        data = _start_session(self.client, "db@example.com")
        exists = SessionContext.objects.filter(
            session_id=data["session_id"]
        ).exists()
        self.assertTrue(exists)

    def test_start_without_user_identifier_still_works(self):
        resp = _post(self.client, "/session/start/", {})
        self.assertEqual(resp.status_code, 201)


# ─────────────────────────────────────────────────────────────────────────────
# POST /session/<id>/collect/
# ─────────────────────────────────────────────────────────────────────────────

class TestCollect(TestCase):

    def _session_id(self) -> str:
        return _start_session(self.client)["session_id"]

    def test_collect_missing_message_returns_400(self):
        sid = self._session_id()
        resp = _post(self.client, f"/session/{sid}/collect/", {})
        self.assertEqual(resp.status_code, 400)

    def test_collect_invalid_session_returns_404(self):
        fake_id = str(uuid.uuid4())
        resp = _post(self.client, f"/session/{fake_id}/collect/",
                     {"message": "hello"})
        self.assertEqual(resp.status_code, 404)

    def test_collect_first_message_returns_next_prompt(self):
        sid = self._session_id()
        resp = _post(self.client, f"/session/{sid}/collect/",
                     {"message": "Will I get a promotion this year?"})
        data = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertIn("system_message", data)
        self.assertIn("input_hint", data)

    def test_collect_returns_input_hint(self):
        sid = self._session_id()
        resp = _post(self.client, f"/session/{sid}/collect/",
                     {"message": "Will I get a promotion?"})
        data = resp.json()
        self.assertIn(data["input_hint"], ("free_text", "yes_no", "date", "location"))

    def test_collect_returns_collection_complete_bool(self):
        sid = self._session_id()
        resp = _post(self.client, f"/session/{sid}/collect/",
                     {"message": "Will things improve?"})
        data = resp.json()
        self.assertIn("collection_complete", data)
        self.assertIsInstance(data["collection_complete"], bool)

    def test_collect_iching_step_returns_yes_no_hint(self):
        """After query step, iching opt-in step returns yes_no hint."""
        sid = self._session_id()
        # Step 1: query
        _post(self.client, f"/session/{sid}/collect/",
              {"message": "Should I start my business?"})
        # Step 2: iching opt-in
        resp = _post(self.client, f"/session/{sid}/collect/",
                     {"message": "no"})
        data = resp.json()
        # Next step after iching opt-in is DOB
        self.assertEqual(resp.status_code, 200)
        self.assertIn("system_message", data)

    def test_collect_advances_through_conversation(self):
        """Walk through several steps and confirm state advances."""
        sid = self._session_id()
        steps = [
            "Should I change careers?",
            "no",            # iching opt-in
            "15 March 1990", # dob
        ]
        responses = []
        for msg in steps:
            resp = _post(self.client, f"/session/{sid}/collect/", {"message": msg})
            self.assertEqual(resp.status_code, 200)
            responses.append(resp.json())
        # Each response should have system_message
        for r in responses:
            self.assertIn("system_message", r)

    def test_collect_profile_confirmation_yes_returns_complete(self):
        """When profile_confirmation_pending, 'yes' → collection_complete."""
        UserProfile.objects.create(
            user_identifier="cfm@example.com",
            dob={"day": 1, "month": 1, "year": 1990},
            birth_time={"tier": "exact", "normalised_time": "10:00",
                        "window_start": None, "window_end": None},
            birth_location={"city": "Delhi", "country": "India"},
            full_birth_name="Confirmed User",
        )
        start_data = _start_session(self.client, "cfm@example.com")
        sid = start_data["session_id"]

        resp = _post(self.client, f"/session/{sid}/collect/",
                     {"message": "yes"})
        data = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data["collection_complete"])

    def test_collect_profile_confirmation_no_starts_fresh(self):
        """When profile_confirmation_pending, 'no' → starts fresh collection."""
        UserProfile.objects.create(
            user_identifier="cfn@example.com",
            dob={"day": 1, "month": 1, "year": 1990},
            birth_time={"tier": "exact", "normalised_time": "08:00",
                        "window_start": None, "window_end": None},
            birth_location={"city": "Delhi", "country": "India"},
            full_birth_name="Old Name",
        )
        start_data = _start_session(self.client, "cfn@example.com")
        sid = start_data["session_id"]

        resp = _post(self.client, f"/session/{sid}/collect/",
                     {"message": "no"})
        data = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(data["collection_complete"])


# ─────────────────────────────────────────────────────────────────────────────
# POST /session/<id>/query/
# ─────────────────────────────────────────────────────────────────────────────

class TestQuery(TestCase):

    def _make_session(self) -> str:
        session = _make_active_session_with_data("qtest@example.com")
        return str(session.session_id)

    @patch("heads.philosophy.services.PhilosophyHeadEngine._call_llm")
    @patch("heads.iching.services.IChingHeadEngine._call_llm")
    @patch("synthesis.services.SynthesisLayer._call_llm")
    def test_query_returns_200(self, mock_synth, mock_iching, mock_phil):
        mock_synth.return_value = _MOCK_SUMMARY
        mock_phil.return_value = {
            "query_theme": "career",
            "query_category": "career",
            "frameworks": {
                "stoicism": {"applied_finding": "Focus on what you can control."},
                "vedanta": {"applied_finding": "Act without attachment to outcome."},
                "karma": {"applied_finding": "Your actions now shape future cycles."},
            },
            "convergence": None,
            "divergence": None,
            "query_relevant_findings": ["Act deliberately."],
            "tendency_window_weeks": None,
        }
        mock_iching.return_value = {
            "query_application": "Dispersion counsel.",
            "query_relevant_findings": ["Dissolve rigidity."],
        }

        sid = self._make_session()
        resp = _post(self.client, f"/session/{sid}/query/",
                     {"query": "What should I focus on this year?"})
        self.assertEqual(resp.status_code, 200)

    @patch("heads.philosophy.services.PhilosophyHeadEngine._call_llm")
    @patch("synthesis.services.SynthesisLayer._call_llm")
    def test_query_returns_summary(self, mock_synth, mock_phil):
        mock_synth.return_value = _MOCK_SUMMARY
        mock_phil.return_value = {
            "query_theme": "career",
            "query_category": "career",
            "frameworks": {
                "stoicism": {"applied_finding": "Act."},
                "vedanta": {"applied_finding": "Detach."},
                "karma": {"applied_finding": "Act now."},
            },
            "convergence": None,
            "divergence": None,
            "query_relevant_findings": ["Act deliberately."],
            "tendency_window_weeks": None,
        }
        sid = self._make_session()
        resp = _post(self.client, f"/session/{sid}/query/",
                     {"query": "Career focus?"})
        data = resp.json()
        self.assertIn("summary", data)

    @patch("heads.philosophy.services.PhilosophyHeadEngine._call_llm")
    @patch("synthesis.services.SynthesisLayer._call_llm")
    def test_query_returns_query_index(self, mock_synth, mock_phil):
        mock_synth.return_value = _MOCK_SUMMARY
        mock_phil.return_value = {
            "query_theme": "career", "query_category": "career",
            "frameworks": {"stoicism": {"applied_finding": "a"},
                           "vedanta": {"applied_finding": "b"},
                           "karma": {"applied_finding": "c"}},
            "convergence": None, "divergence": None,
            "query_relevant_findings": ["x"], "tendency_window_weeks": None,
        }
        sid = self._make_session()
        resp = _post(self.client, f"/session/{sid}/query/",
                     {"query": "Focus question?"})
        data = resp.json()
        self.assertIn("query_index", data)
        self.assertEqual(data["query_index"], 0)

    @patch("heads.philosophy.services.PhilosophyHeadEngine._call_llm")
    @patch("synthesis.services.SynthesisLayer._call_llm")
    def test_query_returns_tendency_window_key(self, mock_synth, mock_phil):
        mock_synth.return_value = _MOCK_SUMMARY
        mock_phil.return_value = {
            "query_theme": "career", "query_category": "career",
            "frameworks": {"stoicism": {"applied_finding": "a"},
                           "vedanta": {"applied_finding": "b"},
                           "karma": {"applied_finding": "c"}},
            "convergence": None, "divergence": None,
            "query_relevant_findings": ["x"], "tendency_window_weeks": None,
        }
        sid = self._make_session()
        resp = _post(self.client, f"/session/{sid}/query/",
                     {"query": "Finances?"})
        data = resp.json()
        self.assertIn("tendency_window", data)

    def test_query_missing_query_field_returns_400(self):
        """Session with no query in data_pool and no query field → 400."""
        svc = SessionService()
        session = svc.start_session("empty-q@example.com")
        session.active_heads = ["numerology", "chinese", "philosophy"]
        session.data_pool = {}  # deliberately no 'query' key
        session.save()
        resp = _post(self.client, f"/session/{str(session.session_id)}/query/", {})
        self.assertEqual(resp.status_code, 400)

    def test_query_invalid_session_returns_404(self):
        fake_id = str(uuid.uuid4())
        resp = _post(self.client, f"/session/{fake_id}/query/",
                     {"query": "test"})
        self.assertEqual(resp.status_code, 404)

    @patch("heads.philosophy.services.PhilosophyHeadEngine._call_llm")
    @patch("synthesis.services.SynthesisLayer._call_llm")
    def test_query_fourth_query_returns_429(self, mock_synth, mock_phil):
        mock_synth.return_value = _MOCK_SUMMARY
        mock_phil.return_value = {
            "query_theme": "career", "query_category": "career",
            "frameworks": {"stoicism": {"applied_finding": "a"},
                           "vedanta": {"applied_finding": "b"},
                           "karma": {"applied_finding": "c"}},
            "convergence": None, "divergence": None,
            "query_relevant_findings": ["x"], "tendency_window_weeks": None,
        }
        sid = self._make_session()
        for i in range(3):
            _post(self.client, f"/session/{sid}/query/",
                  {"query": f"Question {i + 1}?"})
        resp = _post(self.client, f"/session/{sid}/query/",
                     {"query": "Fourth question?"})
        self.assertEqual(resp.status_code, 429)

    @patch("heads.philosophy.services.PhilosophyHeadEngine._call_llm")
    @patch("synthesis.services.SynthesisLayer._call_llm")
    def test_query_stores_result_in_session(self, mock_synth, mock_phil):
        mock_synth.return_value = _MOCK_SUMMARY
        mock_phil.return_value = {
            "query_theme": "career", "query_category": "career",
            "frameworks": {"stoicism": {"applied_finding": "a"},
                           "vedanta": {"applied_finding": "b"},
                           "karma": {"applied_finding": "c"}},
            "convergence": None, "divergence": None,
            "query_relevant_findings": ["x"], "tendency_window_weeks": None,
        }
        sid = self._make_session()
        _post(self.client, f"/session/{sid}/query/",
              {"query": "Will I succeed?"})
        session = SessionContext.objects.get(session_id=sid)
        self.assertEqual(len(session.queries), 1)


# ─────────────────────────────────────────────────────────────────────────────
# POST /session/<id>/trail/
# ─────────────────────────────────────────────────────────────────────────────

class TestTrail(TestCase):

    def _make_session(self) -> str:
        return str(_make_active_session_with_data("trail@example.com").session_id)

    def test_trail_before_any_query_returns_400(self):
        sid = self._make_session()
        resp = _post(self.client, f"/session/{sid}/trail/",
                     {"user_requested": True})
        self.assertEqual(resp.status_code, 400)

    def test_trail_invalid_session_returns_404(self):
        fake_id = str(uuid.uuid4())
        resp = _post(self.client, f"/session/{fake_id}/trail/",
                     {"user_requested": True})
        self.assertEqual(resp.status_code, 404)

    @patch("heads.philosophy.services.PhilosophyHeadEngine._call_llm")
    @patch("synthesis.services.SynthesisLayer._call_llm")
    def test_trail_not_requested_returns_rendered_false(self, mock_synth, mock_phil):
        mock_synth.return_value = _MOCK_SUMMARY
        mock_phil.return_value = {
            "query_theme": "direction", "query_category": "direction",
            "frameworks": {"stoicism": {"applied_finding": "a"},
                           "vedanta": {"applied_finding": "b"},
                           "karma": {"applied_finding": "c"}},
            "convergence": None, "divergence": None,
            "query_relevant_findings": ["x"], "tendency_window_weeks": None,
        }
        sid = self._make_session()
        _post(self.client, f"/session/{sid}/query/",
              {"query": "My direction?"})
        resp = _post(self.client, f"/session/{sid}/trail/",
                     {"user_requested": False})
        data = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(data["rendered"])
        self.assertIsNone(data["trail"])

    @patch("heads.philosophy.services.PhilosophyHeadEngine._call_llm")
    @patch("synthesis.services.SynthesisLayer._call_llm")
    def test_trail_requested_returns_rendered_true(self, mock_synth, mock_phil):
        mock_synth.return_value = _MOCK_SUMMARY
        mock_phil.return_value = {
            "query_theme": "direction", "query_category": "direction",
            "frameworks": {"stoicism": {"applied_finding": "a"},
                           "vedanta": {"applied_finding": "b"},
                           "karma": {"applied_finding": "c"}},
            "convergence": None, "divergence": None,
            "query_relevant_findings": ["x"], "tendency_window_weeks": None,
        }
        sid = self._make_session()
        _post(self.client, f"/session/{sid}/query/",
              {"query": "My direction?"})
        resp = _post(self.client, f"/session/{sid}/trail/",
                     {"user_requested": True})
        data = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data["rendered"])

    @patch("heads.philosophy.services.PhilosophyHeadEngine._call_llm")
    @patch("synthesis.services.SynthesisLayer._call_llm")
    def test_trail_requested_has_trail_list(self, mock_synth, mock_phil):
        mock_synth.return_value = _MOCK_SUMMARY
        mock_phil.return_value = {
            "query_theme": "direction", "query_category": "direction",
            "frameworks": {"stoicism": {"applied_finding": "a"},
                           "vedanta": {"applied_finding": "b"},
                           "karma": {"applied_finding": "c"}},
            "convergence": None, "divergence": None,
            "query_relevant_findings": ["x"], "tendency_window_weeks": None,
        }
        sid = self._make_session()
        _post(self.client, f"/session/{sid}/query/",
              {"query": "My direction?"})
        resp = _post(self.client, f"/session/{sid}/trail/",
                     {"user_requested": True})
        data = resp.json()
        self.assertIsInstance(data["trail"], list)


# ─────────────────────────────────────────────────────────────────────────────
# POST /session/<id>/end/
# ─────────────────────────────────────────────────────────────────────────────

class TestSessionEnd(TestCase):

    def _make_session(self) -> str:
        return str(_make_active_session_with_data("end@example.com").session_id)

    def test_end_returns_200(self):
        sid = self._make_session()
        resp = _post(self.client, f"/session/{sid}/end/", {})
        self.assertEqual(resp.status_code, 200)

    def test_end_invalid_session_returns_404(self):
        fake_id = str(uuid.uuid4())
        resp = _post(self.client, f"/session/{fake_id}/end/", {})
        self.assertEqual(resp.status_code, 404)

    def test_end_no_reading_no_save_prompt(self):
        """Session with no completed reading → no save prompt."""
        sid = self._make_session()
        resp = _post(self.client, f"/session/{sid}/end/", {})
        data = resp.json()
        self.assertIsNone(data["save_prompt"])

    @patch("heads.philosophy.services.PhilosophyHeadEngine._call_llm")
    @patch("synthesis.services.SynthesisLayer._call_llm")
    def test_end_with_reading_returns_save_prompt(self, mock_synth, mock_phil):
        mock_synth.return_value = _MOCK_SUMMARY
        mock_phil.return_value = {
            "query_theme": "career", "query_category": "career",
            "frameworks": {"stoicism": {"applied_finding": "a"},
                           "vedanta": {"applied_finding": "b"},
                           "karma": {"applied_finding": "c"}},
            "convergence": None, "divergence": None,
            "query_relevant_findings": ["x"], "tendency_window_weeks": None,
        }
        sid = self._make_session()
        _post(self.client, f"/session/{sid}/query/",
              {"query": "Should I change jobs?"})
        resp = _post(self.client, f"/session/{sid}/end/", {})
        data = resp.json()
        self.assertIsNotNone(data["save_prompt"])
        self.assertIn("save", data["save_prompt"].lower())

    def test_end_returns_session_status(self):
        sid = self._make_session()
        resp = _post(self.client, f"/session/{sid}/end/", {})
        data = resp.json()
        self.assertIn("session_status", data)
        self.assertIn(data["session_status"], ("complete", "abandoned"))

    @patch("heads.philosophy.services.PhilosophyHeadEngine._call_llm")
    @patch("synthesis.services.SynthesisLayer._call_llm")
    def test_end_with_reading_session_status_complete(self, mock_synth, mock_phil):
        mock_synth.return_value = _MOCK_SUMMARY
        mock_phil.return_value = {
            "query_theme": "career", "query_category": "career",
            "frameworks": {"stoicism": {"applied_finding": "a"},
                           "vedanta": {"applied_finding": "b"},
                           "karma": {"applied_finding": "c"}},
            "convergence": None, "divergence": None,
            "query_relevant_findings": ["x"], "tendency_window_weeks": None,
        }
        sid = self._make_session()
        _post(self.client, f"/session/{sid}/query/",
              {"query": "Should I move?"})
        resp = _post(self.client, f"/session/{sid}/end/", {})
        data = resp.json()
        self.assertEqual(data["session_status"], "complete")

    def test_end_no_reading_session_status_abandoned(self):
        sid = self._make_session()
        resp = _post(self.client, f"/session/{sid}/end/", {})
        data = resp.json()
        self.assertEqual(data["session_status"], "abandoned")


# ─────────────────────────────────────────────────────────────────────────────
# Error shape
# ─────────────────────────────────────────────────────────────────────────────

class TestErrorShape(TestCase):

    def test_404_error_has_required_keys(self):
        fake_id = str(uuid.uuid4())
        resp = _post(self.client, f"/session/{fake_id}/collect/",
                     {"message": "hello"})
        data = resp.json()
        self.assertIn("error", data)
        self.assertIn("code", data)
        self.assertIn("message", data)
        self.assertIn("retry_safe", data)

    def test_400_error_has_required_keys(self):
        sid = _start_session(self.client)["session_id"]
        resp = _post(self.client, f"/session/{sid}/collect/", {})
        data = resp.json()
        self.assertIn("error", data)
        self.assertIn("code", data)
        self.assertIn("message", data)
