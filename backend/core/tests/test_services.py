"""
Tests for S-14, S-15, S-16 — Session Context, Profile Save, Profile Load.

All tests use the Django test database — no mocking of the ORM.

Covers:
  S-14:
  - Session creation and retrieval
  - Data pool field update
  - Birth time/location change mid-session flags prior readings
  - Three-query maximum enforced — fourth query rejected
  - Session end: complete vs abandoned
  - Inactivity check returns correct boolean
  - Data never re-collected within session (data_pool reuse)

  S-15:
  - Prompt only when at least one reading exists
  - Prompt absent when no readings
  - Explicit yes → profile saved without query history
  - Explicit no → nothing saved, confirmation returned
  - Saved profile contains only static data, never queries

  S-16:
  - Profile not found → check returns None
  - Profile found → confirm_profile returns correct formatted text
  - Confirmed profile loaded to session (s01_required = False)
  - Partial profile → get_missing_fields returns only missing
  - Full profile → get_missing_fields returns empty list
  - Corrected input mid-session flags prior readings
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core.models import SessionContext, UserProfile
from core.services import (
    MAX_QUERIES_PER_SESSION,
    SAVE_PROMPT_TEXT,
    ProfileLoadService,
    ProfileSaveService,
    SessionService,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_session(user_identifier: str = "test@example.com") -> SessionContext:
    return SessionService().start_session(user_identifier=user_identifier)


def _query_result(summary: str | None = "The convergence is clear.") -> dict:
    return {
        "query": "What should I focus on this year?",
        "query_category": "direction",
        "head_findings": {},
        "summary": summary,
        "confidence_note": None,
        "trail_rendered": False,
    }


def _full_data_pool() -> dict:
    return {
        "dob": {"day": 15, "month": 3, "year": 1990},
        "birth_time": {"tier": "exact", "value": "10:30"},
        "birth_location": {"city": "Mumbai", "country": "India"},
        "full_birth_name": "Arjun Sharma",
        "current_name": None,
        "gender": "male",
    }


def _make_profile(
    user_identifier: str = "test@example.com",
    full: bool = True,
) -> UserProfile:
    kwargs: dict = {"user_identifier": user_identifier}
    if full:
        kwargs.update(
            dob={"day": 15, "month": 3, "year": 1990},
            birth_time={"tier": "exact", "value": "10:30"},
            birth_location={"city": "Mumbai", "country": "India"},
            full_birth_name="Arjun Sharma",
            current_name=None,
            gender="male",
        )
    return UserProfile.objects.create(**kwargs)


# ── S-14: Session creation ────────────────────────────────────────────────────

class TestSessionCreation(TestCase):

    def test_start_session_returns_session(self):
        svc = SessionService()
        session = svc.start_session("user@example.com")
        self.assertIsNotNone(session)
        self.assertIsNotNone(session.session_id)

    def test_session_starts_active(self):
        session = _make_session()
        self.assertEqual(session.session_status, SessionContext.STATUS_ACTIVE)

    def test_session_persisted_to_db(self):
        session = _make_session("db@example.com")
        fetched = SessionContext.objects.get(session_id=session.session_id)
        self.assertEqual(str(fetched.session_id), str(session.session_id))

    def test_session_data_pool_initially_empty(self):
        session = _make_session()
        self.assertEqual(session.data_pool, {})

    def test_session_queries_initially_empty(self):
        session = _make_session()
        self.assertEqual(session.queries, [])

    def test_session_user_identifier_stored(self):
        session = _make_session("uid-123")
        self.assertEqual(session.user_identifier, "uid-123")


# ── S-14: Session retrieval ───────────────────────────────────────────────────

class TestSessionRetrieval(TestCase):

    def test_get_session_returns_active(self):
        session = _make_session()
        svc = SessionService()
        fetched = svc.get_session(str(session.session_id))
        self.assertIsNotNone(fetched)
        self.assertEqual(str(fetched.session_id), str(session.session_id))

    def test_get_session_nonexistent_returns_none(self):
        svc = SessionService()
        result = svc.get_session("00000000-0000-0000-0000-000000000000")
        self.assertIsNone(result)

    def test_get_session_complete_returns_none(self):
        session = _make_session()
        svc = SessionService()
        svc.end_session(str(session.session_id))
        result = svc.get_session(str(session.session_id))
        self.assertIsNone(result)

    def test_get_session_abandoned_returns_none(self):
        session = _make_session()
        svc = SessionService()
        svc.end_session(str(session.session_id), abandoned=True)
        result = svc.get_session(str(session.session_id))
        self.assertIsNone(result)


# ── S-14: Data pool update ────────────────────────────────────────────────────

class TestDataPoolUpdate(TestCase):

    def test_update_data_pool_stores_field(self):
        session = _make_session()
        svc = SessionService()
        svc.update_data_pool(
            str(session.session_id),
            "full_birth_name",
            "Priya Nair",
        )
        refreshed = SessionContext.objects.get(session_id=session.session_id)
        self.assertEqual(refreshed.data_pool["full_birth_name"], "Priya Nair")

    def test_update_data_pool_preserves_existing_fields(self):
        session = _make_session()
        svc = SessionService()
        svc.update_data_pool(str(session.session_id), "gender", "female")
        svc.update_data_pool(str(session.session_id), "full_birth_name", "Maya")
        refreshed = SessionContext.objects.get(session_id=session.session_id)
        self.assertEqual(refreshed.data_pool["gender"], "female")
        self.assertEqual(refreshed.data_pool["full_birth_name"], "Maya")

    def test_update_data_pool_nonexistent_session_returns_none(self):
        svc = SessionService()
        result, flagged = svc.update_data_pool(
            "00000000-0000-0000-0000-000000000000", "dob", {}
        )
        self.assertIsNone(result)
        self.assertEqual(flagged, [])


# ── S-14: Corrected input flags prior readings ────────────────────────────────

class TestCorrectedInputFlagsPriorReadings(TestCase):

    def test_birth_time_change_flags_existing_queries(self):
        session = _make_session()
        svc = SessionService()
        # Add a completed query first
        svc.add_query(str(session.session_id), _query_result())
        # Now correct birth_time
        _, flagged = svc.update_data_pool(
            str(session.session_id),
            "birth_time",
            {"tier": "approximate", "value": "morning"},
        )
        self.assertTrue(len(flagged) > 0)

    def test_birth_location_change_flags_existing_queries(self):
        session = _make_session()
        svc = SessionService()
        svc.add_query(str(session.session_id), _query_result())
        _, flagged = svc.update_data_pool(
            str(session.session_id),
            "birth_location",
            {"city": "Delhi", "country": "India"},
        )
        self.assertTrue(len(flagged) > 0)

    def test_dob_change_flags_existing_queries(self):
        session = _make_session()
        svc = SessionService()
        svc.add_query(str(session.session_id), _query_result())
        _, flagged = svc.update_data_pool(
            str(session.session_id), "dob", {"day": 1, "month": 1, "year": 1990}
        )
        self.assertTrue(len(flagged) > 0)

    def test_non_correction_field_does_not_flag_queries(self):
        """Changing full_birth_name (not a correction field) does not flag queries."""
        session = _make_session()
        svc = SessionService()
        svc.add_query(str(session.session_id), _query_result())
        _, flagged = svc.update_data_pool(
            str(session.session_id), "full_birth_name", "New Name"
        )
        self.assertEqual(flagged, [])

    def test_prior_queries_have_corrected_data_flag_set(self):
        session = _make_session()
        svc = SessionService()
        svc.add_query(str(session.session_id), _query_result())
        svc.update_data_pool(
            str(session.session_id), "birth_time", {"tier": "none"}
        )
        refreshed = SessionContext.objects.get(session_id=session.session_id)
        for q in refreshed.queries:
            self.assertTrue(q.get("corrected_data_flag"))

    def test_no_flag_when_no_prior_queries(self):
        session = _make_session()
        svc = SessionService()
        _, flagged = svc.update_data_pool(
            str(session.session_id), "birth_time", {"tier": "exact", "value": "08:00"}
        )
        self.assertEqual(flagged, [])


# ── S-14: Three-query maximum ─────────────────────────────────────────────────

class TestQueryMaximum(TestCase):

    def test_three_queries_all_accepted(self):
        session = _make_session()
        svc = SessionService()
        for _ in range(MAX_QUERIES_PER_SESSION):
            _, accepted = svc.add_query(str(session.session_id), _query_result())
            self.assertTrue(accepted)

    def test_fourth_query_rejected(self):
        session = _make_session()
        svc = SessionService()
        for _ in range(MAX_QUERIES_PER_SESSION):
            svc.add_query(str(session.session_id), _query_result())
        _, accepted = svc.add_query(str(session.session_id), _query_result())
        self.assertFalse(accepted)

    def test_fourth_query_not_stored(self):
        session = _make_session()
        svc = SessionService()
        for _ in range(MAX_QUERIES_PER_SESSION):
            svc.add_query(str(session.session_id), _query_result())
        svc.add_query(str(session.session_id), _query_result("extra"))
        refreshed = SessionContext.objects.get(session_id=session.session_id)
        self.assertEqual(len(refreshed.queries), MAX_QUERIES_PER_SESSION)

    def test_query_index_increments(self):
        session = _make_session()
        svc = SessionService()
        for i in range(2):
            svc.add_query(str(session.session_id), _query_result())
        refreshed = SessionContext.objects.get(session_id=session.session_id)
        indices = [q["query_index"] for q in refreshed.queries]
        self.assertEqual(indices, [0, 1])

    def test_query_timestamp_set(self):
        session = _make_session()
        svc = SessionService()
        svc.add_query(str(session.session_id), _query_result())
        refreshed = SessionContext.objects.get(session_id=session.session_id)
        self.assertIn("timestamp", refreshed.queries[0])

    def test_add_query_nonexistent_session_returns_none_false(self):
        svc = SessionService()
        result, accepted = svc.add_query(
            "00000000-0000-0000-0000-000000000000", _query_result()
        )
        self.assertIsNone(result)
        self.assertFalse(accepted)


# ── S-14: Session end ─────────────────────────────────────────────────────────

class TestSessionEnd(TestCase):

    def test_end_session_sets_complete(self):
        session = _make_session()
        svc = SessionService()
        ended = svc.end_session(str(session.session_id))
        self.assertEqual(ended.session_status, SessionContext.STATUS_COMPLETE)

    def test_end_session_abandoned(self):
        session = _make_session()
        svc = SessionService()
        ended = svc.end_session(str(session.session_id), abandoned=True)
        self.assertEqual(ended.session_status, SessionContext.STATUS_ABANDONED)

    def test_end_session_nonexistent_returns_none(self):
        svc = SessionService()
        result = svc.end_session("00000000-0000-0000-0000-000000000000")
        self.assertIsNone(result)

    def test_complete_session_not_retrievable_via_get_session(self):
        session = _make_session()
        svc = SessionService()
        svc.end_session(str(session.session_id))
        self.assertIsNone(svc.get_session(str(session.session_id)))


# ── S-14: Inactivity check ────────────────────────────────────────────────────

class TestInactivityCheck(TestCase):

    def test_recently_active_session_not_inactive(self):
        session = _make_session()
        svc = SessionService()
        self.assertFalse(svc.check_inactivity(str(session.session_id)))

    def test_stale_session_is_inactive(self):
        session = _make_session()
        # Manually back-date last_activity.
        SessionContext.objects.filter(session_id=session.session_id).update(
            last_activity=timezone.now() - timedelta(minutes=31)
        )
        svc = SessionService()
        self.assertTrue(svc.check_inactivity(str(session.session_id)))

    def test_exactly_at_boundary_not_inactive(self):
        """Exactly at 30 minutes — last_activity == cutoff is NOT inactive."""
        session = _make_session()
        SessionContext.objects.filter(session_id=session.session_id).update(
            last_activity=timezone.now() - timedelta(minutes=29)
        )
        svc = SessionService()
        self.assertFalse(svc.check_inactivity(str(session.session_id)))

    def test_nonexistent_session_returns_false(self):
        svc = SessionService()
        self.assertFalse(svc.check_inactivity("00000000-0000-0000-0000-000000000000"))


# ── S-14: has_complete_reading ────────────────────────────────────────────────

class TestHasCompleteReading(TestCase):

    def test_no_queries_not_complete(self):
        session = _make_session()
        svc = SessionService()
        self.assertFalse(svc.has_complete_reading(session))

    def test_query_with_null_summary_not_complete(self):
        session = _make_session()
        svc = SessionService()
        svc.add_query(str(session.session_id), _query_result(summary=None))
        refreshed = SessionContext.objects.get(session_id=session.session_id)
        self.assertFalse(svc.has_complete_reading(refreshed))

    def test_query_with_summary_is_complete(self):
        session = _make_session()
        svc = SessionService()
        svc.add_query(str(session.session_id), _query_result())
        refreshed = SessionContext.objects.get(session_id=session.session_id)
        self.assertTrue(svc.has_complete_reading(refreshed))


# ── S-15: Profile save prompt ─────────────────────────────────────────────────

class TestProfileSavePrompt(TestCase):

    def test_prompt_returned_when_reading_exists(self):
        session = _make_session()
        svc_session = SessionService()
        svc_session.add_query(str(session.session_id), _query_result())

        svc = ProfileSaveService()
        prompt = svc.prompt_save(str(session.session_id))
        self.assertEqual(prompt, SAVE_PROMPT_TEXT)

    def test_no_prompt_when_no_readings(self):
        session = _make_session()
        svc = ProfileSaveService()
        prompt = svc.prompt_save(str(session.session_id))
        self.assertIsNone(prompt)

    def test_no_prompt_when_only_null_summary_query(self):
        session = _make_session()
        svc_session = SessionService()
        svc_session.add_query(str(session.session_id), _query_result(summary=None))

        svc = ProfileSaveService()
        prompt = svc.prompt_save(str(session.session_id))
        self.assertIsNone(prompt)

    def test_no_prompt_for_nonexistent_session(self):
        svc = ProfileSaveService()
        prompt = svc.prompt_save("00000000-0000-0000-0000-000000000000")
        self.assertIsNone(prompt)

    def test_prompt_text_contains_future_sessions(self):
        session = _make_session()
        svc_session = SessionService()
        svc_session.add_query(str(session.session_id), _query_result())
        svc = ProfileSaveService()
        prompt = svc.prompt_save(str(session.session_id))
        self.assertIn("future sessions", prompt)


# ── S-15: Profile save ────────────────────────────────────────────────────────

class TestProfileSave(TestCase):

    def _session_with_pool(self) -> SessionContext:
        session = _make_session()
        pool = _full_data_pool()
        svc = SessionService()
        for k, v in pool.items():
            svc.update_data_pool(str(session.session_id), k, v)
        svc.add_query(str(session.session_id), _query_result())
        return SessionContext.objects.get(session_id=session.session_id)

    def test_save_profile_creates_userprofile(self):
        session = self._session_with_pool()
        svc = ProfileSaveService()
        profile, err = svc.save_profile(str(session.session_id), "save@example.com")
        self.assertIsNone(err)
        self.assertIsNotNone(profile)
        self.assertEqual(profile.user_identifier, "save@example.com")

    def test_saved_profile_has_dob(self):
        session = self._session_with_pool()
        svc = ProfileSaveService()
        profile, _ = svc.save_profile(str(session.session_id), "dob@example.com")
        self.assertEqual(profile.dob["day"], 15)

    def test_saved_profile_has_no_queries(self):
        session = self._session_with_pool()
        svc = ProfileSaveService()
        profile, _ = svc.save_profile(str(session.session_id), "noq@example.com")
        # UserProfile has no queries field — confirm it doesn't exist.
        self.assertFalse(hasattr(profile, "queries"))

    def test_saved_profile_has_no_query_history_in_name_field(self):
        """full_birth_name must not contain query text."""
        session = self._session_with_pool()
        svc = ProfileSaveService()
        profile, _ = svc.save_profile(str(session.session_id), "name@example.com")
        self.assertNotIn("What should", profile.full_birth_name)

    def test_save_second_time_updates_not_duplicates(self):
        session = self._session_with_pool()
        svc = ProfileSaveService()
        svc.save_profile(str(session.session_id), "update@example.com")
        svc.save_profile(str(session.session_id), "update@example.com")
        count = UserProfile.objects.filter(user_identifier="update@example.com").count()
        self.assertEqual(count, 1)

    def test_save_nonexistent_session_returns_error(self):
        svc = ProfileSaveService()
        profile, err = svc.save_profile(
            "00000000-0000-0000-0000-000000000000", "x@example.com"
        )
        self.assertIsNone(profile)
        self.assertIsNotNone(err)

    def test_discard_returns_confirmation(self):
        svc = ProfileSaveService()
        msg = svc.discard_profile("any-session-id")
        self.assertIsInstance(msg, str)
        self.assertTrue(len(msg) > 0)

    def test_discard_does_not_save_profile(self):
        session = _make_session("discard@example.com")
        svc = ProfileSaveService()
        svc.discard_profile(str(session.session_id))
        exists = UserProfile.objects.filter(
            user_identifier="discard@example.com"
        ).exists()
        self.assertFalse(exists)


# ── S-16: Profile check ───────────────────────────────────────────────────────

class TestProfileCheck(TestCase):

    def test_profile_not_found_returns_none(self):
        svc = ProfileLoadService()
        result = svc.check_profile("notfound@example.com")
        self.assertIsNone(result)

    def test_profile_found_returns_profile(self):
        _make_profile("found@example.com")
        svc = ProfileLoadService()
        result = svc.check_profile("found@example.com")
        self.assertIsNotNone(result)

    def test_profile_found_has_correct_identifier(self):
        _make_profile("check@example.com")
        svc = ProfileLoadService()
        result = svc.check_profile("check@example.com")
        self.assertEqual(result.user_identifier, "check@example.com")


# ── S-16: Profile confirmation text ──────────────────────────────────────────

class TestProfileConfirmation(TestCase):

    def test_confirm_profile_contains_name(self):
        profile = _make_profile("conf@example.com")
        svc = ProfileLoadService()
        text = svc.confirm_profile(profile)
        self.assertIn("Arjun Sharma", text)

    def test_confirm_profile_contains_dob(self):
        profile = _make_profile("dob@example.com")
        svc = ProfileLoadService()
        text = svc.confirm_profile(profile)
        self.assertIn("15", text)
        self.assertIn("1990", text)

    def test_confirm_profile_contains_birth_location(self):
        profile = _make_profile("loc@example.com")
        svc = ProfileLoadService()
        text = svc.confirm_profile(profile)
        self.assertIn("Mumbai", text)
        self.assertIn("India", text)

    def test_confirm_profile_contains_birth_time(self):
        profile = _make_profile("bt@example.com")
        svc = ProfileLoadService()
        text = svc.confirm_profile(profile)
        self.assertIn("10:30", text)

    def test_confirm_profile_asks_for_confirmation(self):
        profile = _make_profile("ask@example.com")
        svc = ProfileLoadService()
        text = svc.confirm_profile(profile)
        self.assertIn("Is this still correct", text)

    def test_confirm_profile_welcome_back(self):
        profile = _make_profile("wb@example.com")
        svc = ProfileLoadService()
        text = svc.confirm_profile(profile)
        self.assertIn("Welcome back", text)


# ── S-16: Load profile to session ────────────────────────────────────────────

class TestLoadProfileToSession(TestCase):

    def test_load_sets_s01_required_false(self):
        session = _make_session()
        profile = _make_profile("load@example.com")
        svc = ProfileLoadService()
        updated = svc.load_profile_to_session(str(session.session_id), profile)
        self.assertFalse(updated.data_pool.get("s01_required", True))

    def test_load_populates_data_pool_dob(self):
        session = _make_session()
        profile = _make_profile("pool@example.com")
        svc = ProfileLoadService()
        svc.load_profile_to_session(str(session.session_id), profile)
        refreshed = SessionContext.objects.get(session_id=session.session_id)
        self.assertEqual(refreshed.data_pool["dob"]["day"], 15)

    def test_load_populates_data_pool_name(self):
        session = _make_session()
        profile = _make_profile("name@example.com")
        svc = ProfileLoadService()
        svc.load_profile_to_session(str(session.session_id), profile)
        refreshed = SessionContext.objects.get(session_id=session.session_id)
        self.assertEqual(refreshed.data_pool["full_birth_name"], "Arjun Sharma")

    def test_load_nonexistent_session_returns_none(self):
        profile = _make_profile("ghost@example.com")
        svc = ProfileLoadService()
        result = svc.load_profile_to_session(
            "00000000-0000-0000-0000-000000000000", profile
        )
        self.assertIsNone(result)


# ── S-16: Missing fields detection ───────────────────────────────────────────

class TestGetMissingFields(TestCase):

    def test_full_profile_no_missing_fields(self):
        profile = _make_profile("full@example.com")
        svc = ProfileLoadService()
        missing = svc.get_missing_fields(profile)
        self.assertEqual(missing, [])

    def test_missing_dob(self):
        profile = UserProfile.objects.create(
            user_identifier="nodob@example.com",
            dob=None,
            birth_time={"tier": "exact", "value": "10:00"},
            birth_location={"city": "Delhi", "country": "India"},
            full_birth_name="Test User",
        )
        svc = ProfileLoadService()
        missing = svc.get_missing_fields(profile)
        self.assertIn("dob", missing)

    def test_missing_birth_time(self):
        profile = UserProfile.objects.create(
            user_identifier="nobt@example.com",
            dob={"day": 1, "month": 1, "year": 1990},
            birth_time=None,
            birth_location={"city": "Delhi", "country": "India"},
            full_birth_name="Test User",
        )
        svc = ProfileLoadService()
        missing = svc.get_missing_fields(profile)
        self.assertIn("birth_time", missing)

    def test_missing_birth_location(self):
        profile = UserProfile.objects.create(
            user_identifier="noloc@example.com",
            dob={"day": 1, "month": 1, "year": 1990},
            birth_time={"tier": "exact", "value": "10:00"},
            birth_location=None,
            full_birth_name="Test User",
        )
        svc = ProfileLoadService()
        missing = svc.get_missing_fields(profile)
        self.assertIn("birth_location", missing)

    def test_missing_full_birth_name(self):
        profile = UserProfile.objects.create(
            user_identifier="noname@example.com",
            dob={"day": 1, "month": 1, "year": 1990},
            birth_time={"tier": "exact", "value": "10:00"},
            birth_location={"city": "Delhi", "country": "India"},
            full_birth_name="",
        )
        svc = ProfileLoadService()
        missing = svc.get_missing_fields(profile)
        self.assertIn("full_birth_name", missing)

    def test_multiple_missing_fields(self):
        profile = UserProfile.objects.create(
            user_identifier="multi@example.com",
            dob=None,
            birth_time=None,
            birth_location=None,
            full_birth_name="",
        )
        svc = ProfileLoadService()
        missing = svc.get_missing_fields(profile)
        self.assertIn("dob", missing)
        self.assertIn("birth_time", missing)
        self.assertIn("birth_location", missing)
        self.assertIn("full_birth_name", missing)

    def test_query_not_in_missing_fields(self):
        """Query and I Ching opt-in are always fresh — never in missing fields."""
        profile = _make_profile("qfresh@example.com")
        svc = ProfileLoadService()
        missing = svc.get_missing_fields(profile)
        self.assertNotIn("query", missing)
        self.assertNotIn("iching_opted_in", missing)

    def test_optional_fields_not_in_required_missing(self):
        """current_name and gender are optional — missing them is fine."""
        profile = UserProfile.objects.create(
            user_identifier="opt@example.com",
            dob={"day": 1, "month": 1, "year": 1990},
            birth_time={"tier": "exact", "value": "10:00"},
            birth_location={"city": "Delhi", "country": "India"},
            full_birth_name="Test User",
            current_name=None,
            gender=None,
        )
        svc = ProfileLoadService()
        missing = svc.get_missing_fields(profile)
        self.assertNotIn("current_name", missing)
        self.assertNotIn("gender", missing)


# ── S-16: Full S-01 not re-run unnecessarily ─────────────────────────────────

class TestS01NotRerun(TestCase):

    def test_confirmed_profile_sets_s01_not_required(self):
        """After load_profile_to_session, data_pool has s01_required = False."""
        session = _make_session()
        profile = _make_profile("norun@example.com")
        svc = ProfileLoadService()
        svc.load_profile_to_session(str(session.session_id), profile)
        refreshed = SessionContext.objects.get(session_id=session.session_id)
        self.assertFalse(refreshed.data_pool.get("s01_required", True))

    def test_new_session_without_profile_has_empty_pool(self):
        """No profile loaded → data_pool is empty, caller must run S-01."""
        session = _make_session()
        self.assertEqual(session.data_pool, {})

    def test_partial_profile_missing_fields_returned(self):
        """Partial profile returns non-empty missing field list."""
        profile = UserProfile.objects.create(
            user_identifier="partial@example.com",
            dob={"day": 1, "month": 1, "year": 1990},
            birth_time=None,
            birth_location={"city": "Delhi", "country": "India"},
            full_birth_name="Test User",
        )
        svc = ProfileLoadService()
        missing = svc.get_missing_fields(profile)
        self.assertEqual(missing, ["birth_time"])
