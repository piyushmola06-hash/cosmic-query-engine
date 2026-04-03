"""
S-14 — SessionService
S-15 — ProfileSaveService
S-16 — ProfileLoadService

All session and profile management lives here. No business logic in views.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from django.db import transaction
from django.utils import timezone as django_timezone

from core.models import SessionContext, UserProfile

logger = logging.getLogger(__name__)

# S-14: maximum queries per session.
MAX_QUERIES_PER_SESSION = 3

# S-14: inactivity timeout in minutes.
INACTIVITY_TIMEOUT_MINUTES = 30

# S-15: save prompt text (verbatim from spec).
SAVE_PROMPT_TEXT = (
    "Would you like to save your details for future sessions? "
    "This means you won't need to re-enter your birth information next time. "
    "Your data is stored only for this purpose."
)

# S-16: profile confirmation template.
_CONFIRM_TEMPLATE = (
    "Welcome back. I have your details on file:\n"
    "Name: {name}\n"
    "Date of birth: {dob}\n"
    "Birth time: {birth_time}\n"
    "Birth location: {birth_location}\n"
    "Is this still correct?"
)

# All data pool fields that make up a complete profile.
_PROFILE_FIELDS = ["dob", "birth_time", "birth_location", "full_birth_name"]
_OPTIONAL_PROFILE_FIELDS = ["current_name", "gender"]


# ── S-14 — Session Service ────────────────────────────────────────────────────

class SessionService:
    """
    S-14 — Session Context management.

    Handles session lifecycle: creation, query accumulation, inactivity
    checking, and session end. Does not contain query processing logic —
    that belongs in the head engines and synthesis layer.
    """

    def start_session(self, user_identifier: str = "") -> SessionContext:
        """
        Create a new active SessionContext.

        Returns the new SessionContext instance. The caller is responsible
        for triggering S-16 profile check separately.
        """
        session = SessionContext.objects.create(
            user_identifier=user_identifier,
            session_status=SessionContext.STATUS_ACTIVE,
            data_pool={},
            queries=[],
            active_heads=[],
        )
        logger.debug("S-14 start_session: created session_id=%s", session.session_id)
        return session

    def get_session(self, session_id: str) -> Optional[SessionContext]:
        """
        Retrieve an active session by ID.

        Returns None if not found or not active.
        """
        try:
            session = SessionContext.objects.get(session_id=session_id)
        except SessionContext.DoesNotExist:
            logger.debug("S-14 get_session: not found session_id=%s", session_id)
            return None

        if session.session_status != SessionContext.STATUS_ACTIVE:
            logger.debug(
                "S-14 get_session: session_id=%s status=%s — not active",
                session_id,
                session.session_status,
            )
            return None

        return session

    def update_data_pool(
        self,
        session_id: str,
        field: str,
        value: object,
    ) -> tuple[Optional[SessionContext], list[str]]:
        """
        Update one field in the session data_pool.

        If birth_time or birth_location changes mid-session and queries
        already exist, flags prior readings as using uncorrected data.

        Returns:
            (session, flagged_query_indices)
            flagged_query_indices is non-empty only when correction affects
            prior readings.
        """
        session = self.get_session(session_id)
        if session is None:
            return None, []

        flagged: list[str] = []

        # Mid-session correction — flag prior readings if relevant fields change.
        correction_fields = {"birth_time", "birth_location", "dob"}
        if field in correction_fields and session.queries:
            queries = list(session.queries)
            for q in queries:
                if not q.get("corrected_data_flag"):
                    q["corrected_data_flag"] = True
            session.queries = queries
            flagged = [str(q.get("query_index", i)) for i, q in enumerate(queries)]
            logger.debug(
                "S-14 update_data_pool: field=%s changed mid-session, "
                "flagged %d prior query/queries",
                field,
                len(flagged),
            )

        session.data_pool = {**session.data_pool, field: value}
        session.save()
        return session, flagged

    def add_query(
        self,
        session_id: str,
        query_result: dict,
    ) -> tuple[Optional[SessionContext], bool]:
        """
        Append a completed query result to the session.

        Enforces the 3-query maximum. Returns (session, accepted).
        accepted=False means the query was rejected (limit reached).
        """
        session = self.get_session(session_id)
        if session is None:
            return None, False

        if len(session.queries) >= MAX_QUERIES_PER_SESSION:
            logger.debug(
                "S-14 add_query: session_id=%s at query limit (%d)",
                session_id,
                MAX_QUERIES_PER_SESSION,
            )
            return session, False

        query_result = dict(query_result)
        query_result["query_index"] = len(session.queries)
        if "timestamp" not in query_result:
            query_result["timestamp"] = django_timezone.now().isoformat()

        queries = list(session.queries)
        queries.append(query_result)
        session.queries = queries
        session.save()
        return session, True

    def end_session(
        self,
        session_id: str,
        abandoned: bool = False,
    ) -> Optional[SessionContext]:
        """
        End a session. Sets status to complete or abandoned.

        Abandoned sessions (no complete reading) are discarded silently — no
        S-15 prompt should be triggered by the caller.

        Returns the updated session, or None if not found.
        """
        session = SessionContext.objects.filter(session_id=session_id).first()
        if session is None:
            return None

        if abandoned:
            session.session_status = SessionContext.STATUS_ABANDONED
        else:
            session.session_status = SessionContext.STATUS_COMPLETE

        session.save()
        logger.debug(
            "S-14 end_session: session_id=%s status=%s",
            session_id,
            session.session_status,
        )
        return session

    def check_inactivity(self, session_id: str) -> bool:
        """
        Return True if session's last_activity is more than
        INACTIVITY_TIMEOUT_MINUTES ago.
        """
        session = SessionContext.objects.filter(session_id=session_id).first()
        if session is None:
            return False

        cutoff = django_timezone.now() - timedelta(minutes=INACTIVITY_TIMEOUT_MINUTES)
        return session.last_activity < cutoff

    def has_complete_reading(self, session: SessionContext) -> bool:
        """Return True if at least one query in the session has a non-null summary."""
        return any(
            bool(q.get("summary")) for q in (session.queries or [])
        )


# ── S-15 — Profile Save Service ───────────────────────────────────────────────

class ProfileSaveService:
    """
    S-15 — Profile Save Prompt.

    Profile is never saved without explicit yes from the user.
    Prompt appears only when at least one complete reading exists.
    Saved profile never includes query history.
    """

    def prompt_save(self, session_id: str) -> Optional[str]:
        """
        Return the save prompt text if at least one complete reading exists.

        Returns None (no prompt) if session not found or has no readings.
        """
        session = SessionContext.objects.filter(session_id=session_id).first()
        if session is None:
            return None

        svc = SessionService()
        if not svc.has_complete_reading(session):
            logger.debug(
                "S-15 prompt_save: session_id=%s — no complete reading, no prompt",
                session_id,
            )
            return None

        return SAVE_PROMPT_TEXT

    @transaction.atomic
    def save_profile(
        self, session_id: str, user_identifier: str
    ) -> tuple[Optional[UserProfile], Optional[str]]:
        """
        Extract data_pool from session, save to UserProfile.

        Query history is never saved — only static birth data.

        Returns:
            (profile, error_message)
            error_message is None on success.
        """
        session = SessionContext.objects.filter(session_id=session_id).first()
        if session is None:
            return None, "Session not found."

        pool = session.data_pool or {}

        profile, _ = UserProfile.objects.update_or_create(
            user_identifier=user_identifier,
            defaults={
                "dob": pool.get("dob"),
                "birth_time": pool.get("birth_time"),
                "birth_location": pool.get("birth_location"),
                "full_birth_name": pool.get("full_birth_name", ""),
                "current_name": pool.get("current_name"),
                "gender": pool.get("gender"),
            },
        )
        logger.debug(
            "S-15 save_profile: saved profile_id=%s for user=%s",
            profile.profile_id,
            user_identifier,
        )
        return profile, None

    def discard_profile(self, session_id: str) -> str:
        """
        User explicitly said no. Do nothing. Return confirmation message.
        """
        logger.debug("S-15 discard_profile: session_id=%s — user declined save", session_id)
        return "Your details have not been saved."


# ── S-16 — Profile Load Service ───────────────────────────────────────────────

class ProfileLoadService:
    """
    S-16 — Profile Load and Confirm.

    At new session start, checks for saved profile. Loads and presents for
    confirmation if found. Skips data collection on confirmation.
    Partial profiles collect only missing fields.
    """

    def check_profile(self, user_identifier: str) -> Optional[UserProfile]:
        """
        Return the saved UserProfile for this identifier, or None if not found.
        """
        try:
            return UserProfile.objects.get(user_identifier=user_identifier)
        except UserProfile.DoesNotExist:
            return None

    def confirm_profile(self, profile: UserProfile) -> str:
        """
        Format profile for display per S-16 spec prompt.
        """
        dob = profile.dob or {}
        dob_str = (
            f"{dob.get('day', '?')}/{dob.get('month', '?')}/{dob.get('year', '?')}"
            if dob
            else "Unknown"
        )

        birth_time = profile.birth_time or {}
        tier = birth_time.get("tier", "")
        value = birth_time.get("value", "")
        if tier and value:
            bt_str = f"{tier} — {value}"
        elif tier:
            bt_str = tier
        elif value:
            bt_str = value
        else:
            bt_str = "Not provided"

        loc = profile.birth_location or {}
        city = loc.get("city", "")
        country = loc.get("country", "")
        loc_str = f"{city}, {country}".strip(", ") if (city or country) else "Unknown"

        name = profile.full_birth_name or "Unknown"

        return _CONFIRM_TEMPLATE.format(
            name=name,
            dob=dob_str,
            birth_time=bt_str,
            birth_location=loc_str,
        )

    def load_profile_to_session(
        self, session_id: str, profile: UserProfile
    ) -> Optional[SessionContext]:
        """
        Populate the session data_pool from a confirmed saved profile.

        Sets s01_required = False in the data_pool to signal that full
        data collection can be skipped.

        Returns the updated session, or None if session not found.
        """
        session = SessionContext.objects.filter(session_id=session_id).first()
        if session is None:
            return None

        pool = {
            "dob": profile.dob,
            "birth_time": profile.birth_time,
            "birth_location": profile.birth_location,
            "full_birth_name": profile.full_birth_name,
            "current_name": profile.current_name,
            "gender": profile.gender,
            "s01_required": False,
        }
        session.data_pool = pool
        session.save()
        logger.debug(
            "S-16 load_profile_to_session: session_id=%s loaded from profile_id=%s",
            session_id,
            profile.profile_id,
        )
        return session

    def get_missing_fields(self, profile: UserProfile) -> list[str]:
        """
        Return list of required fields that are null/empty in the saved profile.

        Used to collect only the missing fields rather than running full S-01.
        Query and I Ching opt-in are always collected fresh and are never
        in this list.
        """
        missing: list[str] = []

        if not profile.dob:
            missing.append("dob")
        if not profile.birth_time:
            missing.append("birth_time")
        if not profile.birth_location:
            missing.append("birth_location")
        if not profile.full_birth_name:
            missing.append("full_birth_name")

        return missing
