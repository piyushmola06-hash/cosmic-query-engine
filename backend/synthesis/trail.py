"""
S-13 — Explainability Trail Renderer

Collects explainability trails from all active heads and renders them in
fixed order on explicit user request only.

Done condition:
  Trail renders only on explicit request. All active heads in fixed order.
  Unavailable sections always shown with reason. Null trails skipped with note.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Fixed display order — canonical across the system.
_HEAD_DISPLAY_ORDER: list[tuple[str, str]] = [
    ("vedic", "Vedic Astrology"),
    ("western", "Western Astrology"),
    ("numerology", "Numerology"),
    ("chinese", "Chinese Astrology"),
    ("philosophy", "Philosophy"),
    ("iching", "I Ching"),
]


class TrailRenderer:
    """
    S-13 Explainability Trail Renderer.

    Renders head explainability trails on explicit user request. Never renders
    proactively. Head display order is fixed regardless of active_heads ordering.
    """

    def render(
        self,
        active_heads: list[str],
        head_trails: dict[str, Optional[dict]],
        user_requested: bool,
    ) -> dict:
        """
        Produce the S-13 trail output.

        Args:
            active_heads: Names of heads that ran this query.
            head_trails: Keyed by head name. Each value is the head's
                ``explainability_trail`` dict (with ``label`` and
                ``sections`` keys), or None if the trail is unavailable.
            user_requested: True only when the user explicitly asked to see
                the trail. If False, rendering is suppressed entirely.

        Returns:
            {
                rendered: bool,
                trail: list[HeadTrailEntry] | None,
            }
            where HeadTrailEntry = {
                head_label: str,
                head_order: int,
                sections: list[SectionEntry],
            }
            and SectionEntry = {
                title: str,
                content: str,
                available: bool,
                unavailable_reason: str | None,
            }
        """
        if not user_requested:
            return {"rendered": False, "trail": None}

        trail_entries: list[dict] = []

        for order, (head_name, default_label) in enumerate(
            _HEAD_DISPLAY_ORDER, start=1
        ):
            if head_name not in active_heads:
                continue

            raw_trail = head_trails.get(head_name)

            if raw_trail is None:
                # Null trail: include the head label with a note section.
                trail_entries.append({
                    "head_label": default_label,
                    "head_order": order,
                    "sections": [
                        {
                            "title": "Trail Unavailable",
                            "content": (
                                f"Explainability trail for {default_label} "
                                f"is not available for this reading."
                            ),
                            "available": False,
                            "unavailable_reason": (
                                f"No trail data returned by {default_label}."
                            ),
                        }
                    ],
                })
                logger.debug(
                    "S-13: null trail for head=%s — included with note", head_name
                )
                continue

            # Validate trail object structure — skip malformed, include with note.
            if not isinstance(raw_trail, dict):
                trail_entries.append({
                    "head_label": default_label,
                    "head_order": order,
                    "sections": [
                        {
                            "title": "Trail Unavailable",
                            "content": (
                                f"Explainability trail for {default_label} "
                                f"has an unexpected format."
                            ),
                            "available": False,
                            "unavailable_reason": "Malformed trail object.",
                        }
                    ],
                })
                logger.warning(
                    "S-13: malformed trail for head=%s type=%s",
                    head_name,
                    type(raw_trail).__name__,
                )
                continue

            # Use label from trail object if present; fall back to default.
            head_label = raw_trail.get("label") or default_label

            raw_sections = raw_trail.get("sections")
            if not isinstance(raw_sections, list) or not raw_sections:
                # Malformed sections — include head with single note section.
                trail_entries.append({
                    "head_label": head_label,
                    "head_order": order,
                    "sections": [
                        {
                            "title": "Trail Unavailable",
                            "content": (
                                f"Explainability trail sections for "
                                f"{head_label} are missing or empty."
                            ),
                            "available": False,
                            "unavailable_reason": "Trail sections missing or empty.",
                        }
                    ],
                })
                continue

            # Normalise each section — ensure required keys, preserve domain language.
            sections: list[dict] = []
            for raw_sec in raw_sections:
                if not isinstance(raw_sec, dict):
                    continue
                sections.append({
                    "title": raw_sec.get("title", ""),
                    "content": raw_sec.get("content", ""),
                    "available": bool(raw_sec.get("available", True)),
                    "unavailable_reason": raw_sec.get("unavailable_reason", None),
                })

            trail_entries.append({
                "head_label": head_label,
                "head_order": order,
                "sections": sections,
            })

        return {
            "rendered": True,
            "trail": trail_entries,
        }
