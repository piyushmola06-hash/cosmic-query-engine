"""
S-09 — Philosophy Head Engine

Applies three philosophical frameworks — Stoicism, Vedanta, and karma theory —
to the user's query. No astronomical calculation. No birth data dependency.
Always runs at full fidelity.

Done condition (from spec):
  All three frameworks produce findings for every query. applied_finding
  specific to the query — never generic. practical_guidance actionable and
  grounded. Anti-platitude rules applied to every output. Tendency window
  always null. Confidence flag always false.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Distress signal keywords ──────────────────────────────────────────────────

_DISTRESS_SIGNALS: frozenset[str] = frozenset({
    'desperate', 'hopeless', 'suicidal', 'depressed', 'anxiety', 'anxious',
    'terrified', 'panic', 'crisis', 'breaking down', 'falling apart',
    'can\'t cope', 'cannot cope', 'overwhelmed', 'unbearable', 'suffering',
    'lost everything', 'end it', 'give up',
})

# ── Query category keywords ───────────────────────────────────────────────────

_CATEGORY_KEYWORDS: dict[str, frozenset[str]] = {
    'career':        frozenset({'career', 'job', 'work', 'business', 'profession', 'vocation',
                                'money', 'finance', 'salary', 'promotion', 'fired', 'quit', 'startup'}),
    'relationships': frozenset({'relationship', 'love', 'marriage', 'partner', 'divorce', 'family',
                                'friend', 'romantic', 'breakup', 'loneliness', 'lonely', 'dating'}),
    'health':        frozenset({'health', 'illness', 'sick', 'disease', 'wellness', 'body',
                                'mental', 'recovery', 'healing', 'diagnosis', 'chronic'}),
    'finances':      frozenset({'debt', 'loan', 'savings', 'invest', 'financial', 'broke', 'wealth'}),
    'travel':        frozenset({'travel', 'move', 'relocate', 'emigrate', 'abroad', 'country'}),
    'direction':     frozenset({'direction', 'purpose', 'meaning', 'path', 'calling', 'goal', 'future'}),
}

# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a philosophical analysis engine applying three frameworks to a user's
specific query. You produce structured, honest, query-specific findings.

FRAMEWORK DEFINITIONS
─────────────────────
Stoicism:
  Central tenet: the dichotomy of control. What is up to us — judgments,
  intentions, responses, chosen actions. What is not up to us — external
  outcomes, other people's choices, circumstances. Virtue (wisdom, justice,
  courage, temperance) is the only genuine good. Indifferents (wealth, health,
  reputation) have preferred and dispreferred forms but are not goods in
  themselves. Key figures: Marcus Aurelius (Meditations), Epictetus
  (Enchiridion), Seneca (Letters). Practice: nightly review, dichotomy
  application, memento mori, amor fati.

Vedanta:
  Central tenet: Brahman (universal consciousness) and Atman (individual self)
  are not ultimately separate. Suffering arises from avidya — misidentifying the
  ego-self as the true self. Liberation (moksha) arises through viveka
  (discrimination between real and unreal), vairagya (non-attachment to
  outcomes), and jnana (direct knowledge). The witness-self observes without
  being touched by circumstance. Key texts: Upanishads, Bhagavad Gita,
  Adi Shankaracharya's commentaries.

Karma theory:
  Three types: sanchita (accumulated past karma, the full store), prarabdha
  (currently ripening — the portion of sanchita bearing fruit in this life,
  not alterable by will alone), agami (being created now by present choices —
  the only karma fully available to influence). Applied findings must name
  which karma type is most relevant and why, not speak of karma generically.

QUERY APPLICATION RULES
───────────────────────
1. Strip any esoteric framing from the query. Identify the core human concern.
2. Apply each framework SPECIFICALLY to that concern. A finding that could
   appear in any reading for any person is a contract violation.
3. applied_finding must name something specific about the user's situation.
4. practical_guidance must specify concrete actions, not orientations.
5. key_distinction must draw a distinction that directly illuminates the query —
   not a general teaching of the framework.

ANTI-PLATITUDE RULES — these outputs are FORBIDDEN:
• "Everything happens for a reason"
• "Trust the process"
• "Focus on what you can control" — unless followed immediately by naming
  exactly what that is in this specific situation
• "Let go of what does not serve you" — unless followed immediately by naming
  exactly what that is
• Any finding that applies equally to any user with any query
• Vague encouragement without actionable content
• Spiritual bypassing — using framework language to avoid the real concern

TEST: Could this finding be copy-pasted into a reading for a completely
different user with a completely different query and still make sense? If yes,
it is a platitude and must be replaced.

EDGE CASE HANDLING
──────────────────
Distress signals: If the query contains signs of acute distress (desperation,
hopelessness, crisis language), ALL three frameworks MUST emphasise grounded
present-moment action: Stoicism → the next single right action available now.
Vedanta → the witness-self is untouched; this moment is survivable as it is.
Karma → agami karma (the karma you can shape now) is the most powerful force
available in this moment. Do not minimise the distress.

Third-party query: If the query is about what another person should do, or
about another person's choices, reframe to the user's OWN relationship to the
situation. The query_theme must note this reframing explicitly.

Life context contradiction: If provided life context contradicts the query
(e.g. query says "I love my job" but context says career trouble), use both.
The contradiction itself may be the most important finding.

OUTPUT FORMAT
─────────────
Return ONLY valid JSON. No prose outside the JSON. No markdown fences.

{
  "query_theme": "<one sentence: the core human concern, noting any reframing>",
  "query_category": "<career|relationships|finances|health|travel|direction|general>",
  "frameworks": {
    "stoicism": {
      "core_principle": "<the specific Stoic principle most relevant to this query>",
      "applied_finding": "<what Stoicism reveals about this specific situation>",
      "key_distinction": "<the distinction that illuminates this query>",
      "practical_guidance": "<specific concrete action the user can take>"
    },
    "vedanta": {
      "core_principle": "<the specific Vedantic principle most relevant>",
      "applied_finding": "<what Vedanta reveals about this specific situation>",
      "key_distinction": "<the Vedantic distinction that applies here>",
      "practical_guidance": "<specific concrete action or inquiry>"
    },
    "karma": {
      "core_principle": "<which karma type is most relevant and why>",
      "applied_finding": "<what karma theory reveals about this situation>",
      "key_distinction": "<the karma distinction that matters most here>",
      "practical_guidance": "<specific action that shapes agami karma now>"
    }
  },
  "convergence": "<string: where all three frameworks agree, or null>",
  "divergence": "<string: where the frameworks diverge meaningfully, or null>",
  "query_relevant_findings": [
    "<most important finding for this query>",
    "<second most important finding>"
  ]
}
"""

# ── Head engine ───────────────────────────────────────────────────────────────


class PhilosophyHeadEngine:
    """
    S-09 Philosophy Head Engine.

    Applies Stoicism, Vedanta, and karma theory to the user's query via an
    Anthropic LLM call. Always runs at full fidelity — no birth data required.

    The anthropic_client parameter is injectable to allow tests to provide a
    mock client without making real API calls.
    """

    def __init__(self, anthropic_client: Optional[Any] = None) -> None:
        """
        Initialise the engine.

        Args:
            anthropic_client: Optional pre-built Anthropic client. If None, a
                real client is created using ANTHROPIC_API_KEY from the
                environment (loaded via python-dotenv if .env is present).
        """
        if anthropic_client is not None:
            self._client = anthropic_client
        else:
            # Lazy import so tests that inject a mock never need the real key.
            try:
                from dotenv import load_dotenv
                load_dotenv(
                    dotenv_path=os.path.join(
                        os.path.dirname(__file__), '..', '..', '..', '.env'
                    )
                )
            except ImportError:
                pass  # python-dotenv not installed — rely on env already set

            import anthropic as _anthropic
            api_key = os.environ.get('ANTHROPIC_API_KEY')
            model = os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-4-5')
            self._client = _anthropic.Anthropic(api_key=api_key)
            self._model = model

        # Resolve model — may be overridden by env even when client is injected
        self._model = os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-4-5')

    # ── Public API ────────────────────────────────────────────────────────────

    def compute(
        self,
        query: Optional[str],
        life_context: Optional[dict] = None,
    ) -> dict:
        """
        Compute philosophy findings for the given query.

        Args:
            query: The user's question. May be None — treated as seeking
                guidance itself (spec failure behaviour).
            life_context: Optional dict with keys career, relationships,
                health, other — each a string or None.

        Returns:
            S-09 contract output dict.
        """
        normalised_query = (query or '').strip()
        has_distress = self._detect_distress(normalised_query)

        user_message = self._build_user_message(normalised_query, life_context, has_distress)

        logger.debug(
            'S-09 PhilosophyHeadEngine.compute called',
            extra={'query': normalised_query, 'has_distress': has_distress},
        )

        raw_findings = self._call_llm(user_message)

        logger.debug(
            'S-09 LLM response received',
            extra={'raw_findings': raw_findings},
        )

        return self._build_output(raw_findings)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _detect_distress(self, query: str) -> bool:
        """Return True if the query contains distress signals."""
        lower = query.lower()
        return any(signal in lower for signal in _DISTRESS_SIGNALS)

    def _build_user_message(
        self,
        query: str,
        life_context: Optional[dict],
        has_distress: bool,
    ) -> str:
        """Compose the user-turn message to send to the LLM."""
        parts: list[str] = []

        if query:
            parts.append(f"User query: {query}")
        else:
            parts.append("User query: (no query provided — apply all frameworks to the act of seeking guidance itself)")

        if life_context:
            context_parts: list[str] = []
            for field in ('career', 'relationships', 'health', 'other'):
                value = life_context.get(field)
                if value:
                    context_parts.append(f"  {field}: {value}")
            if context_parts:
                parts.append("Life context:\n" + "\n".join(context_parts))

        if has_distress:
            parts.append(
                "DISTRESS SIGNAL DETECTED: All three frameworks must emphasise "
                "grounded present-moment action above all else. Do not minimise "
                "the difficulty. Apply the specific distress guidance rules."
            )

        return "\n\n".join(parts)

    def _call_llm(self, user_message: str) -> dict:
        """
        Make the Anthropic API call and parse the JSON response.

        Raises:
            ValueError: If the response cannot be parsed as valid JSON or is
                missing required fields.
            anthropic.APIError: On API-level failures.
        """
        response = self._client.messages.create(
            model=self._model,
            max_tokens=1200,
            system=_SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': user_message}],
        )

        raw_text = response.content[0].text.strip()

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"S-09 LLM response was not valid JSON: {exc}\nRaw: {raw_text[:300]}"
            ) from exc

        return parsed

    def _build_output(self, llm_data: dict) -> dict:
        """Map the LLM-parsed dict to the full S-09 contract output shape."""
        frameworks_raw = llm_data.get('frameworks', {})

        def _framework(name: str) -> dict:
            fw = frameworks_raw.get(name, {})
            return {
                'core_principle': fw.get('core_principle', ''),
                'applied_finding': fw.get('applied_finding', ''),
                'key_distinction': fw.get('key_distinction', ''),
                'practical_guidance': fw.get('practical_guidance', ''),
            }

        query_theme = llm_data.get('query_theme', '')
        query_category = llm_data.get('query_category', 'general')
        convergence = llm_data.get('convergence') or None
        divergence = llm_data.get('divergence') or None
        query_relevant = llm_data.get('query_relevant_findings', [])

        trail_sections = self._build_trail(
            query_theme,
            _framework('stoicism'),
            _framework('vedanta'),
            _framework('karma'),
            convergence,
            divergence,
        )

        return {
            'head': 'philosophy',
            'available_findings': [
                'query_theme', 'query_category', 'stoicism',
                'vedanta', 'karma', 'convergence', 'divergence',
            ],
            'unavailable_findings': [],
            'findings': {
                'query_theme': query_theme,
                'query_category': query_category,
                'frameworks': {
                    'stoicism': _framework('stoicism'),
                    'vedanta':  _framework('vedanta'),
                    'karma':    _framework('karma'),
                },
                'convergence': convergence,
                'divergence': divergence,
                'query_relevant_findings': query_relevant,
                'tendency_window_weeks': None,  # Philosophy has no time mechanism
            },
            'confidence_flag': False,  # Always false per spec
            'confidence_reason': None,
            'explainability_trail': {
                'label': 'Philosophy',
                'sections': trail_sections,
            },
        }

    @staticmethod
    def _build_trail(
        query_theme: str,
        stoicism: dict,
        vedanta: dict,
        karma: dict,
        convergence: Optional[str],
        divergence: Optional[str],
    ) -> list[dict]:
        """Build the explainability trail sections."""
        sections = [
            {
                'title': 'Query Theme',
                'content': query_theme,
                'available': bool(query_theme),
            },
            {
                'title': 'Stoicism',
                'content': (
                    f"{stoicism['core_principle']} — "
                    f"{stoicism['applied_finding']} "
                    f"Guidance: {stoicism['practical_guidance']}"
                ),
                'available': bool(stoicism.get('applied_finding')),
            },
            {
                'title': 'Vedanta',
                'content': (
                    f"{vedanta['core_principle']} — "
                    f"{vedanta['applied_finding']} "
                    f"Guidance: {vedanta['practical_guidance']}"
                ),
                'available': bool(vedanta.get('applied_finding')),
            },
            {
                'title': 'Karma Theory',
                'content': (
                    f"{karma['core_principle']} — "
                    f"{karma['applied_finding']} "
                    f"Guidance: {karma['practical_guidance']}"
                ),
                'available': bool(karma.get('applied_finding')),
            },
        ]
        if convergence:
            sections.append({
                'title': 'Convergence',
                'content': convergence,
                'available': True,
            })
        if divergence:
            sections.append({
                'title': 'Divergence',
                'content': divergence,
                'available': True,
            })
        return sections
