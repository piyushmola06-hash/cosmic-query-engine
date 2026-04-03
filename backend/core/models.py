"""
S-14 / S-15 / S-16 — Core models.

SessionContext: persists conversation context within a session.
UserProfile: persists static birth data across sessions (never stores queries).

Divergence note: full_birth_name and current_name are stored as plain
CharFields in v0.1. Encryption (django-cryptography or equivalent) is
deferred — see DIVERGENCES.md.
"""

from __future__ import annotations

import uuid

from django.db import models


class SessionContext(models.Model):
    """
    S-14 — Session Context.

    One row per active or recently-ended session. Queries are stored as a
    JSON list inside the `queries` field — never as separate rows.
    """

    STATUS_ACTIVE = "active"
    STATUS_COMPLETE = "complete"
    STATUS_ABANDONED = "abandoned"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_COMPLETE, "Complete"),
        (STATUS_ABANDONED, "Abandoned"),
    ]

    session_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session_start = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)

    # Shared data pool — populated progressively during S-01 collection.
    data_pool = models.JSONField(default=dict)

    # S-02 output — birth time tier object.
    birth_time_tier = models.JSONField(null=True, blank=True)

    # S-03 output — moon resolution object.
    moon_resolution = models.JSONField(null=True, blank=True)

    # Whether the user opted in to I Ching for this session.
    iching_opted_in = models.BooleanField(default=False)

    # Head names that are active this session (e.g. ["numerology", "iching"]).
    active_heads = models.JSONField(default=list)

    # List of query result objects — see S-14 contract for shape.
    queries = models.JSONField(default=list)

    session_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
    )

    # Opaque identifier — email, device ID, or anonymous token.
    user_identifier = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        app_label = "core"
        ordering = ["-session_start"]

    def __str__(self) -> str:
        return f"Session {self.session_id} [{self.session_status}]"


class UserProfile(models.Model):
    """
    S-15 / S-16 — Persisted user profile.

    Stores only static birth data. Query history is never persisted here.

    v0.1 divergence: full_birth_name and current_name are plain CharFields.
    Encryption deferred — see DIVERGENCES.md.
    """

    profile_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_identifier = models.CharField(max_length=255, unique=True)
    saved_at = models.DateTimeField(auto_now=True)

    # Date of birth — {day, month, year}.
    dob = models.JSONField(null=True, blank=True)

    # S-02 BirthTimeTierObject.
    birth_time = models.JSONField(null=True, blank=True)

    # {city, country}.
    birth_location = models.JSONField(null=True, blank=True)

    # v0.1: plain storage. v0.2: encrypt with django-cryptography.
    full_birth_name = models.CharField(max_length=255, blank=True, default="")
    current_name = models.CharField(max_length=255, blank=True, null=True)

    gender = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        app_label = "core"

    def __str__(self) -> str:
        return f"Profile {self.profile_id} ({self.user_identifier})"
