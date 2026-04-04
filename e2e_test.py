"""
End-to-end system test - all 6 head engines active.
Runs all 12 API steps for the Piyush Kumar Mola test profile.
Uses a mock Anthropic client because API credits are not available.
"""

import json
import os
import sys
import time
from pathlib import Path

# -- Django setup --------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ["ANTHROPIC_API_KEY"] = "mock-key-no-credits"
os.environ["ALLOWED_HOSTS"] = "testserver,localhost,127.0.0.1"
os.environ["DEBUG"] = "true"

import django
from django.conf import settings
django.setup()
# Ensure testserver is in ALLOWED_HOSTS at runtime
if "testserver" not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS.append("testserver")

# -- Mock Anthropic client (no credits available) ------------------------------

PHILOSOPHY_MOCK_JSON = json.dumps({
    "query_theme": "career crossroads - employment security vs entrepreneurial agency",
    "query_category": "career",
    "frameworks": {
        "stoicism": {
            "core_principle": "Dichotomy of control - focus only on what lies within your power.",
            "applied_finding": "The fear of business failure is an external outcome, not within your control. What is within your control is the quality of preparation, the discipline of execution, and the integrity of the attempt.",
            "key_distinction": "Security is not the absence of risk - it is the presence of self-mastery.",
            "practical_guidance": "Audit what you fear about starting the business. Separate the fears that point to genuine preparation gaps from those that are merely discomfort with uncertainty."
        },
        "vedanta": {
            "core_principle": "The nature of the self (Atman) is not defined by occupation or title.",
            "applied_finding": "Attachment to the identity of 'employee' or 'entrepreneur' creates suffering. The crossroads is an invitation to inquire: who is the one choosing?",
            "key_distinction": "Action from dharma (right duty) is qualitatively different from action from fear.",
            "practical_guidance": "Meditate on whether the pull toward business comes from creative dharma or from ego dissatisfaction with the current situation."
        },
        "karma": {
            "core_principle": "Present action plants seeds whose fruit is not always visible immediately.",
            "applied_finding": "A period of Saturn's dasha typically brings structured discipline - not sudden leaps but measured construction. This is a time to build foundations, not gamble.",
            "key_distinction": "The crossroads is not a binary - it may be asking you to prepare thoroughly now so the business launch comes from strength, not desperation.",
            "practical_guidance": "Use the current employment as a funded runway to develop the business's core proposition. The karma of careful preparation yields more stable results than impulsive departure."
        }
    },
    "convergence": "All three frameworks note that this is a moment for honest self-examination rather than reactive decision. The crossroads is real but not urgent.",
    "divergence": "Stoicism emphasises action despite uncertainty; Vedanta suggests the identity question precedes the career question; Karma cautions patience during a structurally demanding period.",
    "query_relevant_findings": [
        {"framework": "stoicism", "finding": "Preparation gaps are within your control; outcomes are not."},
        {"framework": "karma", "finding": "Saturn dasha favours structured construction over sudden leaps."}
    ]
})

ICHING_MOCK_JSON = json.dumps({
    "line_interpretation": "The hexagram reveals a moment of gathering strength before decisive movement. The situation is not yet ripe for an abrupt departure. Consolidation serves better than expansion at this time.",
    "query_application": "The business impulse is genuine and the direction is correct - but the timing and preparation require further development. The hexagram counsels: do not force what must mature naturally.",
    "tendency_direction": "pause",
    "key_symbols": ["water gathering before it flows", "the seed before it germinates", "the bow being drawn before release"]
})

SYNTHESIS_MOCK = (
    "The combined reading across six systems presents a coherent, if uncomfortable, picture. "
    "Numerology places you in a structurally demanding personal year, and the Chinese Four Pillars confirm "
    "a period requiring steady construction rather than abrupt transition. Vedic astrology's current dasha "
    "reinforces this - the planetary period active now rewards disciplined preparation and penalises "
    "impulsive action. Western astrology adds that Saturn's current transit presses on your natal chart "
    "in ways that demand accountability and realistic planning before any major change.\n\n"
    "The I Ching and Philosophy heads both read the crossroads the same way: the question is not whether "
    "to start the business, but when and from what foundation. The honest finding across systems is that "
    "the pull toward entrepreneurship is real and directionally sound - but the conditions as they stand "
    "point to a preparation phase, not a launch phase. Use the security of current employment as runway. "
    "The decision to leave should come from a completed plan, not from dissatisfaction."
)


class _MockContent:
    def __init__(self, text: str) -> None:
        self.text = text


class _MockResponse:
    def __init__(self, text: str) -> None:
        self.content = [_MockContent(text)]


class _MockMessages:
    """Returns contextually appropriate mock responses based on the system prompt."""

    def create(self, *, model: str, max_tokens: int,
               messages: list, system: str = "", **kwargs) -> _MockResponse:
        prompt_lower = system.lower()
        # Synthesis check first — its prompt contains "i ching" as an example
        if "synthesis engine" in prompt_lower or "writing rules" in prompt_lower:
            return _MockResponse(SYNTHESIS_MOCK)
        if "philosophy" in prompt_lower or "stoic" in prompt_lower or "vedanta" in prompt_lower:
            return _MockResponse(PHILOSOPHY_MOCK_JSON)
        if "i ching" in prompt_lower or "iching" in prompt_lower or "hexagram" in prompt_lower:
            return _MockResponse(ICHING_MOCK_JSON)
        # Fallback
        return _MockResponse(SYNTHESIS_MOCK)


class MockAnthropicClient:
    def __init__(self) -> None:
        self.messages = _MockMessages()


# -- Patch the client into every service that uses it -------------------------

mock_client = MockAnthropicClient()

from heads.philosophy.services import PhilosophyHeadEngine
from heads.iching.services import IChingHeadEngine
from synthesis.services import SynthesisLayer

_orig_phil_init = PhilosophyHeadEngine.__init__
_orig_iching_init = IChingHeadEngine.__init__
_orig_synth_init = SynthesisLayer.__init__


def _phil_init(self, anthropic_client=None, **kw):
    _orig_phil_init(self, anthropic_client=mock_client, **kw)


def _iching_init(self, anthropic_client=None, **kw):
    _orig_iching_init(self, anthropic_client=mock_client, **kw)


def _synth_init(self, anthropic_client=None, **kw):
    _orig_synth_init(self, anthropic_client=mock_client, **kw)


PhilosophyHeadEngine.__init__ = _phil_init
IChingHeadEngine.__init__ = _iching_init
SynthesisLayer.__init__ = _synth_init

# -- In-process API calls ------------------------------------------------------

from api.views import CollectView, QueryView, SessionEndView, SessionStartView, TrailView


from django.test import Client as DjangoClient

_client = DjangoClient()


def _post(view_class, path, data):
    """Make an in-process POST via Django test client (handles DRF renderer)."""
    url = path
    resp = _client.post(url, data=json.dumps(data), content_type="application/json")
    try:
        body = json.loads(resp.content)
    except Exception:
        body = {"raw": resp.content.decode(errors="replace")}
    return resp.status_code, body


# -- Printer -------------------------------------------------------------------

_SEP = "-" * 72


def _print_step(step_num: int, title: str, status: int, data: dict,
                elapsed: float) -> None:
    print(f"\n{_SEP}")
    print(f"STEP {step_num}: {title}  [{status}]  ({elapsed*1000:.0f} ms)")
    print(_SEP)
    print(json.dumps(data, indent=2, ensure_ascii=False))


# -- Main test -----------------------------------------------------------------

def run():
    total_start = time.perf_counter()
    print("\n" + "=" * 72)
    print("  COSMIC QUERY ENGINE - END-TO-END TEST")
    print("  Profile: Piyush Kumar Mola | Born: 06 Feb 1988, 10:40 PM, Cuttack")
    print("  Mock LLM client: ON (no API credits)")
    print("=" * 72)

    head_status: dict[str, str] = {}

    # -- STEP 1: Start session -------------------------------------------------
    t = time.perf_counter()
    sc, resp = _post(SessionStartView, "/session/start/", {"user_identifier": "test-user-e2e-001"})
    _print_step(1, "POST /session/start/", sc, resp, time.perf_counter() - t)
    assert sc == 201, f"Expected 201, got {sc}"
    session_id = resp["session_id"]
    print(f"\n  -> session_id: {session_id}")

    # -- Collection messages ---------------------------------------------------
    # Sequence mirrors the S-01 data collection flow.
    collect_steps = [
        (2, "Query (career crossroads)",
         "I am at a crossroads in my career. Should I start my own business or stay in my current job?"),
        (3, "I Ching opt-in -> yes",       "yes"),
        (4, "Date of birth",              "06 February 1988"),
        (5, "DOB confirm -> yes",          "yes"),
        (6, "Birth time",                 "10:40 PM"),
        (7, "Birth time confirm -> yes",   "yes"),
        (8, "Birth city",                 "Cuttack"),
        (9, "Country (if asked)",         "India"),
        (10, "Location confirm -> yes",    "yes"),
        (11, "Full birth name",           "Piyush Kumar Mola"),
        (12, "Current name -> skip",       "skip"),
        (13, "Gender -> skip",             "skip"),
    ]

    collection_complete = False
    step_offset = 0

    for idx, (step_num, label, message) in enumerate(collect_steps):
        if collection_complete:
            break

        t = time.perf_counter()
        sc, resp = _post(CollectView, f"/session/{session_id}/collect/",
                         {"message": message})
        elapsed = time.perf_counter() - t

        _print_step(step_num, f"POST /collect/ - {label}", sc, {
            "sent": message,
            "system_message": resp.get("system_message", resp),
            "input_hint": resp.get("input_hint"),
            "quick_replies": resp.get("quick_replies"),
            "collection_complete": resp.get("collection_complete", False),
        }, elapsed)

        if sc not in (200, 201):
            print(f"  x Unexpected status {sc} - {resp}")
            if resp.get("error"):
                continue

        if resp.get("collection_complete"):
            collection_complete = True
            print(f"\n  + Collection complete after step {step_num}")
            step_offset = len(collect_steps) - idx - 1
            break

    query_step = 14
    trail_step = 15
    end_step = 16

    # -- STEP query: Run query -------------------------------------------------
    print(f"\n{_SEP}")
    print(f"STEP {query_step}: POST /session/{{id}}/query/")
    print(_SEP)
    print("  Query: \"Should I start my own business?\"")
    print("  Running all 6 head engines + synthesis...")
    print("  [This is the main computation step]\n")

    t = time.perf_counter()
    sc, resp = _post(QueryView, f"/session/{session_id}/query/",
                     {"query": "Should I start my own business or stay in my current job?"})
    elapsed = time.perf_counter() - t

    print(f"Status: {sc}  ({elapsed*1000:.0f} ms)\n")

    if sc == 200:
        summary = resp.get("summary", "")
        print("-- SYNTHESIS SUMMARY ----------------------------------------------")
        print(summary)
        print("-------------------------------------------------------------------")
        conf = resp.get("confidence_note")
        if conf:
            print(f"\nConfidence note: {conf}")
        tw = resp.get("tendency_window")
        if tw:
            print(f"Tendency window: {tw}")
        print(f"\nQuery index: {resp.get('query_index')}")
    else:
        print(json.dumps(resp, indent=2, ensure_ascii=False))

    # Pull head-level results from session for reporting
    from core.models import SessionContext
    session_obj = SessionContext.objects.get(session_id=session_id)
    queries = session_obj.queries or []
    if queries:
        last_q = queries[-1]
        head_findings = last_q.get("head_findings", {})
        print(f"\n-- HEAD ENGINE RESULTS ---------------------------------------------")
        for head_name in ["vedic", "western", "numerology", "chinese", "philosophy", "iching"]:
            findings = head_findings.get(head_name)
            if findings is None:
                if head_name in (session_obj.active_heads or []):
                    head_status[head_name] = "ERROR (returned None)"
                    print(f"  {head_name:12s}: x ERROR - returned None")
                else:
                    head_status[head_name] = "NOT ACTIVE"
                    print(f"  {head_name:12s}: - not in active_heads")
            else:
                conf_flag = findings.get("confidence_flag", False)
                conf_reason = findings.get("confidence_reason", "")
                avail = findings.get("available_findings", [])
                unavail = findings.get("unavailable_findings", [])
                head_status[head_name] = "OK" + (" [confidence_flag]" if conf_flag else "")
                print(f"  {head_name:12s}: + OK | available={avail} | unavailable={unavail}")
                if conf_flag and conf_reason:
                    print(f"              confidence: {conf_reason[:100]}")

                # Print key findings per head
                f = findings.get("findings", {})
                if head_name == "vedic":
                    print(f"              rashi={f.get('rashi')} | nakshatra={f.get('nakshatra')} "
                          f"pada={f.get('nakshatra_pada')} | lagna={f.get('lagna')} "
                          f"(available={f.get('lagna_available')})")
                    cd = f.get("current_dasha")
                    if cd:
                        print(f"              dasha={cd.get('planet')} until {cd.get('end_date')}")
                    ad = f.get("current_antardasha")
                    if ad:
                        print(f"              antardasha={ad.get('planet')} until {ad.get('end_date')}")
                    pp = f.get("planetary_positions", {})
                    print(f"              planets: sun={pp.get('sun')} moon={pp.get('moon')} "
                          f"mars={pp.get('mars')} jup={pp.get('jupiter')} sat={pp.get('saturn')}")
                    print(f"              tendency_window={f.get('tendency_window_weeks')}")

                elif head_name == "western":
                    print(f"              sun={f.get('sun_sign')} ({'' if f.get('sun_sign_certain') else 'uncertain'}) "
                          f"| moon={f.get('moon_sign')} | rising={f.get('rising_sign')} "
                          f"(available={f.get('rising_sign_available')})")
                    print(f"              mc={f.get('midheaven')} | chart_pattern={f.get('chart_pattern')}")
                    aspects = f.get("aspects", [])
                    if aspects:
                        print(f"              top aspect: {aspects[0].get('planet1')} "
                              f"{aspects[0].get('aspect')} {aspects[0].get('planet2')} "
                              f"(orb {aspects[0].get('orb')}°)")
                    print(f"              tendency_window={f.get('tendency_window_weeks')}")

                elif head_name == "numerology":
                    print(f"              life_path={f.get('life_path_number')} | "
                          f"expression={f.get('expression_number')} | "
                          f"personal_year={f.get('personal_year')}")

                elif head_name == "chinese":
                    print(f"              animal={f.get('zodiac_animal')} | "
                          f"element={f.get('zodiac_element')} | "
                          f"clash_year={f.get('clash_year')} | "
                          f"ben_ming_nian={f.get('ben_ming_nian', False)}")

                elif head_name == "philosophy":
                    fw = f.get("frameworks", {})
                    print(f"              query_theme={f.get('query_theme', '')[:60]}")
                    if "stoicism" in fw:
                        print(f"              stoicism: {fw['stoicism'].get('practical_guidance','')[:80]}")

                elif head_name == "iching":
                    print(f"              hexagram={f.get('hexagram_number')} ({f.get('hexagram_name_english','')})")
                    print(f"              tendency_direction={f.get('tendency_direction')}")
                    qrf = f.get("query_relevant_findings", [])
                    if qrf:
                        print(f"              finding: {qrf[0].get('finding','')[:80]}")

    # -- STEP trail ------------------------------------------------------------
    print(f"\n{_SEP}")
    print(f"STEP {trail_step}: POST /session/{{id}}/trail/")
    print(_SEP)

    t = time.perf_counter()
    sc, resp = _post(TrailView, f"/session/{session_id}/trail/",
                     {"user_requested": True})
    elapsed = time.perf_counter() - t
    print(f"Status: {sc}  ({elapsed*1000:.0f} ms)\n")

    if resp.get("rendered"):
        trail = resp.get("trail", [])
        print(f"Trail rendered: {len(trail)} head(s)\n")
        for head_trail in trail:
            head_label = head_trail.get("label", "unknown")
            sections = head_trail.get("sections", [])
            avail_count = sum(1 for s in sections if s.get("available"))
            unavail_count = len(sections) - avail_count
            print(f"  > {head_label}")
            print(f"    sections: {len(sections)} total, {avail_count} available, {unavail_count} unavailable")
            for s in sections:
                avail_marker = "+" if s.get("available") else "x"
                content_preview = s.get("content", "")[:70].replace("\n", " ")
                # Sanitize non-ASCII for Windows cp1252 terminals
                content_preview = content_preview.encode("ascii", errors="replace").decode("ascii")
                title_safe = s.get("title", "").encode("ascii", errors="replace").decode("ascii")
                print(f"    [{avail_marker}] {title_safe}: {content_preview}")
    else:
        print(json.dumps(resp, indent=2, ensure_ascii=False))

    # -- STEP end --------------------------------------------------------------
    print(f"\n{_SEP}")
    print(f"STEP {end_step}: POST /session/{{id}}/end/")
    print(_SEP)

    t = time.perf_counter()
    sc, resp = _post(SessionEndView, f"/session/{session_id}/end/",
                     {})
    elapsed = time.perf_counter() - t
    print(f"Status: {sc}  ({elapsed*1000:.0f} ms)\n")
    print(json.dumps(resp, indent=2, ensure_ascii=False))

    # -- SUMMARY ---------------------------------------------------------------
    total_elapsed = time.perf_counter() - total_start
    print(f"\n{'=' * 72}")
    print("  PIPELINE SUMMARY")
    print(f"{'=' * 72}")
    print(f"\n  Total wall time: {total_elapsed:.2f}s\n")
    print("  Head engine results:")
    for head_name in ["vedic", "western", "numerology", "chinese", "philosophy", "iching"]:
        status_str = head_status.get(head_name, "NOT ACTIVE")
        marker = "+" if status_str.startswith("OK") else ("x" if "ERROR" in status_str else "-")
        print(f"    {marker}  {head_name:12s}  {status_str}")

    ok_count = sum(1 for v in head_status.values() if v.startswith("OK"))
    err_count = sum(1 for v in head_status.values() if "ERROR" in v)
    print(f"\n  {ok_count} heads succeeded | {err_count} heads errored")
    print(f"\n  Summary contained: {len(SYNTHESIS_MOCK)} characters across 2 paragraphs")
    print(f"  (Mock LLM used - live Anthropic API would produce dynamic content)")
    print(f"{'=' * 72}\n")


if __name__ == "__main__":
    run()
