"""
Tests for S-01 — Data Collection Layer.

Done condition (from spec):
  All required fields populated or explicitly null.
  Output object valid and structured.
  Ambiguous inputs confirmed back to user before accepting.
  No field silently missing or silently defaulted.

Each test drives a full or partial conversation through DataCollectionService
and asserts on the state and final output object.
"""

from django.test import TestCase

from collection.constants import (
    STEP_BIRTH_LOCATION,
    STEP_BIRTH_TIME,
    STEP_COMPLETE,
    STEP_CURRENT_NAME,
    STEP_DOB,
    STEP_FULL_BIRTH_NAME,
    STEP_GENDER,
    STEP_ICHING_OPTIN,
    STEP_QUERY,
    TIER_APPROXIMATE,
    TIER_EXACT,
    TIER_NONE,
)
from collection.services import (
    CollectionState,
    DataCollectionService,
    _match_approximate_time,
    _parse_date,
    _parse_exact_time,
    _parse_location,
)


class TestHappyPath(TestCase):
    """All fields provided correctly — output is complete and fully populated."""

    def test_full_collection_produces_valid_output(self) -> None:
        svc = DataCollectionService()
        state = CollectionState()

        # Step 1: query
        state, prompt = svc.handle_response(state, "Will I change careers this year?")
        self.assertEqual(state.step, STEP_ICHING_OPTIN)
        self.assertFalse(prompt.is_complete)

        # Step 2: I Ching opt-in
        state, prompt = svc.handle_response(state, "yes")
        self.assertEqual(state.step, STEP_DOB)
        self.assertTrue(state.data["iching_opted_in"])

        # Step 3: date of birth — standard format → confirmation required
        state, prompt = svc.handle_response(state, "15 March 1990")
        self.assertTrue(prompt.is_confirmation_request)
        self.assertIsNotNone(state.pending_confirmation)

        # Step 3a: confirm
        state, prompt = svc.handle_response(state, "yes")
        self.assertEqual(state.step, STEP_BIRTH_TIME)
        self.assertEqual(state.data["dob"], {"day": 15, "month": 3, "year": 1990})

        # Step 4: exact birth time → confirmation required
        state, prompt = svc.handle_response(state, "10:30 AM")
        self.assertTrue(prompt.is_confirmation_request)

        # Step 4a: confirm
        state, prompt = svc.handle_response(state, "yes")
        self.assertEqual(state.step, STEP_BIRTH_LOCATION)
        self.assertEqual(state.data["birth_time"]["tier"], TIER_EXACT)
        self.assertEqual(state.data["birth_time"]["value"], "10:30")

        # Step 5: birth location → confirmation required
        state, prompt = svc.handle_response(state, "Mumbai, India")
        self.assertTrue(prompt.is_confirmation_request)

        # Step 5a: confirm
        state, prompt = svc.handle_response(state, "yes")
        self.assertEqual(state.step, STEP_FULL_BIRTH_NAME)
        self.assertEqual(state.data["birth_location"]["city"], "Mumbai")
        self.assertEqual(state.data["birth_location"]["country"], "India")

        # Step 6: full birth name
        state, prompt = svc.handle_response(state, "Arjun Ramesh Mehta")
        self.assertEqual(state.step, STEP_CURRENT_NAME)

        # Step 7: current name (different)
        state, prompt = svc.handle_response(state, "Arjun Mehta")
        self.assertEqual(state.step, STEP_GENDER)
        self.assertEqual(state.data["current_name"], "Arjun Mehta")

        # Step 8: gender
        state, prompt = svc.handle_response(state, "male")
        self.assertEqual(state.step, STEP_COMPLETE)
        self.assertTrue(prompt.is_complete)

        # Build and validate output
        output = svc.build_output(state)

        self.assertEqual(output["query"], "Will I change careers this year?")
        self.assertTrue(output["iching_opted_in"])
        self.assertEqual(output["dob"], {"day": 15, "month": 3, "year": 1990})
        self.assertEqual(output["birth_time"]["tier"], TIER_EXACT)
        self.assertEqual(output["birth_location"]["city"], "Mumbai")
        self.assertEqual(output["full_birth_name"], "Arjun Ramesh Mehta")
        self.assertEqual(output["current_name"], "Arjun Mehta")
        self.assertEqual(output["gender"], "male")
        self.assertIn("iching", output["active_heads"])
        self.assertIn("vedic", output["active_heads"])
        self.assertIn("philosophy", output["active_heads"])


class TestMissingBirthTime(TestCase):
    """User does not know birth time — collection proceeds, field is null."""

    def _run_to_birth_time(self, svc: DataCollectionService, state: CollectionState) -> CollectionState:
        """Drive state up to the birth time step."""
        state, _ = svc.handle_response(state, "What does the year ahead look like?")
        state, _ = svc.handle_response(state, "no")
        state, _ = svc.handle_response(state, "15/03/1990")
        state, _ = svc.handle_response(state, "yes")  # confirm dob
        return state

    def test_explicit_dont_know_produces_none_tier(self) -> None:
        svc = DataCollectionService()
        state = CollectionState()
        state = self._run_to_birth_time(svc, state)
        self.assertEqual(state.step, STEP_BIRTH_TIME)

        state, prompt = svc.handle_response(state, "I don't know")
        # Must advance past birth time — never block
        self.assertEqual(state.step, STEP_BIRTH_LOCATION)
        self.assertFalse(prompt.is_confirmation_request)
        self.assertEqual(state.data["birth_time"]["tier"], TIER_NONE)
        self.assertIsNone(state.data["birth_time"]["value"])

    def test_unknown_birth_time_not_in_output_as_missing(self) -> None:
        """Birth time must be explicitly null in output, not absent."""
        svc = DataCollectionService()
        state = CollectionState()
        state = self._run_to_birth_time(svc, state)

        state, _ = svc.handle_response(state, "unknown")
        state, _ = svc.handle_response(state, "Delhi, India")
        state, _ = svc.handle_response(state, "yes")  # confirm location
        state, _ = svc.handle_response(state, "Priya Sharma")
        state, _ = svc.handle_response(state, "skip")
        state, _ = svc.handle_response(state, "skip")

        self.assertEqual(state.step, STEP_COMPLETE)
        output = svc.build_output(state)
        self.assertIn("birth_time", output)
        self.assertEqual(output["birth_time"]["tier"], TIER_NONE)
        self.assertIsNone(output["birth_time"]["value"])


class TestWrongDateFormat(TestCase):
    """Date given in a non-standard format — parsed and confirmed before accepting."""

    def test_iso_date_triggers_confirmation(self) -> None:
        svc = DataCollectionService()
        state = CollectionState()
        state, _ = svc.handle_response(state, "Any question")
        state, _ = svc.handle_response(state, "no")

        # ISO format
        state, prompt = svc.handle_response(state, "1990-03-15")
        self.assertTrue(prompt.is_confirmation_request, "ISO date must trigger confirmation")
        self.assertIsNotNone(state.pending_confirmation)
        self.assertEqual(state.pending_confirmation["value"]["day"], 15)
        self.assertEqual(state.pending_confirmation["value"]["month"], 3)
        self.assertEqual(state.pending_confirmation["value"]["year"], 1990)

    def test_confirmation_commits_parsed_date(self) -> None:
        svc = DataCollectionService()
        state = CollectionState()
        state, _ = svc.handle_response(state, "Any question")
        state, _ = svc.handle_response(state, "no")

        state, _ = svc.handle_response(state, "1990-03-15")
        state, prompt = svc.handle_response(state, "yes")

        self.assertIsNone(state.pending_confirmation)
        self.assertEqual(state.data["dob"], {"day": 15, "month": 3, "year": 1990})
        self.assertEqual(state.step, STEP_BIRTH_TIME)

    def test_denial_re_asks_for_date(self) -> None:
        svc = DataCollectionService()
        state = CollectionState()
        state, _ = svc.handle_response(state, "Any question")
        state, _ = svc.handle_response(state, "no")

        state, _ = svc.handle_response(state, "1990-03-15")  # triggers confirmation
        state, prompt = svc.handle_response(state, "no")

        # Still on DOB step, pending cleared, re-ask message
        self.assertIsNone(state.pending_confirmation)
        self.assertEqual(state.step, STEP_DOB)
        self.assertFalse(prompt.is_confirmation_request)

    def test_natural_language_date_parsed_correctly(self) -> None:
        result = _parse_date("March 15, 1990")
        self.assertIsNotNone(result)
        self.assertEqual(result["day"], 15)
        self.assertEqual(result["month"], 3)
        self.assertEqual(result["year"], 1990)

    def test_ordinal_date_parsed_correctly(self) -> None:
        result = _parse_date("15th March 1990")
        self.assertIsNotNone(result)
        self.assertEqual(result["day"], 15)
        self.assertEqual(result["month"], 3)

    def test_garbage_date_returns_none(self) -> None:
        self.assertIsNone(_parse_date("not a date"))
        self.assertIsNone(_parse_date("banana"))
        self.assertIsNone(_parse_date(""))


class TestApproximateTimeMapping(TestCase):
    """Approximate time expressions map to correct windows from the S-02 table."""

    def test_morning_maps_to_correct_window(self) -> None:
        result = _match_approximate_time("morning")
        self.assertIsNotNone(result)
        _, ws, we = result
        self.assertEqual(ws, "06:00")
        self.assertEqual(we, "09:00")

    def test_evening_maps_to_correct_window(self) -> None:
        _, ws, we = _match_approximate_time("evening")
        self.assertEqual(ws, "18:00")
        self.assertEqual(we, "21:00")

    def test_after_sunset_maps_to_evening_window(self) -> None:
        _, ws, we = _match_approximate_time("after sunset")
        self.assertEqual(ws, "18:00")
        self.assertEqual(we, "21:00")

    def test_dawn_maps_to_correct_window(self) -> None:
        _, ws, we = _match_approximate_time("dawn")
        self.assertEqual(ws, "04:00")
        self.assertEqual(we, "06:00")

    def test_night_maps_to_correct_window(self) -> None:
        _, ws, we = _match_approximate_time("at night")
        self.assertEqual(ws, "21:00")
        self.assertEqual(we, "00:00")

    def test_approximate_time_triggers_confirmation(self) -> None:
        svc = DataCollectionService()
        state = CollectionState()
        state, _ = svc.handle_response(state, "Test query")
        state, _ = svc.handle_response(state, "no")
        state, _ = svc.handle_response(state, "15/03/1990")
        state, _ = svc.handle_response(state, "yes")

        state, prompt = svc.handle_response(state, "morning")
        self.assertTrue(prompt.is_confirmation_request)
        self.assertEqual(state.pending_confirmation["kind"], "birth_time_approximate")
        self.assertEqual(state.pending_confirmation["window_start"], "06:00")
        self.assertEqual(state.pending_confirmation["window_end"], "09:00")

    def test_approximate_time_confirmed_stores_correct_tier(self) -> None:
        svc = DataCollectionService()
        state = CollectionState()
        state, _ = svc.handle_response(state, "Test query")
        state, _ = svc.handle_response(state, "no")
        state, _ = svc.handle_response(state, "15/03/1990")
        state, _ = svc.handle_response(state, "yes")

        state, _ = svc.handle_response(state, "morning")
        state, prompt = svc.handle_response(state, "yes")

        self.assertEqual(state.data["birth_time"]["tier"], TIER_APPROXIMATE)
        self.assertEqual(state.data["birth_time"]["window_start"], "06:00")
        self.assertEqual(state.data["birth_time"]["window_end"], "09:00")
        self.assertEqual(state.step, STEP_BIRTH_LOCATION)

    def test_hedged_exact_time_treated_as_approximate(self) -> None:
        """'I think it was around 3pm' → approximate tier, not exact."""
        svc = DataCollectionService()
        state = CollectionState()
        state, _ = svc.handle_response(state, "Test query")
        state, _ = svc.handle_response(state, "no")
        state, _ = svc.handle_response(state, "15/03/1990")
        state, _ = svc.handle_response(state, "yes")

        state, prompt = svc.handle_response(state, "I think it was around 3pm")
        self.assertTrue(prompt.is_confirmation_request)
        self.assertEqual(state.pending_confirmation["kind"], "birth_time_approximate")

        state, _ = svc.handle_response(state, "yes")
        self.assertEqual(state.data["birth_time"]["tier"], TIER_APPROXIMATE)


class TestOptionalFieldSkip(TestCase):
    """Optional fields (current_name, gender) store null when skipped."""

    def _run_to_current_name(
        self, svc: DataCollectionService, state: CollectionState
    ) -> CollectionState:
        state, _ = svc.handle_response(state, "What does next year hold?")
        state, _ = svc.handle_response(state, "no")
        state, _ = svc.handle_response(state, "15/03/1990")
        state, _ = svc.handle_response(state, "yes")
        state, _ = svc.handle_response(state, "10:30 AM")
        state, _ = svc.handle_response(state, "yes")
        state, _ = svc.handle_response(state, "Delhi, India")
        state, _ = svc.handle_response(state, "yes")
        state, _ = svc.handle_response(state, "Priya Sharma")
        return state

    def test_skip_current_name_stores_null(self) -> None:
        svc = DataCollectionService()
        state = CollectionState()
        state = self._run_to_current_name(svc, state)
        self.assertEqual(state.step, STEP_CURRENT_NAME)

        state, prompt = svc.handle_response(state, "skip")
        self.assertIsNone(state.data["current_name"])
        self.assertEqual(state.step, STEP_GENDER)

    def test_no_for_current_name_stores_null(self) -> None:
        svc = DataCollectionService()
        state = CollectionState()
        state = self._run_to_current_name(svc, state)

        state, _ = svc.handle_response(state, "no")
        self.assertIsNone(state.data["current_name"])

    def test_skip_gender_stores_null(self) -> None:
        svc = DataCollectionService()
        state = CollectionState()
        state = self._run_to_current_name(svc, state)

        state, _ = svc.handle_response(state, "skip")  # current_name
        state, prompt = svc.handle_response(state, "skip")  # gender

        self.assertIsNone(state.data["gender"])
        self.assertTrue(prompt.is_complete)

    def test_skipped_optional_fields_present_as_null_in_output(self) -> None:
        """Skipped optional fields must appear explicitly as null — not absent."""
        svc = DataCollectionService()
        state = CollectionState()
        state = self._run_to_current_name(svc, state)

        state, _ = svc.handle_response(state, "skip")
        state, _ = svc.handle_response(state, "skip")

        output = svc.build_output(state)
        self.assertIn("current_name", output)
        self.assertIn("gender", output)
        self.assertIsNone(output["current_name"])
        self.assertIsNone(output["gender"])


class TestToleranceRules(TestCase):
    """Additional tolerance rule coverage."""

    def test_city_without_country_prompts_for_country(self) -> None:
        svc = DataCollectionService()
        state = CollectionState()
        state, _ = svc.handle_response(state, "Test query")
        state, _ = svc.handle_response(state, "no")
        state, _ = svc.handle_response(state, "15/03/1990")
        state, _ = svc.handle_response(state, "yes")
        state, _ = svc.handle_response(state, "I don't know")  # birth time → none

        # Provide only city
        state, prompt = svc.handle_response(state, "London")
        self.assertIn("country", prompt.message.lower())
        self.assertEqual(state.data.get("_partial_city"), "London")

    def test_city_without_country_then_country_produces_confirmation(self) -> None:
        svc = DataCollectionService()
        state = CollectionState()
        state, _ = svc.handle_response(state, "Test query")
        state, _ = svc.handle_response(state, "no")
        state, _ = svc.handle_response(state, "15/03/1990")
        state, _ = svc.handle_response(state, "yes")
        state, _ = svc.handle_response(state, "I don't know")

        state, _ = svc.handle_response(state, "London")
        state, prompt = svc.handle_response(state, "UK")
        self.assertTrue(prompt.is_confirmation_request)

    def test_unrecognised_birth_time_rephrased_once_then_null(self) -> None:
        svc = DataCollectionService()
        state = CollectionState()
        state, _ = svc.handle_response(state, "Test query")
        state, _ = svc.handle_response(state, "no")
        state, _ = svc.handle_response(state, "15/03/1990")
        state, _ = svc.handle_response(state, "yes")

        # First unrecognised → rephrase
        state, prompt1 = svc.handle_response(state, "xyzzy gibberish")
        self.assertFalse(prompt1.is_complete)
        self.assertEqual(state.step, STEP_BIRTH_TIME)

        # Second unrecognised → null and advance
        state, prompt2 = svc.handle_response(state, "still gibberish")
        self.assertEqual(state.step, STEP_BIRTH_LOCATION)
        self.assertEqual(state.data["birth_time"]["tier"], TIER_NONE)

    def test_iching_not_opted_in_excludes_iching_from_active_heads(self) -> None:
        svc = DataCollectionService()
        state = CollectionState()
        state, _ = svc.handle_response(state, "Test query")
        state, _ = svc.handle_response(state, "no")  # I Ching opt-in = no
        state, _ = svc.handle_response(state, "15/03/1990")
        state, _ = svc.handle_response(state, "yes")
        state, _ = svc.handle_response(state, "I don't know")
        state, _ = svc.handle_response(state, "Mumbai, India")
        state, _ = svc.handle_response(state, "yes")
        state, _ = svc.handle_response(state, "Test Name")
        state, _ = svc.handle_response(state, "skip")
        state, _ = svc.handle_response(state, "skip")

        output = svc.build_output(state)
        self.assertNotIn("iching", output["active_heads"])
        self.assertIn("vedic", output["active_heads"])


class TestOutputStructure(TestCase):
    """Output object always has every key defined in the S-01 contract."""

    REQUIRED_KEYS = {
        "query", "iching_opted_in", "dob", "birth_time",
        "birth_location", "full_birth_name", "current_name",
        "gender", "active_heads",
    }

    def test_output_contains_all_contract_keys(self) -> None:
        svc = DataCollectionService()
        state = CollectionState()

        state, _ = svc.handle_response(state, "Will I find love?")
        state, _ = svc.handle_response(state, "no")
        state, _ = svc.handle_response(state, "15/03/1990")
        state, _ = svc.handle_response(state, "yes")
        state, _ = svc.handle_response(state, "I don't know")
        state, _ = svc.handle_response(state, "Tokyo, Japan")
        state, _ = svc.handle_response(state, "yes")
        state, _ = svc.handle_response(state, "Hiroshi Tanaka")
        state, _ = svc.handle_response(state, "skip")
        state, _ = svc.handle_response(state, "skip")

        output = svc.build_output(state)
        for key in self.REQUIRED_KEYS:
            self.assertIn(key, output, f"Output missing required key: {key!r}")

    def test_active_heads_always_contains_five_mandatory_heads(self) -> None:
        svc = DataCollectionService()
        state = CollectionState()

        state, _ = svc.handle_response(state, "Test question")
        state, _ = svc.handle_response(state, "no")
        state, _ = svc.handle_response(state, "15/03/1990")
        state, _ = svc.handle_response(state, "yes")
        state, _ = svc.handle_response(state, "I don't know")
        state, _ = svc.handle_response(state, "Paris, France")
        state, _ = svc.handle_response(state, "yes")
        state, _ = svc.handle_response(state, "Marie Dupont")
        state, _ = svc.handle_response(state, "skip")
        state, _ = svc.handle_response(state, "skip")

        output = svc.build_output(state)
        for head in ("vedic", "western", "numerology", "chinese", "philosophy"):
            self.assertIn(head, output["active_heads"])
