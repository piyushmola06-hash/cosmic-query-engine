"""
S-10 — I Ching Head Engine

Runs only when the user opts in (S-04). Maps a seed word or number to one of
64 hexagrams via a deterministic SHA-256 hash. Applies the hexagram to the
user's query via an LLM call.

Done condition (from spec):
  Seed collection never blocks session. Same seed always produces same
  hexagram. query_application specific to query. Anti-platitude discipline
  applied. Tendency window derived from tendency_direction — never null.
  Trail shows full casting chain.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import unicodedata
from typing import Any, Optional

from heads.iching.hexagrams import HEXAGRAM_BY_NUMBER

logger = logging.getLogger(__name__)

# ── Tendency window mapping ───────────────────────────────────────────────────

TENDENCY_WINDOWS: dict[str, dict] = {
    "forward":   {"min": 2,  "max": 8},
    "pause":     {"min": 4,  "max": 16},
    "retreat":   {"min": 8,  "max": 24},
    "transform": {"min": 6,  "max": 20},
}

# ── LLM system prompt ─────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an I Ching interpreter applying a specific hexagram to the user's query.

Your task is to answer: given this hexagram and this specific question, what
does the I Ching counsel?

QUERY APPLICATION RULES
───────────────────────
1. Engage directly with the intersection of hexagram meaning and the user's
   actual situation. Do not paraphrase the judgment generically.
2. The query_application must be specific to this query. A reading that could
   be given for any query with this hexagram is a contract violation.
3. Name specific aspects of the user's situation and how this hexagram
   illuminates them.
4. query_relevant_findings must each state something the hexagram reveals
   about this specific question — not about the hexagram in general.

ANTI-PLATITUDE RULES — these outputs are FORBIDDEN:
• "Everything happens for a reason"
• "Trust the process"
• "Focus on what you can control" — unless specifying exactly what
• "Let go of what does not serve you" — unless specifying exactly what
• Any reading that applies equally to any user with any hexagram

TEST: Could this reading be given for a completely different question with the
same hexagram and still make sense? If yes — it is generic. Replace it.

OUTPUT FORMAT
─────────────
Return ONLY valid JSON. No prose outside the JSON. No markdown fences.

{
  "query_application": "<specific counsel from this hexagram for this query>",
  "query_relevant_findings": [
    "<first specific finding for this query>",
    "<second specific finding for this query>"
  ]
}
"""

# ── Seed normalisation ────────────────────────────────────────────────────────

def normalise_seed(seed: str) -> tuple[str, bool]:
    """
    Normalise a seed string for hashing.

    Steps:
      1. Lowercase and strip leading/trailing whitespace.
      2. NFKD decomposition to separate combining characters (handles
         diacritics — é becomes e + combining accent, then ASCII-encode
         drops the accent).
      3. Attempt ASCII encoding to produce a clean Latin string.
      4. Strip remaining non-alphanumeric characters.

    Returns:
        (normalised_string, non_latin_detected)

    non_latin_detected is True when non-ASCII characters remained after NFKD
    decomposition — signals that partial transliteration was applied and the
    trail should flag it.
    """
    s = seed.lower().strip()
    s_nfkd = unicodedata.normalize("NFKD", s)

    # Detect non-Latin content before stripping
    non_latin = any(ord(c) > 127 for c in s_nfkd)

    # Strip to ASCII — handles accented Latin; non-Latin becomes empty
    ascii_part = s_nfkd.encode("ascii", "ignore").decode("ascii")
    ascii_clean = re.sub(r"[^a-z0-9]", "", ascii_part)

    if ascii_clean:
        return ascii_clean, non_latin

    # Pure non-Latin (CJK, Arabic, etc.) — use NFKD string as-is for hashing
    # (UTF-8 bytes give deterministic hash; transliteration library not available)
    fallback = re.sub(r"\s+", "", s_nfkd)
    return fallback, True


# ── Seed-to-hexagram mapping ──────────────────────────────────────────────────

def seed_to_hexagram_number(normalised: str) -> tuple[int, bool]:
    """
    Map a normalised seed string to a hexagram number (1–64).

    Uses SHA-256: first 8 hex chars → integer → mod 64 + 1.
    Falls back to Unicode code point sum if hashlib is unavailable.

    Returns:
        (hexagram_number, sha256_fallback_used)
    """
    sha256_fallback = False
    try:
        import hashlib
        digest = hashlib.sha256(normalised.encode("utf-8")).hexdigest()
        integer = int(digest[:8], 16)
    except Exception:
        # Spec fallback: sum of Unicode code points
        integer = sum(ord(c) for c in normalised)
        sha256_fallback = True

    hexagram_number = (integer % 64) + 1
    return hexagram_number, sha256_fallback


# ── Head engine ───────────────────────────────────────────────────────────────

class IChingHeadEngine:
    """
    S-10 I Ching Head Engine.

    Maps a seed to one of 64 hexagrams via a deterministic SHA-256 hash, then
    applies that hexagram to the user's query via an Anthropic LLM call.

    The anthropic_client parameter is injectable to allow tests to provide a
    mock without real API calls.
    """

    def __init__(self, anthropic_client: Optional[Any] = None) -> None:
        """
        Initialise the engine.

        Args:
            anthropic_client: Optional pre-built Anthropic client. If None,
                a real client is created from ANTHROPIC_API_KEY in the
                environment (loaded via python-dotenv if .env is present).
        """
        if anthropic_client is not None:
            self._client = anthropic_client
        else:
            try:
                from dotenv import load_dotenv
                load_dotenv(
                    dotenv_path=os.path.join(
                        os.path.dirname(__file__), "..", "..", "..", ".env"
                    )
                )
            except ImportError:
                pass

            import anthropic as _anthropic
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            self._client = _anthropic.Anthropic(api_key=api_key)

        self._model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")

    # ── Public API ────────────────────────────────────────────────────────────

    def compute(
        self,
        seed: Optional[str | int | float],
        query: Optional[str],
        opted_in: bool = True,
    ) -> dict:
        """
        Compute I Ching findings for the given seed and query.

        Args:
            seed: The user-provided seed word or number. May be empty/None —
                treated as a failure to provide a seed, a random seed is
                generated.
            query: The user's question.
            opted_in: Must be True (the head only runs on opt-in).

        Returns:
            S-10 contract output dict.
        """
        normalised_query = (query or "").strip()

        # ── Seed handling ─────────────────────────────────────────────────────
        seed_str = str(seed).strip() if seed is not None else ""
        random_seed_used = False

        if not seed_str:
            # Spec: empty after two prompts → random seed silently
            seed_str = secrets.token_hex(8)
            random_seed_used = True
            logger.debug("S-10: empty seed — generated random seed")

        # ── Normalise ─────────────────────────────────────────────────────────
        normalised, non_latin = normalise_seed(seed_str)
        if not normalised:
            normalised = secrets.token_hex(8)
            random_seed_used = True

        # ── Hash → hexagram number ─────────────────────────────────────────────
        hexagram_number, sha256_fallback = seed_to_hexagram_number(normalised)

        # ── Hexagram lookup ────────────────────────────────────────────────────
        hexagram = HEXAGRAM_BY_NUMBER.get(hexagram_number)
        if hexagram is None:
            # Spec failure behaviour: fall back to hexagram 1
            logger.error(
                "S-10: hexagram lookup returned None for number %d — falling back to 1",
                hexagram_number,
            )
            hexagram_number = 1
            hexagram = HEXAGRAM_BY_NUMBER[1]

        tendency_direction = hexagram["tendency_direction"]
        tendency_window = TENDENCY_WINDOWS[tendency_direction]

        logger.debug(
            "S-10: seed=%r normalised=%r hexagram=%d %s",
            seed_str, normalised, hexagram_number, hexagram["name_english"],
        )

        # ── LLM call ──────────────────────────────────────────────────────────
        llm_result = self._call_llm(hexagram, normalised_query)

        query_application = llm_result.get("query_application", "")
        query_relevant_findings = llm_result.get("query_relevant_findings", [])

        # ── Build hash snippet for trail ──────────────────────────────────────
        try:
            import hashlib
            digest = hashlib.sha256(normalised.encode("utf-8")).hexdigest()
            hash_snippet = digest[:8]
        except Exception:
            hash_snippet = "(fallback hash)"

        # ── Explainability trail ──────────────────────────────────────────────
        trail_sections = self._build_trail(
            seed_original=seed_str,
            normalised=normalised,
            hash_snippet=hash_snippet,
            hexagram_number=hexagram_number,
            hexagram=hexagram,
            query_application=query_application,
            query_relevant_findings=query_relevant_findings,
            tendency_direction=tendency_direction,
            tendency_window=tendency_window,
            random_seed_used=random_seed_used,
            non_latin=non_latin,
            sha256_fallback=sha256_fallback,
        )

        return {
            "head": "iching",
            "available_findings": [
                "seed_used", "hexagram_number", "hexagram_name_chinese",
                "hexagram_name_english", "image", "judgment", "core_theme",
                "polarity", "tendency_direction", "query_application",
                "query_relevant_findings", "tendency_window_weeks",
            ],
            "unavailable_findings": [],
            "findings": {
                "seed_used": seed_str,
                "hexagram_number": hexagram_number,
                "hexagram_name_chinese": hexagram["name_chinese"],
                "hexagram_name_english": hexagram["name_english"],
                "image": hexagram["image"],
                "judgment": hexagram["judgment"],
                "core_theme": hexagram["core_theme"],
                "polarity": hexagram["polarity"],
                "tendency_direction": tendency_direction,
                "query_application": query_application,
                "query_relevant_findings": query_relevant_findings,
                "tendency_window_weeks": tendency_window,
            },
            "confidence_flag": False,
            "confidence_reason": None,
            "explainability_trail": {
                "label": "I Ching",
                "sections": trail_sections,
            },
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _call_llm(self, hexagram: dict, query: str) -> dict:
        """
        Call the LLM to generate a query-specific application.

        Raises:
            ValueError: If the response cannot be parsed as JSON.
        """
        user_message = (
            f"Hexagram {hexagram['number']}: {hexagram['name_chinese']} "
            f"({hexagram['name_english']})\n"
            f"Image: {hexagram['image']}\n"
            f"Judgment: {hexagram['judgment']}\n"
            f"Core theme: {hexagram['core_theme']}\n\n"
            f"User query: {query or '(no specific question — apply hexagram to the question of how to proceed)'}"
        )

        logger.debug("S-10 LLM call: hexagram=%d query=%r", hexagram["number"], query)

        response = self._client.messages.create(
            model=self._model,
            max_tokens=600,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        raw_text = response.content[0].text.strip()

        logger.debug("S-10 LLM response: %s", raw_text[:200])

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"S-10 LLM response was not valid JSON: {exc}\nRaw: {raw_text[:300]}"
            ) from exc

        return parsed

    @staticmethod
    def _build_trail(
        seed_original: str,
        normalised: str,
        hash_snippet: str,
        hexagram_number: int,
        hexagram: dict,
        query_application: str,
        query_relevant_findings: list,
        tendency_direction: str,
        tendency_window: dict,
        random_seed_used: bool,
        non_latin: bool,
        sha256_fallback: bool,
    ) -> list[dict]:
        """Build the six S-10 explainability trail sections."""

        # Section 1: Seed + hexagram cast (full chain)
        cast_notes: list[str] = []
        if random_seed_used:
            cast_notes.append("No seed provided — random seed generated.")
        if non_latin:
            cast_notes.append(
                "Non-Latin seed detected — NFKD normalisation applied; "
                "limited transliteration used for hashing."
            )
        if sha256_fallback:
            cast_notes.append("SHA-256 unavailable — Unicode code point sum fallback used.")

        cast_content = (
            f"Seed: \"{seed_original}\" "
            f"→ normalised: \"{normalised}\" "
            f"→ SHA-256 first 8 chars: {hash_snippet} "
            f"→ hexagram {hexagram_number}"
        )
        if cast_notes:
            cast_content += " — " + " ".join(cast_notes)

        sections = [
            {
                "title": "Seed + Hexagram Cast",
                "content": cast_content,
                "available": True,
            },
            {
                "title": "Hexagram Identity",
                "content": (
                    f"{hexagram['number']}. {hexagram['name_chinese']} "
                    f"({hexagram['name_english']}) — "
                    f"{hexagram['core_theme']}. "
                    f"Polarity: {hexagram['polarity']}. "
                    f"Domain affinities: {', '.join(hexagram['domain_affinities'])}."
                ),
                "available": True,
            },
            {
                "title": "Image + Judgment",
                "content": (
                    f"Image: {hexagram['image']} "
                    f"Judgment: {hexagram['judgment']}"
                ),
                "available": True,
            },
            {
                "title": "Applied to Your Question",
                "content": query_application,
                "available": bool(query_application),
            },
            {
                "title": "Tendency Direction",
                "content": (
                    f"{tendency_direction.capitalize()}: "
                    f"{tendency_window['min']}–{tendency_window['max']} weeks."
                ),
                "available": True,
            },
            {
                "title": "Query-Relevant Findings",
                "content": (
                    " | ".join(query_relevant_findings)
                    if query_relevant_findings
                    else "No specific findings."
                ),
                "available": bool(query_relevant_findings),
            },
        ]

        return sections
