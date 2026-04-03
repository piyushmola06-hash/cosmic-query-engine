"""
Backend API — five HTTP endpoints wiring all services.

POST /session/start/
POST /session/<id>/collect/
POST /session/<id>/query/
POST /session/<id>/trail/
POST /session/<id>/end/
"""

from __future__ import annotations

import logging
from typing import Optional

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from collection.birth_time import BirthTimeTierDetector
from collection.constants import (
    STEP_BIRTH_LOCATION,
    STEP_BIRTH_LOCATION_COUNTRY,
    STEP_BIRTH_TIME,
    STEP_BIRTH_TIME_CONFIRM,
    STEP_COMPLETE,
    STEP_DOB,
    STEP_DOB_CONFIRM,
    STEP_FULL_BIRTH_NAME,
    STEP_GENDER,
    STEP_ICHING_OPTIN,
    STEP_CURRENT_NAME,
    STEP_QUERY,
)
from collection.moon_sign import MoonSignResolver
from collection.services import CollectionState, DataCollectionService
from core.models import SessionContext
from core.services import (
    ProfileLoadService,
    ProfileSaveService,
    SessionService,
)
from heads.chinese.services import ChineseAstrologyHeadEngine
from heads.iching.services import IChingHeadEngine
from heads.numerology.services import NumerologyHeadEngine
from heads.philosophy.services import PhilosophyHeadEngine
from synthesis.confidence import ConfidenceNoteGenerator
from synthesis.services import SynthesisLayer
from synthesis.trail import TrailRenderer

logger = logging.getLogger(__name__)

# ── Input hint and quick reply maps (derived from step) ───────────────────────

_INPUT_HINTS: dict[str, str] = {
    STEP_QUERY: "free_text",
    STEP_ICHING_OPTIN: "yes_no",
    STEP_DOB: "date",
    STEP_DOB_CONFIRM: "yes_no",
    STEP_BIRTH_TIME: "free_text",
    STEP_BIRTH_TIME_CONFIRM: "yes_no",
    STEP_BIRTH_LOCATION: "location",
    STEP_BIRTH_LOCATION_COUNTRY: "location",
    STEP_FULL_BIRTH_NAME: "free_text",
    STEP_CURRENT_NAME: "free_text",
    STEP_GENDER: "free_text",
}

_QUICK_REPLIES: dict[str, list[str]] = {
    STEP_ICHING_OPTIN: ["Yes", "No"],
    STEP_DOB_CONFIRM: ["Yes", "No"],
    STEP_BIRTH_TIME_CONFIRM: ["Yes", "No"],
}

# Special step injected when profile confirmation is pending.
_STEP_PROFILE_CONFIRM = "profile_confirm"

# ── Error helper ──────────────────────────────────────────────────────────────

def _error(code: str, message: str, retry_safe: bool = False,
           http_status: int = 400) -> Response:
    return Response(
        {"error": True, "code": code, "message": message, "retry_safe": retry_safe},
        status=http_status,
    )


# ── CollectionState serialisation ────────────────────────────────────────────

def _state_to_dict(state: CollectionState) -> dict:
    return {
        "step": state.step,
        "data": state.data,
        "pending_confirmation": state.pending_confirmation,
        "rephrase_counts": state.rephrase_counts,
    }


def _state_from_dict(d: dict) -> CollectionState:
    s = CollectionState()
    s.step = d.get("step", STEP_QUERY)
    s.data = d.get("data", {})
    s.pending_confirmation = d.get("pending_confirmation")
    s.rephrase_counts = d.get("rephrase_counts", {})
    return s


# ── Head engine runner ─────────────────────────────────────────────────────────

def _run_head_engines(
    session: SessionContext,
    query: str,
    anthropic_client=None,
) -> dict[str, Optional[dict]]:
    """
    Run all available head engines.

    S-05 (Vedic) and S-06 (Western) are deferred — Swiss Ephemeris heads
    not yet built. Their slots are left as None and noted in synthesis_notes.
    """
    pool = session.data_pool or {}
    dob = pool.get("dob", {})
    birth_time_tier = session.birth_time_tier or {}
    birth_location = pool.get("birth_location", {})
    full_birth_name = pool.get("full_birth_name", "")
    current_name = pool.get("current_name")
    active_heads = list(session.active_heads or [])

    head_findings: dict[str, Optional[dict]] = {}

    # Vedic and Western deferred.
    if "vedic" in active_heads:
        head_findings["vedic"] = None
    if "western" in active_heads:
        head_findings["western"] = None

    # S-07 Numerology
    if "numerology" in active_heads:
        try:
            result = NumerologyHeadEngine().compute(
                full_birth_name=full_birth_name,
                current_name=current_name,
                dob=dob,
                query=query,
            )
            head_findings["numerology"] = result
        except Exception:
            logger.exception("Numerology head failed")
            head_findings["numerology"] = None

    # S-08 Chinese
    if "chinese" in active_heads:
        try:
            result = ChineseAstrologyHeadEngine().compute(
                dob=dob,
                birth_time=birth_time_tier,
                birth_location=birth_location,
                query=query,
            )
            head_findings["chinese"] = result
        except Exception:
            logger.exception("Chinese head failed")
            head_findings["chinese"] = None

    # S-09 Philosophy
    if "philosophy" in active_heads:
        try:
            engine = PhilosophyHeadEngine(anthropic_client=anthropic_client)
            result = engine.compute(query=query)
            head_findings["philosophy"] = result
        except Exception:
            logger.exception("Philosophy head failed")
            head_findings["philosophy"] = None

    # S-10 I Ching
    if "iching" in active_heads:
        try:
            seed = full_birth_name or str(dob)
            engine = IChingHeadEngine(anthropic_client=anthropic_client)
            result = engine.compute(seed=seed, query=query)
            head_findings["iching"] = result
        except Exception:
            logger.exception("I Ching head failed")
            head_findings["iching"] = None

    return head_findings


def _extract_universal_signals(head_findings: dict) -> dict:
    """Pull universal signals from numerology and chinese head findings."""
    signals = {
        "personal_year_9": False,
        "clash_year": False,
        "ben_ming_nian": False,
        "clash_reason": None,
        "ben_ming_nian_reason": None,
    }
    num = head_findings.get("numerology")
    if num:
        f = num.get("findings", num)
        if f.get("personal_year") == 9:
            signals["personal_year_9"] = True

    chi = head_findings.get("chinese")
    if chi:
        f = chi.get("findings", chi)
        signals["clash_year"] = bool(f.get("clash_year"))
        signals["clash_reason"] = f.get("clash_reason")
        signals["ben_ming_nian"] = bool(f.get("ben_ming_nian"))
        signals["ben_ming_nian_reason"] = f.get("ben_ming_nian_reason")

    return signals


def _run_synthesis(
    session: SessionContext,
    query: str,
    head_findings: dict,
    anthropic_client=None,
) -> tuple[dict, dict]:
    """Run S-11 synthesis + S-12 confidence note. Returns (synthesis, confidence)."""
    active_heads = list(session.active_heads or [])
    universal_signals = _extract_universal_signals(head_findings)

    synthesis_layer = SynthesisLayer(anthropic_client=anthropic_client)
    synthesis_result = synthesis_layer.synthesise(
        query=query,
        query_category="general",
        active_heads=active_heads,
        head_findings=head_findings,
        universal_signals=universal_signals,
    )

    head_confidence: dict = {}
    for head_name, findings in head_findings.items():
        if findings is not None:
            head_confidence[head_name] = {
                "flag": bool(findings.get("confidence_flag", False)),
                "reason": findings.get("confidence_reason"),
            }
        else:
            head_confidence[head_name] = {"flag": False, "reason": None}

    moon = session.moon_resolution or {}
    moon_conf = {
        "moon_sign_certain": moon.get("moon_sign_certain", True),
        "transition_occurred": moon.get("transition_occurred", False),
    }

    confidence_result = ConfidenceNoteGenerator().generate(
        active_heads=active_heads,
        head_confidence=head_confidence,
        moon=moon_conf,
    )

    return synthesis_result, confidence_result


# ─────────────────────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────────────────────


class SessionStartView(APIView):
    """
    POST /session/start/

    Creates a new session. Checks for saved profile. Returns session_id,
    profile status, and confirmation prompt if profile found.
    """

    def post(self, request: Request) -> Response:
        user_identifier = (request.data or {}).get("user_identifier", "")

        profile_svc = ProfileLoadService()
        session_svc = SessionService()

        # S-16: check for saved profile.
        profile = profile_svc.check_profile(user_identifier)

        # S-14: create session.
        session = session_svc.start_session(user_identifier=user_identifier)
        session_id = str(session.session_id)

        confirm_prompt = None
        profile_data = None

        if profile:
            confirm_prompt = profile_svc.confirm_profile(profile)
            profile_data = {
                "full_birth_name": profile.full_birth_name,
                "dob": profile.dob,
                "birth_time": profile.birth_time,
                "birth_location": profile.birth_location,
                "current_name": profile.current_name,
                "gender": profile.gender,
            }
            # Store profile in session pool tentatively; mark confirmation pending.
            profile_svc.load_profile_to_session(session_id, profile)
            session = SessionContext.objects.get(session_id=session_id)
            pool = dict(session.data_pool)
            pool["_profile_confirmation_pending"] = True
            session.data_pool = pool
            session.save()

        return Response({
            "session_id": session_id,
            "profile_found": profile is not None,
            "profile_data": profile_data,
            "confirm_prompt": confirm_prompt,
        }, status=status.HTTP_201_CREATED)


class CollectView(APIView):
    """
    POST /session/<id>/collect/

    Drives the S-01 data collection conversation. Accepts one user message
    per call. Returns next system message and input metadata. When
    collection_complete, triggers S-02 and S-03.
    """

    def post(self, request: Request, session_id) -> Response:
        session_svc = SessionService()
        session = session_svc.get_session(str(session_id))
        if session is None:
            return _error("session_not_found", "Session not found or no longer active.",
                          http_status=404)

        message = (request.data or {}).get("message", "").strip()
        if not message:
            return _error("missing_message", "Field 'message' is required.")

        pool = dict(session.data_pool)

        # ── Profile confirmation pending ──────────────────────────────────────
        if pool.get("_profile_confirmation_pending"):
            return self._handle_profile_confirmation(session, pool, message)

        # ── Normal S-01 collection ────────────────────────────────────────────
        raw_state = pool.get("_collection_state")
        if raw_state:
            state = _state_from_dict(raw_state)
        else:
            state = CollectionState()

        collection_svc = DataCollectionService()
        state, prompt = collection_svc.handle_response(state, message)

        # Persist updated state.
        pool["_collection_state"] = _state_to_dict(state)
        session.data_pool = pool
        session.save()

        if prompt.is_complete:
            return self._on_collection_complete(session, state, collection_svc)

        hint = _INPUT_HINTS.get(state.step, "free_text")
        quick_replies = _QUICK_REPLIES.get(state.step)
        # If pending_confirmation, override hint to yes_no.
        if state.pending_confirmation is not None:
            hint = "yes_no"
            quick_replies = ["Yes", "No"]

        return Response({
            "system_message": prompt.message,
            "input_hint": hint,
            "collection_complete": False,
            "quick_replies": quick_replies,
        })

    def _handle_profile_confirmation(
        self,
        session: SessionContext,
        pool: dict,
        message: str,
    ) -> Response:
        """Handle the user's yes/no response to the S-16 profile confirmation."""
        confirmed = message.lower().strip() in ("yes", "y", "yeah", "yep", "correct",
                                                 "that's correct", "thats correct", "right")
        pool.pop("_profile_confirmation_pending", None)

        if confirmed:
            # Profile already loaded — mark s01 not required.
            pool["s01_required"] = False
            session.data_pool = pool
            # Set active_heads from the loaded profile data.
            from collection.constants import MANDATORY_HEADS
            session.active_heads = list(MANDATORY_HEADS)
            session.save()

            # Run S-02 and S-03 on the loaded profile data.
            self._run_s02_s03(session)

            return Response({
                "system_message": "Great. What is your question?",
                "input_hint": "free_text",
                "collection_complete": True,
                "quick_replies": None,
            })
        else:
            # User wants to correct — clear profile data, start fresh S-01.
            pool = {k: v for k, v in pool.items()
                    if k not in ("dob", "birth_time", "birth_location",
                                 "full_birth_name", "current_name", "gender",
                                 "s01_required")}
            pool["_collection_state"] = _state_to_dict(CollectionState())
            session.data_pool = pool
            session.save()

            first_prompt = DataCollectionService().current_prompt(CollectionState())
            return Response({
                "system_message": first_prompt.message,
                "input_hint": _INPUT_HINTS.get(CollectionState().step, "free_text"),
                "collection_complete": False,
                "quick_replies": None,
            })

    def _on_collection_complete(
        self,
        session: SessionContext,
        state: CollectionState,
        collection_svc: DataCollectionService,
    ) -> Response:
        """Collection finished — build S-01 output, run S-02 and S-03."""
        output = collection_svc.build_output(state)

        # Update session with S-01 data.
        pool = dict(session.data_pool)
        pool.update({k: v for k, v in output.items()
                     if k not in ("active_heads",)})
        pool.pop("_collection_state", None)
        session.data_pool = pool
        session.active_heads = output.get("active_heads", [])
        session.iching_opted_in = output.get("iching_opted_in", False)
        session.save()

        self._run_s02_s03(session)

        return Response({
            "system_message": (
                "Thank you. I have everything I need. "
                "You can ask your question now or I can proceed with the reading."
            ),
            "input_hint": "free_text",
            "collection_complete": True,
            "quick_replies": None,
        })

    @staticmethod
    def _run_s02_s03(session: SessionContext) -> None:
        """Run S-02 BirthTimeTierDetector and S-03 MoonSignResolver, persist results."""
        pool = session.data_pool or {}
        birth_time_raw = pool.get("birth_time")

        # S-02
        if isinstance(birth_time_raw, dict):
            # Already a structured tier object (from profile load or prior run).
            tier_result_dict = birth_time_raw
        else:
            raw_str = birth_time_raw if isinstance(birth_time_raw, str) else None
            tier_result = BirthTimeTierDetector().classify(raw_str)
            tier_result_dict = {
                "tier": tier_result.tier,
                "normalised_time": tier_result.normalised_time,
                "window_start": tier_result.window_start,
                "window_end": tier_result.window_end,
            }

        session.birth_time_tier = tier_result_dict

        # S-03
        moon_result = MoonSignResolver().resolve(
            dob=pool.get("dob") or {},
            birth_time=tier_result_dict,
            birth_location=pool.get("birth_location"),
        )
        session.moon_resolution = moon_result
        session.save()

        logger.debug(
            "S-02/S-03 complete for session=%s tier=%s",
            session.session_id,
            tier_result_dict.get("tier"),
        )


class QueryView(APIView):
    """
    POST /session/<id>/query/

    Accepts a query string. Runs all available head engines + S-11 + S-12.
    Enforces 3-query maximum.
    """

    def post(self, request: Request, session_id) -> Response:
        session_svc = SessionService()
        session = session_svc.get_session(str(session_id))
        if session is None:
            return _error("session_not_found", "Session not found or no longer active.",
                          http_status=404)

        query = (request.data or {}).get("query", "").strip()
        if not query:
            # Fall back to query in data_pool (set during S-01).
            query = (session.data_pool or {}).get("query", "")
        if not query:
            return _error("missing_query", "Field 'query' is required.")

        # Enforce 3-query maximum before running anything.
        if len(session.queries or []) >= 3:
            return _error(
                "query_limit_reached",
                "This session has reached the maximum of 3 queries.",
                http_status=429,
            )

        # Inject mock client for testing if provided via request (test hook).
        anthropic_client = getattr(request, "_anthropic_client", None)

        # Run head engines.
        head_findings = _run_head_engines(session, query, anthropic_client)

        # Run S-11 + S-12.
        synthesis_result, confidence_result = _run_synthesis(
            session, query, head_findings, anthropic_client
        )

        # Build trail per-head for S-13 storage.
        head_trails = {
            head_name: (
                findings.get("explainability_trail")
                if findings else None
            )
            for head_name, findings in head_findings.items()
        }

        # Store query result in session.
        query_result = {
            "query": query,
            "query_category": "general",
            "head_findings": {
                k: v for k, v in head_findings.items() if v is not None
            },
            "head_trails": head_trails,
            "summary": synthesis_result.get("summary"),
            "confidence_note": confidence_result,
            "tendency_window": synthesis_result.get("tendency_window"),
            "convergence_signals": synthesis_result.get("convergence_signals", []),
            "divergence_signals": synthesis_result.get("divergence_signals", []),
            "trail_rendered": False,
        }

        _, accepted = session_svc.add_query(str(session_id), query_result)
        if not accepted:
            return _error(
                "query_limit_reached",
                "This session has reached the maximum of 3 queries.",
                http_status=429,
            )

        query_index = len(session_svc.get_session(str(session_id)).queries) - 1

        return Response({
            "summary": synthesis_result.get("summary"),
            "confidence_note": confidence_result if confidence_result.get("note_required") else None,
            "tendency_window": synthesis_result.get("tendency_window"),
            "query_index": query_index,
        })


class TrailView(APIView):
    """
    POST /session/<id>/trail/

    Returns the explainability trail for the last processed query.
    Returns 400 if no query has been processed yet.
    """

    def post(self, request: Request, session_id) -> Response:
        session_svc = SessionService()
        session = session_svc.get_session(str(session_id))
        if session is None:
            return _error("session_not_found", "Session not found or no longer active.",
                          http_status=404)

        queries = session.queries or []
        if not queries:
            return _error(
                "no_query_processed",
                "No query has been processed yet in this session.",
                http_status=400,
            )

        user_requested = bool((request.data or {}).get("user_requested", False))

        # Use the last query's head_trails.
        last_query = queries[-1]
        head_trails = last_query.get("head_trails", {})

        renderer = TrailRenderer()
        result = renderer.render(
            active_heads=list(session.active_heads or []),
            head_trails=head_trails,
            user_requested=user_requested,
        )

        return Response(result)


class SessionEndView(APIView):
    """
    POST /session/<id>/end/

    Ends the session. Returns S-15 save prompt if at least one reading exists.
    """

    def post(self, request: Request, session_id) -> Response:
        # Allow end on any session (active or not) by looking it up directly.
        session = SessionContext.objects.filter(session_id=str(session_id)).first()
        if session is None:
            return _error("session_not_found", "Session not found.", http_status=404)

        session_svc = SessionService()
        save_svc = ProfileSaveService()

        has_reading = session_svc.has_complete_reading(session)
        abandoned = not has_reading

        session_svc.end_session(str(session_id), abandoned=abandoned)

        save_prompt = save_svc.prompt_save(str(session_id)) if has_reading else None

        return Response({
            "save_prompt": save_prompt,
            "session_status": SessionContext.STATUS_COMPLETE if has_reading
                              else SessionContext.STATUS_ABANDONED,
        })
