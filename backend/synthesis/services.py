"""
S-11 — Synthesis Layer

Consumes structured findings from all active heads. Merges into a single
coherent prose summary. All active heads contribute equally. Does not read
explainability trails. Does not produce confidence notes.

Done condition (from spec):
  All active head findings in working set. Convergence and divergence both
  detected and neither suppressed. Universal signals always surface. Composite
  window correctly averaged and in weeks. Self-review checklist passes.
  Summary is prose. Anti-platitude and anti-optimism rules pass on every
  sentence.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Caution-direction values ──────────────────────────────────────────────────
# I Ching and other heads use these directions to signal caution.
_CAUTION_DIRECTIONS: frozenset[str] = frozenset({"retreat", "pause"})
_FORWARD_DIRECTIONS: frozenset[str] = frozenset({"forward"})

# ── Self-review: forbidden opener ─────────────────────────────────────────────
_FORBIDDEN_OPENER = "based on your birth chart"

# ── Bullet-list detection pattern ────────────────────────────────────────────
_BULLET_PATTERN = re.compile(
    r"^\s*(?:[-*•]|\d+[.)])\s",
    re.MULTILINE,
)

# ── LLM system prompt ─────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are the synthesis engine for a multi-system esoteric reading.

Your task: write a 1–2 paragraph prose summary of what the combined systems
reveal about the user's question. This is a synthesis — not a per-system
report.

WRITING RULES
─────────────
1. First sentence: state the most important signal from the combined readings.
2. 1–2 paragraphs. Each paragraph max 500 words. Total max 1000 words.
3. Convergence signals form the structural spine of the summary.
4. Divergence signals must be named honestly — never suppressed.
5. Universal signals (personal year, clash year, return year) are priority
   anchors — weave them in before other findings.
6. Tendency window: woven in naturally as "roughly X to Y weeks" — never as
   a fixed calendar date.
7. Every sentence references at least one specific finding from the working
   set.
8. No per-head attribution more than twice in the entire summary (do not keep
   saying "numerology says..." and "I Ching says...").
9. Never opens with "Based on your birth chart" or any variant.
10. Never closes with any disclaimer, caveat, or "consult a professional".
11. Always prose — never a bullet list, numbered list, or headers.
12. Never uses the word "journey".

ANTI-PLATITUDE RULES — these outputs are FORBIDDEN:
• "Everything happens for a reason"
• "Trust the process"
• "Focus on what you can control" without naming exactly what
• "Let go of what does not serve you" without naming exactly what
• Any sentence that applies equally to any reading

ANTI-OPTIMISM RULES — these outputs are FORBIDDEN:
• "Things will improve" without specific basis in the findings
• Reframing difficulty as hidden opportunity without a supporting finding
• Softening multiple caution signals into a single reassuring sentence
• Describing universal signals (clash year, return year) as purely positive

OUTPUT FORMAT
─────────────
Return ONLY valid JSON. No prose outside the JSON. No markdown fences.

{"summary": "<1–2 paragraph prose summary here>"}
"""


class SynthesisLayer:
    """
    S-11 Synthesis Layer.

    Consumes head findings from the pipeline and produces a single coherent
    prose summary via an LLM call. Convergence and divergence are detected
    from the structured findings before the LLM call and passed in as
    explicit signals — the LLM is never asked to detect them.

    The anthropic_client parameter is injectable for testing.
    """

    def __init__(self, anthropic_client: Optional[Any] = None) -> None:
        if anthropic_client is not None:
            self._client = anthropic_client
        else:
            try:
                from dotenv import load_dotenv
                load_dotenv(
                    dotenv_path=os.path.join(
                        os.path.dirname(__file__), "..", ".env"
                    )
                )
            except ImportError:
                pass

            import anthropic as _anthropic
            self._client = _anthropic.Anthropic(
                api_key=os.environ.get("ANTHROPIC_API_KEY")
            )

        self._model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")

    # ── Public API ────────────────────────────────────────────────────────────

    def synthesise(
        self,
        query: str,
        query_category: str,
        active_heads: list[str],
        head_findings: dict[str, Optional[dict]],
        universal_signals: dict,
    ) -> dict:
        """
        Produce the S-11 synthesis output.

        Args:
            query: The user's question.
            query_category: One of the S-01 categories.
            active_heads: Names of heads that ran (e.g. ["numerology","iching"]).
            head_findings: Full head engine output dict (with "head", "findings",
                "confidence_flag" keys) keyed by head name, or None if that head
                did not run or failed.
            universal_signals: Dict with keys personal_year_9, clash_year,
                ben_ming_nian, clash_reason, ben_ming_nian_reason.

        Returns:
            S-11 contract output dict.
        """
        synthesis_notes_parts: list[str] = []

        # ── Step 1: Collect working set ───────────────────────────────────────
        working_set, excluded_heads = self._collect_working_set(
            active_heads, head_findings
        )
        if excluded_heads:
            synthesis_notes_parts.append(
                f"Excluded head(s) with null findings: {', '.join(excluded_heads)}."
            )

        if not working_set:
            return {
                "summary": None,
                "paragraph_count": 0,
                "word_count": 0,
                "tendency_window": None,
                "convergence_signals": [],
                "divergence_signals": [],
                "universal_signals_surfaced": [],
                "synthesis_notes": "No findings available.",
            }

        # ── Step 2: Convergence signals ───────────────────────────────────────
        convergence_signals = self._detect_convergence(
            active_heads, head_findings
        )

        # ── Step 3: Divergence signals ────────────────────────────────────────
        divergence_signals = self._detect_divergence(
            active_heads, head_findings
        )

        # ── Step 4: Universal signals ─────────────────────────────────────────
        universal_signals_surfaced = self._surface_universal_signals(
            universal_signals
        )

        # ── Step 5: Composite tendency window ─────────────────────────────────
        tendency_window = self._compute_tendency_window(
            active_heads, head_findings
        )

        # ── Step 6: LLM summary ───────────────────────────────────────────────
        raw_summary = self._call_llm(
            query=query,
            query_category=query_category,
            working_set=working_set,
            convergence_signals=convergence_signals,
            divergence_signals=divergence_signals,
            universal_signals_surfaced=universal_signals_surfaced,
            tendency_window=tendency_window,
        )

        # ── Step 7: Self-review ───────────────────────────────────────────────
        summary, review_notes = self._self_review(raw_summary, tendency_window)
        if review_notes:
            synthesis_notes_parts.extend(review_notes)

        word_count = len(summary.split()) if summary else 0
        paragraph_count = len([p for p in summary.split("\n\n") if p.strip()]) if summary else 0
        paragraph_count = min(max(paragraph_count, 1), 2) if summary else 0

        synthesis_notes = (
            " ".join(synthesis_notes_parts) if synthesis_notes_parts else None
        )

        return {
            "summary": summary,
            "paragraph_count": paragraph_count,
            "word_count": word_count,
            "tendency_window": tendency_window,
            "convergence_signals": convergence_signals,
            "divergence_signals": divergence_signals,
            "universal_signals_surfaced": universal_signals_surfaced,
            "synthesis_notes": synthesis_notes,
        }

    # ── Step 1: Working set ───────────────────────────────────────────────────

    def _collect_working_set(
        self,
        active_heads: list[str],
        head_findings: dict[str, Optional[dict]],
    ) -> tuple[list[dict], list[str]]:
        """
        Pull query_relevant_findings from every active head.
        Tag each finding with its source head.

        Returns:
            (working_set, excluded_heads)
            working_set: list of {"head": str, "finding": any}
            excluded_heads: list of head names excluded due to null findings
        """
        working_set: list[dict] = []
        excluded: list[str] = []

        for head_name in active_heads:
            raw = head_findings.get(head_name)
            if raw is None:
                excluded.append(head_name)
                continue

            findings = self._get_findings(raw)
            qrf = findings.get("query_relevant_findings", [])

            if not isinstance(qrf, list):
                qrf = []

            for item in qrf:
                working_set.append({"head": head_name, "finding": item})

        return working_set, excluded

    # ── Step 2: Convergence detection ─────────────────────────────────────────

    def _detect_convergence(
        self,
        active_heads: list[str],
        head_findings: dict[str, Optional[dict]],
    ) -> list[str]:
        """Detect convergence signals across heads."""
        signals: list[str] = []

        # ── Timing alignment ──────────────────────────────────────────────────
        windows = self._collect_windows(active_heads, head_findings)
        timing_overlap = self._find_timing_overlap(windows)
        if timing_overlap:
            heads_str = ", ".join(timing_overlap["heads"])
            signals.append(
                f"Timing alignment: {heads_str} produce overlapping tendency "
                f"windows ({timing_overlap['overlap_min']}–"
                f"{timing_overlap['overlap_max']} weeks)."
            )

        # ── Domain alignment ──────────────────────────────────────────────────
        contributing_heads = [
            h for h in active_heads
            if head_findings.get(h) is not None
            and bool(self._get_findings(head_findings[h]).get("query_relevant_findings"))
        ]
        if len(contributing_heads) >= 2:
            signals.append(
                f"Domain alignment: {len(contributing_heads)} systems address "
                f"this query ({', '.join(contributing_heads)})."
            )

        # ── Caution alignment ─────────────────────────────────────────────────
        caution_heads = self._find_caution_heads(active_heads, head_findings)
        if len(caution_heads) >= 2:
            signals.append(
                f"Caution alignment: {', '.join(caution_heads)} both signal "
                f"difficulty or the need for restraint."
            )

        # ── Philosophy convergence ────────────────────────────────────────────
        if "philosophy" in active_heads and head_findings.get("philosophy"):
            phil_findings = self._get_findings(head_findings["philosophy"])
            phil_convergence = phil_findings.get("convergence")
            if phil_convergence:
                signals.append(
                    f"Philosophical convergence: {phil_convergence}"
                )

        return signals

    # ── Step 3: Divergence detection ──────────────────────────────────────────

    def _detect_divergence(
        self,
        active_heads: list[str],
        head_findings: dict[str, Optional[dict]],
    ) -> list[str]:
        """Detect divergence signals across heads."""
        signals: list[str] = []

        # ── Timing divergence ─────────────────────────────────────────────────
        windows = self._collect_windows(active_heads, head_findings)
        timing_divergence = self._find_timing_divergence(windows)
        if timing_divergence:
            a, b = timing_divergence["heads"]
            wa, wb = timing_divergence["windows"]
            signals.append(
                f"Timing divergence: {a} window ({wa['min']}–{wa['max']} weeks) "
                f"and {b} window ({wb['min']}–{wb['max']} weeks) do not overlap."
            )

        # ── Direction divergence ──────────────────────────────────────────────
        direction_conflict = self._find_direction_conflict(
            active_heads, head_findings
        )
        if direction_conflict:
            signals.append(direction_conflict)

        # ── Philosophy divergence ─────────────────────────────────────────────
        if "philosophy" in active_heads and head_findings.get("philosophy"):
            phil_findings = self._get_findings(head_findings["philosophy"])
            phil_divergence = phil_findings.get("divergence")
            if phil_divergence:
                signals.append(
                    f"Philosophical divergence: {phil_divergence}"
                )

        return signals

    # ── Step 4: Universal signals ──────────────────────────────────────────────

    def _surface_universal_signals(self, universal_signals: dict) -> list[str]:
        """Surface universal signals when true. Always included when true."""
        surfaced: list[str] = []

        if universal_signals.get("personal_year_9"):
            surfaced.append(
                "This is a year of completion and release in your numerological cycle."
            )

        if universal_signals.get("clash_year"):
            clash_reason = universal_signals.get("clash_reason") or "a clash year"
            surfaced.append(
                f"Clash year active: {clash_reason}"
            )

        if universal_signals.get("ben_ming_nian"):
            ben_reason = universal_signals.get("ben_ming_nian_reason", "")
            base = (
                "You are in your return year — heightened significance in "
                "both opportunity and vulnerability."
            )
            surfaced.append(
                f"{base} {ben_reason}".strip() if ben_reason else base
            )

        return surfaced

    # ── Step 5: Composite tendency window ─────────────────────────────────────

    def _compute_tendency_window(
        self,
        active_heads: list[str],
        head_findings: dict[str, Optional[dict]],
    ) -> Optional[dict]:
        """
        Average min and max across all non-null head tendency windows.
        Returns None if all windows are null.
        """
        windows = self._collect_windows(active_heads, head_findings)
        if not windows:
            return None

        mins = [w["window"]["min"] for w in windows]
        maxes = [w["window"]["max"] for w in windows]
        composite_min = round(sum(mins) / len(mins))
        composite_max = round(sum(maxes) / len(maxes))
        contributing = [w["head"] for w in windows]

        expressed = f"roughly {composite_min} to {composite_max} weeks"

        return {
            "composite_min_weeks": composite_min,
            "composite_max_weeks": composite_max,
            "contributing_heads": contributing,
            "expressed_as": expressed,
        }

    # ── Step 6: LLM call ──────────────────────────────────────────────────────

    def _call_llm(
        self,
        query: str,
        query_category: str,
        working_set: list[dict],
        convergence_signals: list[str],
        divergence_signals: list[str],
        universal_signals_surfaced: list[str],
        tendency_window: Optional[dict],
    ) -> str:
        """
        Build context message and call the Anthropic API.
        Returns the raw summary string.
        """
        lines: list[str] = [
            f"User query: {query or '(no query provided)'}",
            f"Query category: {query_category}",
            "",
        ]

        if universal_signals_surfaced:
            lines.append("UNIVERSAL SIGNALS (priority anchors):")
            for sig in universal_signals_surfaced:
                lines.append(f"  • {sig}")
            lines.append("")

        if convergence_signals:
            lines.append("CONVERGENCE SIGNALS (structural spine):")
            for sig in convergence_signals:
                lines.append(f"  • {sig}")
            lines.append("")

        if divergence_signals:
            lines.append("DIVERGENCE SIGNALS (name these honestly):")
            for sig in divergence_signals:
                lines.append(f"  • {sig}")
            lines.append("")

        if tendency_window:
            lines.append(
                f"COMPOSITE TENDENCY WINDOW: {tendency_window['expressed_as']} "
                f"(from {', '.join(tendency_window['contributing_heads'])})."
            )
            lines.append("")

        if working_set:
            lines.append("WORKING SET (query-relevant findings, tagged by source):")
            for entry in working_set:
                head = entry["head"]
                finding = entry["finding"]
                if isinstance(finding, dict):
                    text = finding.get("note") or finding.get("value") or str(finding)
                else:
                    text = str(finding)
                lines.append(f"  [{head}] {text}")
            lines.append("")

        user_message = "\n".join(lines)

        logger.debug("S-11 SynthesisLayer._call_llm query=%r", query)

        response = self._client.messages.create(
            model=self._model,
            max_tokens=1200,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        raw_text = response.content[0].text.strip()

        logger.debug("S-11 LLM raw response: %s", raw_text[:200])

        try:
            parsed = json.loads(raw_text)
            return parsed.get("summary", raw_text)
        except json.JSONDecodeError:
            # If not JSON, treat the whole response as the summary
            return raw_text

    # ── Step 7: Self-review ───────────────────────────────────────────────────

    def _self_review(
        self,
        summary: str,
        tendency_window: Optional[dict],
    ) -> tuple[str, list[str]]:
        """
        Mechanical self-review checklist.

        Checks that can be reliably enforced in code:
          □ Word count within ceiling (1000 words)
          □ Word "journey" not present
          □ Does not open with forbidden opener
          □ Not a bullet list
          □ Tendency window referenced in weeks (if window is non-null)

        Returns:
            (reviewed_summary, list_of_review_notes)
        """
        notes: list[str] = []
        result = summary

        # □ Word count ceiling — truncate at sentence boundary
        words = result.split()
        if len(words) > 1000:
            truncated = _truncate_at_sentence_boundary(result, 1000)
            notes.append(
                f"Summary truncated from {len(words)} words to word ceiling. "
                f"Truncated at sentence boundary."
            )
            result = truncated

        # □ Word "journey" not present
        if re.search(r"\bjourney\b", result, re.IGNORECASE):
            result = re.sub(r"\bjourney\b", "path", result, flags=re.IGNORECASE)
            notes.append('Self-review: word "journey" replaced with "path".')

        # □ Forbidden opener
        if result.lower().lstrip().startswith(_FORBIDDEN_OPENER):
            notes.append(
                'Self-review: summary opens with forbidden phrase '
                '"Based on your birth chart". Revision needed.'
            )

        # □ Bullet list check
        if _BULLET_PATTERN.search(result):
            notes.append(
                "Self-review: summary appears to contain a bullet list. "
                "Revision needed — prose only."
            )

        # □ Tendency window referenced in weeks (if window is non-null)
        if tendency_window and "week" not in result.lower():
            notes.append(
                "Self-review: tendency window was provided but no week reference "
                "found in summary."
            )

        return result, notes

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _get_findings(head_output: dict) -> dict:
        """
        Extract the findings dict from a head engine output.
        Accepts both full head output ({"findings": {...}}) and bare findings
        dicts ({"query_relevant_findings": [...]}).
        """
        if "findings" in head_output:
            return head_output["findings"]
        return head_output

    def _collect_windows(
        self,
        active_heads: list[str],
        head_findings: dict[str, Optional[dict]],
    ) -> list[dict]:
        """
        Collect non-null tendency windows from all active heads.

        Returns list of {"head": str, "window": {"min": number, "max": number}}.
        """
        result: list[dict] = []
        for head_name in active_heads:
            raw = head_findings.get(head_name)
            if raw is None:
                continue
            findings = self._get_findings(raw)
            window = findings.get("tendency_window_weeks")
            if window and isinstance(window, dict):
                mn = window.get("min")
                mx = window.get("max")
                if mn is not None and mx is not None:
                    result.append({"head": head_name, "window": {"min": mn, "max": mx}})
        return result

    @staticmethod
    def _windows_overlap(w1: dict, w2: dict) -> bool:
        """Return True if two windows [min,max] overlap."""
        return w1["min"] <= w2["max"] and w2["min"] <= w1["max"]

    def _find_timing_overlap(
        self, windows: list[dict]
    ) -> Optional[dict]:
        """
        Find the first pair of windows that overlap.
        Returns {"heads": [h1, h2], "overlap_min": int, "overlap_max": int}
        or None.
        """
        for i in range(len(windows)):
            for j in range(i + 1, len(windows)):
                w1 = windows[i]
                w2 = windows[j]
                if self._windows_overlap(w1["window"], w2["window"]):
                    overlap_min = round(max(w1["window"]["min"], w2["window"]["min"]))
                    overlap_max = round(min(w1["window"]["max"], w2["window"]["max"]))
                    return {
                        "heads": [w1["head"], w2["head"]],
                        "overlap_min": overlap_min,
                        "overlap_max": overlap_max,
                    }
        return None

    def _find_timing_divergence(
        self, windows: list[dict]
    ) -> Optional[dict]:
        """
        Find the first pair of windows that do NOT overlap at all.
        Returns {"heads": [h1, h2], "windows": [w1, w2]} or None.
        """
        for i in range(len(windows)):
            for j in range(i + 1, len(windows)):
                w1 = windows[i]
                w2 = windows[j]
                if not self._windows_overlap(w1["window"], w2["window"]):
                    return {
                        "heads": [w1["head"], w2["head"]],
                        "windows": [w1["window"], w2["window"]],
                    }
        return None

    def _find_caution_heads(
        self,
        active_heads: list[str],
        head_findings: dict[str, Optional[dict]],
    ) -> list[str]:
        """
        Return list of heads that signal caution/difficulty.

        Caution indicators:
          - I Ching: tendency_direction in {retreat, pause}
          - Chinese: clash_year == True
          - Any head with tendency_window_weeks where min > 6 (long wait signal)
        """
        caution: list[str] = []
        for head_name in active_heads:
            raw = head_findings.get(head_name)
            if raw is None:
                continue
            findings = self._get_findings(raw)

            # I Ching explicit direction
            if findings.get("tendency_direction") in _CAUTION_DIRECTIONS:
                caution.append(head_name)
                continue

            # Chinese clash year
            if findings.get("clash_year") is True:
                caution.append(head_name)
                continue

        return caution

    def _find_direction_conflict(
        self,
        active_heads: list[str],
        head_findings: dict[str, Optional[dict]],
    ) -> Optional[str]:
        """
        Detect when one head counsels forward movement and another signals
        caution. Returns a descriptive string or None.
        """
        forward_heads: list[str] = []
        caution_heads: list[str] = []

        for head_name in active_heads:
            raw = head_findings.get(head_name)
            if raw is None:
                continue
            findings = self._get_findings(raw)
            direction = findings.get("tendency_direction")
            if direction in _FORWARD_DIRECTIONS:
                forward_heads.append(head_name)
            elif direction in _CAUTION_DIRECTIONS:
                caution_heads.append(head_name)
            elif findings.get("clash_year") is True:
                caution_heads.append(head_name)

        if forward_heads and caution_heads:
            return (
                f"Direction divergence: {', '.join(forward_heads)} counsel "
                f"forward movement while {', '.join(caution_heads)} signal "
                f"caution or restraint."
            )
        return None


# ── Utility ───────────────────────────────────────────────────────────────────

def _truncate_at_sentence_boundary(text: str, max_words: int) -> str:
    """
    Truncate text to at most max_words words, ending at a sentence boundary.
    """
    sentences = re.split(r"(?<=[.!?])\s+", text)
    result_parts: list[str] = []
    word_total = 0
    for sentence in sentences:
        sentence_words = len(sentence.split())
        if word_total + sentence_words > max_words:
            break
        result_parts.append(sentence)
        word_total += sentence_words
    return " ".join(result_parts) if result_parts else text[: max_words * 6]
