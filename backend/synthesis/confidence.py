"""
S-12 — Confidence Note Generator

Collects confidence flags from all active heads. Produces a single
consolidated plain-language note when any head is at reduced fidelity.

Done condition:
  Note produced if and only if at least one head has confidence_flag = true.
  Always one consolidated statement. Severity always set when note_required =
  true. Tone never apologises or reassures. Note never appears when all heads
  at full fidelity.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Fixed canonical head order — used for consistent note phrasing.
_HEAD_ORDER: list[str] = [
    "vedic",
    "western",
    "numerology",
    "chinese",
    "philosophy",
    "iching",
]

# Human-readable labels per head.
_HEAD_LABELS: dict[str, str] = {
    "vedic": "Vedic astrology",
    "western": "Western astrology",
    "numerology": "Numerology",
    "chinese": "Chinese astrology",
    "philosophy": "Philosophy",
    "iching": "I Ching",
}


class ConfidenceNoteGenerator:
    """
    S-12 Confidence Note Generator.

    Accepts head confidence objects and moon resolution data. Returns a
    single consolidated confidence note (or null) with a severity level.
    """

    def generate(
        self,
        active_heads: list[str],
        head_confidence: dict[str, Optional[dict]],
        moon: dict,
    ) -> dict:
        """
        Produce the S-12 confidence note output.

        Args:
            active_heads: Names of heads that ran this query.
            head_confidence: Keyed by head name, each value a dict with
                ``flag`` (bool) and ``reason`` (str | None).
                Missing entries are treated as flag=False.
            moon: Dict with ``moon_sign_certain`` (bool) and
                ``transition_occurred`` (bool).

        Returns:
            {
                note_required: bool,
                note: str | None,
                affected_heads: list[str],
                severity: "minor" | "moderate" | "significant" | None,
            }
        """
        affected_heads: list[str] = []
        reasons: list[str] = []
        has_calculation_failure = False

        for head_name in _HEAD_ORDER:
            if head_name not in active_heads:
                continue

            # Philosophy flag should always be False; log anomaly if True.
            if head_name == "philosophy":
                conf = head_confidence.get(head_name) or {}
                if conf.get("flag"):
                    logger.warning(
                        "S-12: philosophy head has confidence_flag=True — "
                        "this is anomalous. Excluding from confidence note."
                    )
                continue

            conf = head_confidence.get(head_name)
            if conf is None:
                # Missing entry → treat as no flag (per spec failure behaviour).
                continue

            flag = bool(conf.get("flag", False))
            if not flag:
                continue

            affected_heads.append(head_name)
            reason = conf.get("reason") or ""

            # Detect calculation failure keyword in reason.
            if "calculation failure" in reason.lower() or "failed" in reason.lower():
                has_calculation_failure = True

            if reason:
                reasons.append(reason)

        # Moon sign uncertainty: not tied to a specific head flag, but surfaces
        # independently when transition_occurred=True and moon_sign_certain=False.
        moon_uncertain = (
            not moon.get("moon_sign_certain", True)
            and moon.get("transition_occurred", False)
        )

        if not affected_heads and not moon_uncertain:
            return {
                "note_required": False,
                "note": None,
                "affected_heads": [],
                "severity": None,
            }

        # ── Severity calculation ──────────────────────────────────────────────
        severity = self._compute_severity(
            affected_heads=affected_heads,
            moon_uncertain=moon_uncertain,
            has_calculation_failure=has_calculation_failure,
        )

        # ── Build consolidated note ───────────────────────────────────────────
        note = self._build_note(
            affected_heads=affected_heads,
            reasons=reasons,
            moon_uncertain=moon_uncertain,
        )

        return {
            "note_required": True,
            "note": note,
            "affected_heads": affected_heads,
            "severity": severity,
        }

    # ── Severity ──────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_severity(
        affected_heads: list[str],
        moon_uncertain: bool,
        has_calculation_failure: bool,
    ) -> str:
        """
        Apply spec severity rules:
          1 head flagged, moon sign uncertainty only          → minor
          1–2 heads flagged, approximate birth time          → minor
          2–3 heads flagged, approximate or no time          → moderate
          4+ heads flagged, or any calculation failure       → significant
        """
        if has_calculation_failure or len(affected_heads) >= 4:
            return "significant"

        count = len(affected_heads)

        if count == 0 and moon_uncertain:
            # Moon uncertainty only, no head flags
            return "minor"

        if count >= 2:
            # 2-3 heads (< 4 already handled above)
            return "moderate"

        # 1 head flagged (or 0 with moon uncertainty already excluded above)
        return "minor"

    # ── Note builder ──────────────────────────────────────────────────────────

    @staticmethod
    def _build_note(
        affected_heads: list[str],
        reasons: list[str],
        moon_uncertain: bool,
    ) -> str:
        """
        Build a single consolidated plain-language note.

        Rules:
        - One or two sentences — never a list.
        - Matter-of-fact. No apology. No reassurance.
        - States what is reduced and why.
        """
        parts: list[str] = []

        if affected_heads:
            labels = [_HEAD_LABELS.get(h, h) for h in affected_heads]

            if len(labels) == 1:
                head_phrase = labels[0]
            elif len(labels) == 2:
                head_phrase = f"{labels[0]} and {labels[1]}"
            else:
                head_phrase = (
                    ", ".join(labels[:-1]) + f", and {labels[-1]}"
                )

            # Consolidate reasons — deduplicate and join.
            unique_reasons = list(dict.fromkeys(
                r.rstrip(".").strip() for r in reasons if r.strip()
            ))

            if unique_reasons:
                reason_phrase = "; ".join(unique_reasons)
                parts.append(
                    f"{head_phrase} operating at reduced fidelity: "
                    f"{reason_phrase}."
                )
            else:
                parts.append(
                    f"{head_phrase} operating at reduced fidelity."
                )

        if moon_uncertain:
            parts.append(
                "Moon sign assigned by majority-day rule — "
                "birth time unknown and moon transitioned signs on birth date."
            )

        return " ".join(parts)
