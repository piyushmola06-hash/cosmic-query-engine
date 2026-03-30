# Cosmic Query Engine — Feature Spec

---

## Changelog

| Version | Description |
|---------|-------------|
| v0.5 | Added Phase 4 multi-surface specs, cascade map, conversation architecture decision, input_hint field, multi-query session limit, Swiss Ephemeris dependency note |
| v0.4 | Initial spec complete — all slice contracts, data model, design philosophy, session behaviour |

---

## Design Philosophy

Transparency-first, never-block. When data is missing or uncertain, the system proceeds with whatever is available and communicates degradation honestly. It never silently fails, never silently guesses, never refuses to run due to incomplete input. All active heads contribute equally to synthesis regardless of data fidelity. The reading experience stays clean — caveats surface separately, never embedded in findings.

---

## Problem

The user wants to ask questions about their future or life direction and receive a grounded, honest reading drawn from multiple esoteric and philosophical frameworks — without the system guessing, flattering, or hallucinating.

---

## Knowledge Heads

Five heads run automatically on every query: Vedic astrology, Western astrology, Numerology, Chinese astrology, and Philosophy (Stoicism, Vedanta, karma). A sixth head — I Ching — is optional. At session start, the system asks the user whether to include it. If yes, it runs its own interaction workflow during data collection and its findings merge into synthesis equally with the other heads. If no, it is skipped entirely.

**v0.1 scope:** I Ching only. Tarot deferred to v0.2. Changing lines and moving hexagram deferred to v0.2. v0.1 produces a single primary hexagram from a deterministic seed hash — same seed always produces same hexagram across sessions.

**Philosophy head role:** The Philosophy head is the only head that engages directly with the user's query as a human question rather than as a data input. It applies Stoicism, Vedanta, and karma theory specifically to the query — never generically. Its findings anchor the synthesis layer when other heads have degraded data, and its convergence and divergence fields surface genuine agreements and tensions across frameworks. Generic or platitudinous output from this head is a system failure, not an acceptable degradation.

**Vedic vs Western distinction:** Vedic and Western astrology measure different things and must not be treated as redundant by the synthesis layer. Vedic's primary identity marker is the moon sign (rashi). Western's is the sun sign. Vedic time-based predictions derive from the Vimshottari dasha sequence fixed at birth. Western time-based predictions derive from current outer planet transits against the natal chart. Both produce tendency windows in weeks but from fundamentally different mechanisms — the synthesis layer treats their outputs as complementary, not confirmatory.

**Universal signals:** Certain findings across heads are considered significant enough to always surface in query-relevant findings regardless of query domain. These are: Numerology personal year 9 (completion year), Chinese astrology clash year, and Chinese astrology ben ming nian (return year). The synthesis layer treats these as priority signals when present.

**Dual system (Numerology):** The Numerology head computes the Expression number using both Pythagorean and Chaldean systems. Where they produce the same result, a single value is surfaced. Where they diverge, both values are shown and the divergence is noted. All other numbers use Pythagorean only. Personal year 9 is always surfaced in query-relevant findings regardless of query domain.

**Chinese calendar conversion:** The Chinese zodiac year is determined by the lunisolar calendar, not the Gregorian year. Users born between January 1 and Chinese New Year's date of their birth year belong to the previous zodiac year. This conversion is mandatory — Gregorian year is never used directly for zodiac determination.

**Query relevance mapping (Vedic):** The Vedic head selects query-relevant findings based on the domain of the user's query — career, relationships, finances, health, travel, or general direction. If the query spans multiple domains, the top three most relevant findings across domains are surfaced. If no domain is identified, the current dasha, antardasha, rashi, and nakshatra are used as defaults.

---

## Shared Data Pool

Collected once at session start, used by all active heads:

- Full date of birth
- Birth time (tiered — see below)
- Birth city + country
- Full birth name as on birth certificate
- Current name if different
- Gender (optional)
- The user's query

---

## Data Collection Sequence

Query → I Ching opt-in → date of birth → birth time → birth city + country → full birth name → current name (optional) → gender (optional).

Order is fixed. No field is re-asked if already provided earlier in the conversation.

**I Ching opt-in:** Offered at step 2 of every session, immediately after the user submits their query. Phrasing and presentation are identical regardless of query type. The system never decides contextually whether to offer or suppress it.

---

## Birth Time Tiers

- **Exact time provided** → full reading including ascendant and house-based predictions
- **Approximate time provided** (e.g. "morning", "after sunset") → system maps to a 3-hour window, proceeds with reduced confidence on ascendant and house readings, warns user explicitly that those findings carry lower certainty
- **No time provided** → system proceeds without ascendant or house-based readings, warns user clearly which findings are unavailable and why

Birth time rectification is out of scope for v0.1.

**Hedged time expressions:** If the user provides a specific time but qualifies it with uncertainty (e.g. "I think", "maybe", "not sure", "around"), the system treats the input as approximate tier regardless of the specificity of the time given. The stated time is used as the centre of a 2-hour window.

---

## Moon Sign Ambiguity

When birth time is unknown and the moon transitions signs on the user's birth date, the system uses the sign the moon occupied for the majority of that day. No question is asked. The confidence note flags this.

**Location-sensitive calculation:** Moon sign transitions are calculated in local time at the birth location, not UTC. Birth city + country is required for accurate transition timing. If location cannot be resolved, UTC is used as a fallback and flagged in the confidence note.

**Approximate tier and moon signs:** The majority-day rule is applied only when the birth time window genuinely overlaps a sign transition. If the window falls entirely before or after the transition, the moon sign is assigned with full certainty regardless of tier.

---

## Birth Location

System asks for city + country in plain text. Coordinates resolved internally. Never asks the user for coordinates.

---

## Per-Head Data Requirements

**Vedic astrology** → full DOB, birth time (tiered), birth city + country. Optional: gender.

**Western astrology** → full DOB, birth time (tiered), birth city + country. Degrades identically to Vedic when birth time is missing.

**Numerology** → full birth name as on birth certificate, full DOB. Optional: current name if changed.

**Chinese astrology** → birth year, month, day. Optional: birth hour (enables Four Pillars). Without birth hour: zodiac animal reading only, no Four Pillars.

**Philosophy** → user query only. Optional: life context (career, relationships, health). Always runs at full fidelity.

**I Ching** → user opt-in at session start. Runs seed-based interaction workflow during data collection. Skipped entirely if not opted in.

---

## Synthesis Weighting

All active heads contribute equally. Degraded heads are never silently suppressed — their contribution is equal, their reduced fidelity is disclosed.

**Synthesis process:** The summary is produced by detecting convergence signals across all active head findings, qualifying with divergence signals where present, and anchoring universal signals (personal year 9, clash year, ben ming nian) as priority content. The summary is never a per-head list. It reads as a considered judgment from all active systems speaking together. Every sentence must reference at least one specific finding from the working set — generic sentences are removed before output is returned.

---

## Output Format

1–2 paragraphs, max 500 words each, synthesising all active heads. Tone is direct, no false optimism. Predictions expressed as tendencies with a date range in weeks — never fixed-date certainties. On request, user can expand the explainability trail to see each head's individual finding.

**Tendency windows:** All time-based findings across all heads are expressed as a minimum and maximum week range derived from the head's own calculations. Fixed dates are never used. If a head cannot derive a tendency window from its available data, it returns null for that field — the synthesis layer omits time references for that head rather than guessing.

---

## Confidence Notes

A single consolidated note appears directly below the summary when any head operates at reduced fidelity. Names affected findings in plain language. The summary itself is never interrupted.

---

## Session Behaviour

Context retained within session, cleared on session end. Individual queries only — no group or family readings.

**Multi-query limit:** A maximum of three queries per session. After the third query the system informs the user the session has reached its limit and offers to end the session and start a new one.

At session end, system asks whether to save the profile. If yes, birth data stored and confirmed on return. If no, discarded. No silent saving.

---

## Constraints

- Refuses sexually explicit or profane requests
- When confidence is low, asks for more data rather than proceeding
- Does not express certainty it does not have
- Additional constraints to be added in future versions

---

## Infrastructure Dependencies

**Swiss Ephemeris:** The system depends on Swiss Ephemeris for all astronomical calculations. This library must be selected, integrated, and validated before any head engine implementation begins. It is the single most important infrastructure dependency in the system.

**LLM dependency:** S-09 (Philosophy), S-10 (I Ching query application), and S-11 (Synthesis) require LLM calls to generate natural language output from structured findings. These calls must be made server-side — never from a client.

**I Ching lookup table:** The 64 hexagram records — name, image, judgment, core theme, domain affinities, polarity, tendency direction — are curated static content that must be authored and reviewed before S-10 can be built or tested. This is a content task, not a code task, and should be completed before the S-10 implementation sprint begins.

---

---

# Slice Contracts

---

## S-01 — Data Collection Layer

**Spec reference:** Shared data pool, Birth time tiers, Birth location, Per-head data requirements

**What this slice does**
Collects all user data required by active heads at session start, before any query is processed. Asks questions in plain language, one logical group at a time. Never asks for the same data twice. Tolerates malformed or out-of-order input gracefully — rephrases and re-asks rather than failing.

**Inputs**
Raw conversational user responses — any format, any order.

**Outputs**
```json
{
  "query": "string",
  "tarot_opted_in": "boolean",
  "dob": { "day": "number", "month": "number", "year": "number" },
  "birth_time": {
    "tier": "exact | approximate | none",
    "value": "HH:MM | morning | evening | afternoon | night | null",
    "window_start": "HH:MM | null",
    "window_end": "HH:MM | null"
  },
  "birth_location": { "city": "string", "country": "string" },
  "full_birth_name": "string",
  "current_name": "string | null",
  "gender": "string | null",
  "active_heads": ["vedic", "western", "numerology", "chinese", "philosophy", "iching?"]
}
```

**Question sequence**
1. User's query
2. I Ching opt-in — offered identically every session
3. Full date of birth
4. Birth time — exact, approximate, or unknown
5. Birth city + country
6. Full birth name as on birth certificate
7. Current name if different (optional)
8. Gender (optional)

**Tolerance rules**
- Date in wrong format → parse and confirm back to user before proceeding
- City without country → ask for country
- Approximate time in natural language → map to window, confirm with user
- Unrecognised input → rephrase once, then mark as null and continue
- City resolves to multiple locations → present top 3 options, ask user to confirm
- Never guess silently

**Done condition**
All required fields populated or explicitly null. Output object valid and structured. Ambiguous inputs confirmed back to user before accepting. No field silently missing or silently defaulted.

**Failure behaviours**
Gibberish for required field → rephrase and re-ask once. If still unresolvable → null, noted downstream. User refuses required field → null, proceed. Never block, never guess.

---

## S-02 — Birth Time Tier Detection

**Spec reference:** Birth time tiers, Tolerance rules

**What this slice does**
Takes the raw birth time input collected by S-01 and classifies it into one of three tiers. Maps approximate natural language inputs to a defined time window. Flags the tier for use by downstream heads and the confidence note generator.

**Inputs**
Raw birth time string from S-01 output.

**Outputs**
```json
{
  "tier": "exact | approximate | none",
  "normalised_time": "HH:MM | null",
  "window_start": "HH:MM | null",
  "window_end": "HH:MM | null",
  "confidence_flag": "boolean",
  "confidence_reason": "string | null"
}
```

**Classification rules**

*Exact tier:* Input contains a recognisable time in any format → normalise to HH:MM (24-hour). Confirm back to user. User confirms → tier = exact, confidence_flag = false.

*Approximate tier:* Map to window using this table:
```
"dawn" | "early morning" | "before sunrise"   → 04:00 – 06:00
"morning" | "in the morning"                  → 06:00 – 09:00
"late morning" | "before noon"                → 09:00 – 12:00
"noon" | "around noon" | "midday"             → 11:00 – 13:00
"afternoon" | "in the afternoon"              → 12:00 – 15:00
"late afternoon" | "evening started"          → 15:00 – 18:00
"evening" | "in the evening" | "after sunset" → 18:00 – 21:00
"night" | "at night"                          → 21:00 – 00:00
"late night" | "past midnight" | "early hours"→ 00:00 – 04:00
```
Confirm with user. tier = approximate, confidence_flag = true.

*None tier:* Input is null or explicit statement of not knowing → tier = none, confidence_flag = true.

**Edge cases**
- Hedged specific time (e.g. "I think it was around 3pm but I'm not sure") → approximate tier, not exact
- Time range stated → use as window directly
- Single digit or nonsensical → ask once using simplified options, then none tier
- Invalid time (e.g. "25:00") → flag as invalid, ask once, then none tier

**Downstream consumers**
S-05 Vedic, S-06 Western, S-08 Chinese, S-12 Confidence note generator

**Done condition**
Every possible birth time input produces a valid structured output with the correct tier. No input causes a crash or silent default. All approximate inputs confirmed before locking. Confidence flag correct on every non-exact tier.

**Failure behaviours**
Unrecognised input → ask once using simplified options. If still unresolvable → none tier. Never block, never guess silently.

---

## S-03 — Moon Sign Ambiguity Resolution

**Spec reference:** Moon sign ambiguity, Birth time tiers

**What this slice does**
Determines whether the moon changes signs on the user's birth date. If it does and birth time is unknown or approximate, applies the majority-day rule to assign a definitive moon sign. Flags the result for downstream heads and the confidence note generator.

**Inputs**
```json
{
  "dob": { "day": "number", "month": "number", "year": "number" },
  "birth_time": {
    "tier": "exact | approximate | none",
    "normalised_time": "HH:MM | null",
    "window_start": "HH:MM | null",
    "window_end": "HH:MM | null"
  },
  "birth_location": { "city": "string", "country": "string" }
}
```

**Outputs**
```json
{
  "moon_sign": "string",
  "moon_sign_certain": "boolean",
  "transition_occurred": "boolean",
  "transition_time_local": "HH:MM | null",
  "majority_sign": "string | null",
  "minority_sign": "string | null",
  "majority_hours": "number | null",
  "confidence_flag": "boolean",
  "confidence_reason": "string | null"
}
```

**Processing rules**

*Step 1:* Calculate moon position at 00:00 and 23:59 local time. If same sign → no transition, moon_sign_certain = true, confidence_flag = false.

*Step 2 (transition detected):* Calculate precise transition time. Identify majority and minority sign by hours occupied.

*Step 3 — Route by tier:*
- Exact → compare normalised_time to transition_time_local. Assign sign with certainty.
- Approximate → if window entirely before or after transition → certain. If window overlaps → majority-day rule, confidence_flag = true.
- None → majority-day rule unconditionally, confidence_flag = true.

**Edge cases**
- Moon changes signs at exactly midnight → entire day belongs to second sign, certain
- Moon changes signs twice in one day → use longest continuous block, flag as unusual
- Location unresolvable → fall back to UTC, note in confidence_reason
- Invalid DOB → return null for all moon fields, flag

**Downstream consumers**
S-05 Vedic, S-06 Western, S-12 Confidence note generator

**Done condition**
Every combination of birth time tier × moon transition scenario produces valid output. Majority-day rule applied only when window genuinely overlaps. Exact tier never uses majority-day rule. Location always used for local time calculation — UTC is fallback only.

**Failure behaviours**
Ephemeris calculation fails → moon_sign = null, confidence_flag = true. Location resolution fails → UTC fallback, flagged. Never crash.

---

## S-04 — I Ching Opt-in

*(Contracted within S-10. See S-10 — seed collection interaction workflow.)*

---

## S-05 — Vedic Astrology Head Engine

**Spec reference:** Per-head data requirements, Birth time tiers, Moon sign ambiguity, Design philosophy

**What this slice does**
Computes Vedic astrological findings across all available dimensions. Returns a structured findings object and a self-contained explainability trail written in Vedic domain language. Never narrates — only computes and structures.

**Inputs**
```json
{
  "dob": { "day": "number", "month": "number", "year": "number" },
  "birth_time": { "tier": "string", "normalised_time": "string|null", "window_start": "string|null", "window_end": "string|null" },
  "birth_location": { "city": "string", "country": "string" },
  "gender": "string | null",
  "moon": { "moon_sign": "string", "moon_sign_certain": "boolean", "transition_occurred": "boolean" },
  "query": "string"
}
```

**Outputs**
```json
{
  "head": "vedic",
  "available_findings": [],
  "unavailable_findings": [],
  "findings": {
    "rashi": "string | null",
    "rashi_certain": "boolean",
    "lagna": "string | null",
    "lagna_available": "boolean",
    "nakshatra": "string | null",
    "nakshatra_pada": "number | null",
    "current_dasha": { "planet": "string", "start_date": "string", "end_date": "string" },
    "current_antardasha": { "planet": "string", "start_date": "string", "end_date": "string" },
    "active_bhavas": [],
    "planetary_positions": { "sun": "string", "moon": "string", "mars": "string", "mercury": "string", "jupiter": "string", "venus": "string", "saturn": "string", "rahu": "string", "ketu": "string" },
    "yogas": [],
    "current_transits": [],
    "query_relevant_findings": [],
    "tendency_window_weeks": { "min": "number", "max": "number" }
  },
  "confidence_flag": "boolean",
  "confidence_reason": "string | null",
  "explainability_trail": {
    "label": "Vedic astrology",
    "sections": [{ "title": "string", "content": "string", "available": "boolean" }]
  }
}
```

**Computation rules by tier**

*Exact:* Full computation — lagna, all 12 bhavas, rashi, nakshatra, pada, Vimshottari dasha sequence, planetary positions, yogas, transits. All findings available.

*Approximate:* Lagna and bhavas omitted. Rashi from S-03. Nakshatra computed and flagged if uncertain. Dasha available with reduced confidence. Non-lagna yogas available. confidence_flag = true.

*None:* Same as approximate but dasha confidence further reduced. confidence_flag = true.

**Query relevance mapping**
```
Career / work       → 10th bhava lord, Saturn, Sun, current dasha
Relationships       → 7th bhava lord, Venus, Jupiter (females), dasha
Finances            → 2nd and 11th bhava lords, Jupiter, Venus
Health              → 1st and 6th bhava lords, Mars, Saturn transits
Travel / relocation → 9th and 12th bhava lords, Rahu, transits
General direction   → lagna lord, dasha + antardasha, active yogas
No match            → dasha + antardasha, rashi, nakshatra
```
If relevant bhava unavailable → fall back to planetary positions. query_relevant_findings never empty.

**Tendency window**
Derived from dasha + antardasha transition dates, expressed in weeks. If unavailable → null.

**Explainability trail sections**
Rashi · Lagna · Nakshatra · Current dasha · Antardasha · Active yogas · Current transits · Query-relevant findings. Unavailable sections include plain-language reason — never silently omitted.

**Done condition**
All three tiers produce valid output. query_relevant_findings always has at least one entry. Tendency window always in weeks or null. Unavailable findings explicitly listed. Trail complete regardless of availability. Confidence flag correctly set.

**Failure behaviours**
Ephemeris unavailable → return nulls, flag, never crash. Query relevance no match → fall back to general direction mapping. Single planet failure → null that planet, continue.

---

## S-06 — Western Astrology Head Engine

**Spec reference:** Per-head data requirements, Birth time tiers, Moon sign ambiguity, Design philosophy

**What this slice does**
Computes Western astrological findings. Same input shape as S-05 — domain knowledge differs, contract structure identical. Uses Placidus house system as default.

**Inputs**
Identical to S-05.

**Outputs**
```json
{
  "head": "western",
  "available_findings": [],
  "unavailable_findings": [],
  "findings": {
    "sun_sign": "string",
    "sun_sign_certain": "boolean",
    "moon_sign": "string",
    "moon_sign_certain": "boolean",
    "rising_sign": "string | null",
    "rising_sign_available": "boolean",
    "mercury_sign": "string",
    "venus_sign": "string",
    "mars_sign": "string",
    "jupiter_sign": "string",
    "saturn_sign": "string",
    "north_node_sign": "string",
    "south_node_sign": "string",
    "houses": { "1st": "string|null", "2nd": "string|null", "3rd": "string|null", "4th": "string|null", "5th": "string|null", "6th": "string|null", "7th": "string|null", "8th": "string|null", "9th": "string|null", "10th": "string|null", "11th": "string|null", "12th": "string|null" },
    "midheaven": "string | null",
    "midheaven_available": "boolean",
    "aspects": [],
    "current_transits": [],
    "chart_pattern": "string | null",
    "query_relevant_findings": [],
    "tendency_window_weeks": { "min": "number", "max": "number" }
  },
  "confidence_flag": "boolean",
  "confidence_reason": "string | null",
  "explainability_trail": {
    "label": "Western astrology",
    "sections": [{ "title": "string", "content": "string", "available": "boolean" }]
  }
}
```

**Computation rules by tier**

*Exact:* Full computation — sun sign, moon sign, rising sign, all 12 houses (Placidus), midheaven, planetary positions, aspects (8° orb for major aspects), transits, chart pattern.

*Approximate:* Rising sign, houses, midheaven unavailable. Sun sign, moon sign, planetary positions, non-angular aspects, transits available. confidence_flag = true.

*None:* Same as approximate. confidence_flag = true.

**Sun sign cusp handling**
Birth date within 2 days of sign boundary → compute precisely from ephemeris. If tier is not exact → sun_sign_certain = false, flag in trail.

**Query relevance mapping**
```
Career / work       → 10th house ruler, Saturn, Sun, MC, Saturn transits
Relationships       → 7th house ruler, Venus, Mars, Venus transits
Finances            → 2nd house ruler, Jupiter, Venus, Jupiter transits
Health              → 1st and 6th house rulers, Mars, Chiron transits
Travel / relocation → 9th house ruler, Jupiter, Sagittarius, north node
General direction   → rising sign, sun sign, moon sign, north node, chart pattern
No match            → sun sign, moon sign, major transits
```

**Tendency window**
Derived from nearest exact aspect between transiting outer planet and natal planet within 6-month window. Expressed in weeks. If no transit within window → null.

**Vedic vs Western comparison**

| Dimension | Vedic | Western |
|-----------|-------|---------|
| Primary identity marker | Rashi (moon sign) | Sun sign |
| Ascendant term | Lagna | Rising sign |
| House system | Bhava (whole sign) | Placidus |
| Time-based prediction | Vimshottari dasha | Outer planet transits |
| Nodes | Rahu / Ketu | North / South node |
| Tendency window source | Dasha transition dates | Nearest exact transit |
| Outer planets used | Saturn and inward only | All including Uranus, Neptune, Pluto |

**Explainability trail sections**
Sun sign · Moon sign · Rising sign · Planetary positions · Houses · Midheaven · Aspects · Current transits · Chart pattern · Query-relevant findings. Unavailable sections always include reason.

**Edge cases**
- Cusp date + none tier → compute from ephemeris using noon UTC, flag uncertain
- More than 20 aspects → return 8 most significant by orb tightness
- Placidus fails for extreme latitudes (>66°N or <66°S) → fall back to whole sign system, note in trail

**Done condition**
All three tiers produce valid output. Cusp handling correct for all tiers. S-03 moon_sign_certain inherited correctly — never recomputed. Tendency window in weeks or null.

**Failure behaviours**
Ephemeris unavailable → same as S-05. Placidus failure → whole sign fallback. Transit calculation empty → null window, proceed.

---

## S-07 — Numerology Head Engine

**Spec reference:** Per-head data requirements, Design philosophy

**What this slice does**
Computes core numerology findings using Pythagorean system as primary and Chaldean as secondary for Expression number. No birth time dependency. No location dependency. Always runs at full fidelity.

**Inputs**
```json
{
  "full_birth_name": "string",
  "current_name": "string | null",
  "dob": { "day": "number", "month": "number", "year": "number" },
  "query": "string"
}
```

**Outputs**
```json
{
  "head": "numerology",
  "available_findings": [],
  "unavailable_findings": [],
  "findings": {
    "life_path_number": "number",
    "life_path_master": "boolean",
    "expression_number": { "pythagorean": "number", "chaldean": "number", "divergent": "boolean" },
    "soul_urge_number": "number",
    "personality_number": "number",
    "birthday_number": "number",
    "personal_year_number": "number",
    "personal_month_number": "number",
    "maturity_number": "number",
    "current_name_number": "number | null",
    "current_name_divergence": "boolean | null",
    "pinnacle_cycles": [{ "cycle": "number", "number": "number", "age_start": "number", "age_end": "number|ongoing", "active": "boolean" }],
    "challenge_numbers": { "first": "number", "second": "number", "main": "number", "final": "number" },
    "query_relevant_findings": [],
    "tendency_window_weeks": { "min": "number", "max": "number" }
  },
  "confidence_flag": "boolean",
  "confidence_reason": "string | null",
  "explainability_trail": {
    "label": "Numerology",
    "sections": [{ "title": "string", "content": "string", "available": "boolean" }]
  }
}
```

**Computation rules**

- *Life path:* Sum all DOB digits, reduce. Master numbers 11, 22, 33 never reduced.
- *Expression:* Pythagorean and Chaldean both computed. Divergent if different.
- *Soul urge:* Vowels only (Pythagorean). Y treated as vowel when it makes vowel sound.
- *Personality:* Consonants only (Pythagorean). Y treatment inverse of soul urge.
- *Birthday:* Day of birth unreduced.
- *Personal year:* DOB day + month + current year digits, reduced. Recomputed each query.
- *Personal month:* Personal year + current month, reduced. Recomputed each query.
- *Maturity:* Life path + expression (Pythagorean), reduced.
- *Pinnacles:* Four cycles — first ends at (36 − life path), each subsequent adds 9 years.
- *Challenges:* Four numbers derived from DOB digit subtraction.

**Name handling**
Remove titles, hyphens, apostrophes. Normalise accented characters to base Latin. Spaces ignored in calculation. Non-Latin script → transliterate, flag in trail.

**Personal year 9 rule**
Always surfaced in query_relevant_findings regardless of query domain.

**Tendency window**
```
min = weeks to end of current personal month
max = weeks to end of current personal year
```
Never null for this head.

**Done condition**
All numbers computed correctly. Master numbers never reduced. Personal year and month always from today's date. tendency_window_weeks never null. Pythagorean and Chaldean both computed for expression. Personal year 9 always surfaces.

**Failure behaviours**
Name null or empty → compute DOB-based numbers only, flag. DOB partial → compute what is possible, flag. Non-Latin transliteration fails → null affected numbers, flag.

---

## S-08 — Chinese Astrology Head Engine

**Spec reference:** Per-head data requirements, Birth time tiers, Design philosophy

**What this slice does**
Computes Chinese astrological findings at two levels — zodiac animal (always available) and Four Pillars of Destiny / Ba Zi (when birth hour available). Chinese calendar conversion is mandatory before any computation.

**Inputs**
```json
{
  "dob": { "day": "number", "month": "number", "year": "number" },
  "birth_time": { "tier": "string", "normalised_time": "string|null", "window_start": "string|null", "window_end": "string|null" },
  "birth_location": { "city": "string", "country": "string" },
  "query": "string"
}
```

**Outputs**
```json
{
  "head": "chinese",
  "available_findings": [],
  "unavailable_findings": [],
  "findings": {
    "zodiac_animal": "string",
    "zodiac_element": "string",
    "zodiac_year_certain": "boolean",
    "yin_yang": "yin | yang",
    "four_pillars": {
      "available": "boolean",
      "year_pillar": { "heavenly_stem": "string", "earthly_branch": "string", "element": "string", "animal": "string" },
      "month_pillar": { "heavenly_stem": "string", "earthly_branch": "string", "element": "string", "animal": "string" },
      "day_pillar": { "heavenly_stem": "string", "earthly_branch": "string", "element": "string", "animal": "string" },
      "hour_pillar": { "heavenly_stem": "string|null", "earthly_branch": "string|null", "element": "string|null", "animal": "string|null" },
      "day_master": "string | null",
      "day_master_strength": "strong | weak | neutral | null",
      "dominant_element": "string | null",
      "lacking_element": "string | null"
    },
    "current_luck_pillar": { "heavenly_stem": "string", "earthly_branch": "string", "element": "string", "age_start": "number", "age_end": "number", "active": "boolean" },
    "current_year_energy": { "animal": "string", "element": "string", "relationship_to_natal": "string" },
    "current_month_energy": { "animal": "string", "element": "string" },
    "clash_year": "boolean",
    "clash_reason": "string | null",
    "query_relevant_findings": [],
    "tendency_window_weeks": { "min": "number", "max": "number" }
  },
  "confidence_flag": "boolean",
  "confidence_reason": "string | null",
  "explainability_trail": {
    "label": "Chinese astrology",
    "sections": [{ "title": "string", "content": "string", "available": "boolean" }]
  }
}
```

**Chinese calendar conversion**
Convert DOB from Gregorian to Chinese lunisolar calendar before any computation. Users born before Chinese New Year in their Gregorian birth year belong to the previous zodiac year. This conversion is mandatory — Gregorian year never used directly.

**Computation rules by tier**

*All tiers — base reading:* Zodiac animal, element, yin/yang, current year energy, current month energy, clash year detection, year + month + day pillars.

*Exact:* Full Four Pillars — hour pillar from normalised_time using Chinese double-hour system. Day master and strength computed. Luck pillar available.

*Approximate:* Hour pillar resolved if window falls within one double-hour. If window spans two double-hours → check if day master strength conclusion is the same under both. If same → use either. If different → omit hour pillar.

*None:* Three pillars only (year, month, day). Hour pillar null. Day master computable from day pillar alone.

**Chinese double-hour system**
```
23:00 – 00:59 → Rat    | 01:00 – 02:59 → Ox
03:00 – 04:59 → Tiger  | 05:00 – 06:59 → Rabbit
07:00 – 08:59 → Dragon | 09:00 – 10:59 → Snake
11:00 – 12:59 → Horse  | 13:00 – 14:59 → Goat
15:00 – 16:59 → Monkey | 17:00 – 18:59 → Rooster
19:00 – 20:59 → Dog    | 21:00 – 22:59 → Pig
```

**Clash year pairs**
Rat/Horse · Ox/Goat · Tiger/Monkey · Rabbit/Rooster · Dragon/Dog · Snake/Pig. Always surfaced in query_relevant_findings when true.

**Ben ming nian (return year)**
Current year animal matches natal zodiac animal → flag in query_relevant_findings.

**Tendency window**
```
min = weeks to next Chinese month transition
max = weeks to next Chinese New Year
```
Never null for this head.

**Done condition**
Chinese calendar conversion always applied. Clash year always detected and surfaced. Ben ming nian detected and flagged. Hour pillar ambiguity resolved by day master strength consistency check. tendency_window_weeks never null. Explainability trail always contains clash year section.

**Failure behaviours**
Chinese calendar library unavailable → fall back to Gregorian year, flag. Four Pillars pillar failure → null that pillar, continue. Luck pillar failure → null, base reading unaffected.

---

## S-09 — Philosophy Head Engine

**Spec reference:** Per-head data requirements, Design philosophy

**What this slice does**
Applies three philosophical frameworks — Stoicism, Vedanta, and karma theory — to the user's query. No astronomical calculation. No birth data dependency. Always runs at full fidelity.

**Inputs**
```json
{
  "query": "string",
  "life_context": {
    "career": "string | null",
    "relationships": "string | null",
    "health": "string | null",
    "other": "string | null"
  }
}
```

**Outputs**
```json
{
  "head": "philosophy",
  "available_findings": [],
  "unavailable_findings": [],
  "findings": {
    "query_theme": "string",
    "query_category": "career | relationships | finances | health | travel | direction | general",
    "frameworks": {
      "stoicism": { "core_principle": "string", "applied_finding": "string", "key_distinction": "string", "practical_guidance": "string" },
      "vedanta": { "core_principle": "string", "applied_finding": "string", "key_distinction": "string", "practical_guidance": "string" },
      "karma": { "core_principle": "string", "applied_finding": "string", "key_distinction": "string", "practical_guidance": "string" }
    },
    "convergence": "string | null",
    "divergence": "string | null",
    "query_relevant_findings": [],
    "tendency_window_weeks": null
  },
  "confidence_flag": false,
  "confidence_reason": null,
  "explainability_trail": {
    "label": "Philosophy",
    "sections": [{ "title": "string", "content": "string", "available": "boolean" }]
  }
}
```

**Framework definitions**

*Stoicism:* Central tenet — dichotomy of control. What is up to us (judgments, intentions, responses) vs what is not (external outcomes, other people). Virtue is the only true good. Key figures: Marcus Aurelius, Epictetus, Seneca.

*Vedanta:* Central tenet — Brahman and Atman are not separate. Suffering arises from identifying with the ego-self rather than the universal self. Liberation through viveka, vairagya, jnana.

*Karma theory:* Three types — sanchita (accumulated past), prarabdha (currently ripening), agami (being created now by present choices). Applied findings distinguish which type is most relevant.

**Computation steps**
1. Query theme extraction — strip esoteric framing, identify core human concern
2. Framework application — four fields per framework: core_principle, applied_finding, key_distinction, practical_guidance
3. Convergence and divergence assessment
4. Query relevance population

**Anti-platitude rules**
Forbidden outputs (contract violations):
- "Everything happens for a reason"
- "Trust the process"
- "Focus on what you can control" (without specifying what)
- "Let go of what does not serve you" (without specifying what)
- Any finding that applies equally to any user with any query

*Test:* Could this finding be copy-pasted into a reading for a completely different user with a different query and still make sense? If yes — it is a platitude. Replace it.

**Tendency window**
Always null. Philosophy has no time-based mechanism.

**Edge cases**
- Purely esoteric query → extract implicit human concern and apply frameworks to that
- Distress signals → all frameworks emphasise grounded present-moment action. Stoicism: next right action. Vedanta: witness self is untouched. Karma: agami karma is the most powerful force available now
- Third-party query → reframe to user's relationship to the situation
- Life context contradicts query → use both; the contradiction may be the most relevant finding

**Done condition**
All three frameworks produce findings for every query. applied_finding specific to the query — never generic. practical_guidance actionable and grounded. Anti-platitude rules applied to every output. Tendency window always null. Confidence flag always false.

**Failure behaviours**
Query and life_context both null → apply all frameworks to the concept of seeking guidance itself. Framework fails anti-platitude test after three attempts → return least generic with trail note.

---

## S-10 — I Ching Head Engine

**Spec reference:** Knowledge heads, I Ching optional head, Design philosophy

*Tarot deferred to v0.2. Changing lines and moving hexagram deferred to v0.2.*

**What this slice does**
Runs only when user opted in (S-04). Collects a seed word or number during data collection. Maps seed to one of 64 hexagrams via deterministic hash. Computes I Ching findings applied to the user's query.

**Seed collection interaction (S-04 workflow)**
Presented immediately after opt-in at step 2 of question sequence:

> "Before we begin your reading, take a moment. Think of a word, a name, a number — anything that feels significant to you right now. It could be the first thing that comes to mind, or something you have been carrying. Type it here."

Rules: Any non-empty string or number accepted. No validation beyond non-empty. Never tell user what makes a good seed. If user asks what to type → repeat prompt once. If empty after two prompts → generate random seed silently, proceed.

**Seed-to-hexagram mapping**
```
Step 1 — Normalise: lowercase, strip whitespace and punctuation
Step 2 — Hash: SHA-256 of normalised string, take first 8 hex chars, convert to integer
Step 3 — Map: hexagram_number = (integer mod 64) + 1
Step 4 — Determinism: same seed always produces same hexagram
```
SHA-256 fallback: sum of Unicode code points mod 64 + 1. Flag in trail.

**Inputs**
```json
{
  "seed": "string | number",
  "query": "string",
  "opted_in": true
}
```

**Outputs**
```json
{
  "head": "iching",
  "available_findings": [],
  "unavailable_findings": [],
  "findings": {
    "seed_used": "string",
    "hexagram_number": "number",
    "hexagram_name_chinese": "string",
    "hexagram_name_english": "string",
    "image": "string",
    "judgment": "string",
    "core_theme": "string",
    "polarity": "yin | yang | balanced",
    "tendency_direction": "forward | pause | retreat | transform",
    "query_application": "string",
    "query_relevant_findings": [],
    "tendency_window_weeks": { "min": "number", "max": "number" }
  },
  "confidence_flag": false,
  "confidence_reason": null,
  "explainability_trail": {
    "label": "I Ching",
    "sections": [{ "title": "string", "content": "string", "available": "boolean" }]
  }
}
```

**Tendency direction → window mapping**
```
forward   → { min: 2,  max: 8  }
pause     → { min: 4,  max: 16 }
retreat   → { min: 8,  max: 24 }
transform → { min: 6,  max: 20 }
```
Never null for this head.

**Query application rule**
Same anti-platitude discipline as S-09 applies in full. query_application must answer: given this hexagram and this specific query, what does the I Ching counsel? Must not paraphrase judgment generically. Must engage with the intersection of hexagram meaning and user's actual question.

**Explainability trail sections**
Seed + hexagram cast · Hexagram identity · Image + judgment · Applied to your question · Tendency direction · Query-relevant findings

**Edge cases**
- Seed is a number 1–64 → apply hash regardless, never map directly
- Non-Latin seed → transliterate before hashing, flag in trail
- SHA-256 unavailable → simplified hash fallback, flag in trail

**Done condition**
Seed collection never blocks session. Same seed always produces same hexagram. query_application specific to query. Anti-platitude discipline applied. Tendency window derived from tendency_direction — never null. Trail shows full casting chain.

**Failure behaviours**
Empty seed after two prompts → random seed, note in trail. Hexagram lookup returns null → fall back to hexagram 1, log. query_application fails anti-platitude after three attempts → return least generic with trail note.

---

## S-11 — Synthesis Layer

**Spec reference:** Output format, Synthesis weighting, Design philosophy

**What this slice does**
Consumes structured findings from all active heads. Merges into a single coherent summary. All active heads contribute equally. Does not read explainability trails. Does not produce confidence notes.

**Inputs**
```json
{
  "query": "string",
  "query_category": "career | relationships | finances | health | travel | direction | general",
  "active_heads": [],
  "head_findings": {
    "vedic": "VedicFindingsObject | null",
    "western": "WesternFindingsObject | null",
    "numerology": "NumerologyFindingsObject | null",
    "chinese": "ChineseFindingsObject | null",
    "philosophy": "PhilosophyFindingsObject | null",
    "iching": "IChingFindingsObject | null"
  },
  "universal_signals": {
    "personal_year_9": "boolean",
    "clash_year": "boolean",
    "ben_ming_nian": "boolean",
    "clash_reason": "string | null",
    "ben_ming_nian_reason": "string | null"
  }
}
```

**Outputs**
```json
{
  "summary": "string",
  "paragraph_count": "1 | 2",
  "word_count": "number",
  "tendency_window": {
    "composite_min_weeks": "number",
    "composite_max_weeks": "number",
    "contributing_heads": [],
    "expressed_as": "string"
  },
  "convergence_signals": [],
  "divergence_signals": [],
  "universal_signals_surfaced": [],
  "synthesis_notes": "string | null"
}
```

**Computation steps**

1. Collect query_relevant_findings from all active heads — tag with source head
2. Detect convergence signals (timing alignment, domain alignment, caution alignment, philosophy convergence)
3. Detect divergence signals (timing divergence, direction divergence, philosophy divergence)
4. Surface universal signals (personal_year_9, clash_year, ben_ming_nian) — always included when true
5. Compute composite tendency window — average min and max across non-null head windows
6. Draft summary — convergence signals as structural spine, divergence as honest qualifications, universal signals as priority anchors
7. Self-review checklist

**Self-review checklist**
```
□ First sentence states most important signal
□ All convergence signals present
□ Divergence signals named, not suppressed
□ All universal signals woven in
□ Tendency window in weeks, woven naturally, never fixed date
□ Every sentence references at least one specific finding
□ No sentence fails anti-platitude test
□ No sentence fails anti-optimism test
□ Word count within ceiling
□ Summary reads as judgment, not list
```

**Summary writing rules**
- 1–2 paragraphs, max 500 words each, max 1000 words total
- Direct, unvarnished, no false optimism
- No per-head attribution more than twice
- Never opens with "Based on your birth chart..."
- Never closes with any disclaimer
- Never a bullet list — always prose
- Never uses the word "journey"

**Anti-optimism violations**
- "Things will improve" without basis in findings
- Difficulty reframed as hidden opportunity without supporting finding
- Caution signals from multiple heads softened into single reassuring sentence
- Universal signals described as purely positive

**Composite tendency window**
Average of all non-null head windows. Expressed as plain language range in weeks. If all null → tendency_window = null. Never fabricated.

**Done condition**
All active head findings in working set. Convergence and divergence both detected and neither suppressed. Universal signals always surface. Composite window correctly averaged and in weeks. Self-review checklist passes. Summary is prose. Anti-platitude and anti-optimism rules pass on every sentence.

**Failure behaviours**
One or more head findings null → exclude, note in synthesis_notes. Working set empty → summary = null, synthesis_notes = "No findings available." Self-review fails after three revisions → return best available with note. Word count exceeds ceiling → truncate at sentence boundary.

---

## S-12 — Confidence Note Generator

**Spec reference:** Confidence notes, Design philosophy

**What this slice does**
Collects confidence flags from all active heads. Produces a single consolidated plain-language note appearing directly below the summary when any head is at reduced fidelity.

**Inputs**
```json
{
  "active_heads": [],
  "head_confidence": {
    "vedic":      { "flag": "boolean", "reason": "string | null" },
    "western":    { "flag": "boolean", "reason": "string | null" },
    "numerology": { "flag": "boolean", "reason": "string | null" },
    "chinese":    { "flag": "boolean", "reason": "string | null" },
    "philosophy": { "flag": "boolean", "reason": "string | null" },
    "iching":     { "flag": "boolean", "reason": "string | null" }
  },
  "moon": { "moon_sign_certain": "boolean", "transition_occurred": "boolean" }
}
```

**Outputs**
```json
{
  "note_required": "boolean",
  "note": "string | null",
  "affected_heads": [],
  "severity": "minor | moderate | significant | null"
}
```

**Severity rules**
```
1 head flagged, moon sign uncertainty only  → minor
1–2 heads flagged, approximate birth time   → minor
2–3 heads flagged, approximate or no time   → moderate
4+ heads flagged, or any calculation failure → significant
```

**Note format**
Single consolidated sentence or two — not a list. Matter-of-fact. Does not apologise. Does not reassure. States what is reduced and why.

**Done condition**
Note produced if and only if at least one head has confidence_flag = true. Always one consolidated statement. Severity always set when note_required = true. Never appears when all heads at full fidelity.

**Failure behaviours**
Any head confidence object missing → treat as flag = false. Never crash.

---

## S-13 — Explainability Trail Renderer

**Spec reference:** Output format, Design philosophy

**What this slice does**
Collects explainability trails from all active heads. Renders them in a structured expandable format on explicit user request only. Never shown by default.

**Inputs**
```json
{
  "active_heads": [],
  "head_trails": {
    "vedic":      "ExplainabilityTrailObject | null",
    "western":    "ExplainabilityTrailObject | null",
    "numerology": "ExplainabilityTrailObject | null",
    "chinese":    "ExplainabilityTrailObject | null",
    "philosophy": "ExplainabilityTrailObject | null",
    "iching":     "ExplainabilityTrailObject | null"
  },
  "user_requested": "boolean"
}
```

**Outputs**
```json
{
  "rendered": "boolean",
  "trail": [
    {
      "head_label": "string",
      "head_order": "number",
      "sections": [{ "title": "string", "content": "string", "available": "boolean", "unavailable_reason": "string | null" }]
    }
  ]
}
```

**Head display order**
1. Vedic astrology · 2. Western astrology · 3. Numerology · 4. Chinese astrology · 5. Philosophy · 6. I Ching (if active)

**Display trigger**
User requests in natural language — "show me the detail", "how did you get there", "explain your reasoning", "what did each system say". System recognises intent patterns — no specific command required.

**Rules**
- Gate on user_requested = true — never render proactively
- Unavailable sections shown with reason — never hidden
- Domain language preserved per head — no normalisation
- Trail does not regenerate within same session

**Done condition**
Trail renders only on explicit request. All active heads in fixed order. Unavailable sections always shown with reason. Null trails skipped with note.

**Failure behaviours**
Malformed trail object → skip that head's sections, include label with note. Never crash.

---

## S-14 — Session Context

**Spec reference:** Session behaviour

**Session context object**
```json
{
  "session_id": "string",
  "session_start": "timestamp",
  "data_pool": "SharedDataPoolObject | null",
  "birth_time_tier": "BirthTimeTierObject | null",
  "moon_resolution": "MoonResolutionObject | null",
  "tarot_opted_in": "boolean",
  "active_heads": [],
  "queries": [
    {
      "query_index": "number",
      "query": "string",
      "query_category": "string",
      "head_findings": {},
      "summary": "string | null",
      "confidence_note": "ConfidenceNoteObject | null",
      "trail_rendered": "boolean",
      "timestamp": "timestamp"
    }
  ],
  "session_status": "active | complete | abandoned"
}
```

**Rules**
- Data never re-collected within a session
- Multiple queries supported — data_pool reused, heads re-run per query
- Session ends on explicit close or 30-minute inactivity timeout (default)
- On session end → trigger S-15, then clear all context
- Abandoned session (no complete reading) → discard silently, no S-15 prompt

**Corrected input mid-session**
Update data_pool, re-run S-02 and S-03. Do not re-run earlier queries automatically — inform user that previous readings used uncorrected data.

**Done condition**
Data never re-collected within session. Multiple queries supported. Context fully cleared after S-15 completes. Corrected input updates pool and flags prior readings.

**Failure behaviours**
Context corrupted → recover from last valid query entry. If unrecoverable → notify user, start new session, offer re-collection.

---

## S-15 — Profile Save Prompt

**Spec reference:** Session behaviour, Profile persistence

**What this slice does**
At session end (at least one complete reading produced), prompts user to save profile. Saves on explicit yes only.

**Prompt**
> "Would you like to save your details for future sessions? This means you won't need to re-enter your birth information next time. Your data is stored only for this purpose."

**Saved profile object**
```json
{
  "profile_id": "string",
  "saved_at": "timestamp",
  "data_pool": {
    "dob": { "day": "number", "month": "number", "year": "number" },
    "birth_time": "BirthTimeTierObject",
    "birth_location": { "city": "string", "country": "string" },
    "full_birth_name": "string",
    "current_name": "string | null",
    "gender": "string | null"
  }
}
```

Query history is never saved. Only static personal data.

**Done condition**
Profile never saved without explicit yes. Prompt appears only when at least one reading produced. No-response treated as no. Saved profile never includes query history.

**Failure behaviours**
Storage write fails → notify user, never silently fail.

---

## S-16 — Profile Load and Confirm

**Spec reference:** Session behaviour, Profile persistence

**What this slice does**
At new session start, checks for saved profile. Loads and presents for confirmation if found. Skips data collection on confirmation.

**Profile found — prompt**
> "Welcome back. I have your details on file:
> Name: [full_birth_name]
> Date of birth: [dob]
> Birth time: [tier + value]
> Birth location: [city, country]
> Is this still correct?"

- Confirmed → load data_pool, skip S-01, proceed directly to query + I Ching opt-in
- Not confirmed → pre-fill S-01 with saved values, collect only changed fields

**Profile not found** → run full S-01.

**Partial profile** → collect only missing fields, not full S-01 re-run.

**Done condition**
Profile presented in full before use. Partial profiles collect only missing fields. Query and I Ching opt-in always collected fresh. Full S-01 never re-run unnecessarily.

**Failure behaviours**
Storage read fails → treat as no profile, run full S-01, notify user.

---

---

# Phase 4 — Multi-Surface Specs

---

## Conversation Architecture

The backend drives all data collection conversation logic. The frontend is a stateless display layer — it renders what the backend sends and forwards what the user types. The backend decides what question to ask next, validates responses, handles rephrasing, and signals when collection is complete. Neither the web frontend nor the mobile client contains any conversation logic or knowledge of the S-01 question sequence.

---

## Backend API Surface Spec

**Owns:** S-01 processing, S-02, S-03, S-05 through S-12, S-14, S-15, S-16.

### Endpoint Structure

```
POST /session/start
  → Creates session, triggers S-16 profile check
  → Returns: { session_id, profile_found, profile_data? }

POST /session/{id}/collect
  → Accepts one user message at a time
  → Runs S-01 conversation logic
  → Returns: {
      system_message: string,
      input_hint: "free_text" | "yes_no" | "date" | "location",
      collection_complete: boolean,
      quick_replies: [...] | null
    }
  → When collection_complete: triggers all head engines

POST /session/{id}/query
  → Accepts query string
  → Runs S-11 synthesis, S-12 confidence note
  → Returns: { summary, confidence_note?, tendency_window }
  → Streaming preferred

POST /session/{id}/trail
  → Returns S-13 explainability trail for last query
  → Only callable after query has been processed

POST /session/{id}/end
  → Triggers S-15 profile save prompt
  → Clears session after save decision
  → Returns: { profile_saved }
```

`input_hint` tells the frontend what input type to render. Frontend never infers this from question content — backend tells it explicitly.

### Parallelisation Order

```
On collection_complete:
  → S-02, S-03 first (blocking — Vedic and Western depend on them)
  → Then parallel: S-05, S-06, S-07, S-08, S-09, S-10?
  → Then: S-11 (waits for all heads)
  → Then: S-12 (waits for S-11)
  S-13 trail pre-assembled from head outputs — available after heads complete
```

### Auth

Session-based auth for v0.1. session_id is cryptographically random UUID. Profile storage keyed to persistent user identifier (email or device ID). Full auth system out of scope for v0.1.

### Rate Limiting

- One active session per user at a time
- Maximum three queries per session
- Maximum one session start per minute per user

### Error Response Shape

```json
{
  "error": true,
  "code": "string",
  "message": "string",
  "retry_safe": "boolean"
}
```

---

## Web Frontend Surface Spec

**Owns:** UI rendering for S-01 data collection, loading states, summary display, confidence note display, trail expand/collapse, session start/end UI, profile confirmation.

### UI Pattern

Conversational chat interface. System speaks first, user responds in text input. Never a form — always a conversation.

### Data Collection UI

```
Date of birth    → free text, never force date picker, backend parses
Birth time       → free text only — never show time picker
Birth city       → free text, numbered list if multiple matches returned
I Ching opt-in   → yes/no quick-reply buttons + typed response accepted
```

### Loading State

Display per-head progress messages as heads complete — streamed from API:
- "Reading your Vedic chart..."
- "Calculating your numerology..."
- "Consulting the I Ching..." (if opted in)
- "Bringing it all together..."

### Summary Display

Streamed token by token. Plain prose — no headers, bullets, or bold within summary. Confidence note below summary as visually quieter block. Tendency window woven into prose — not a separate element.

### Explainability Trail

Hidden by default. Triggered by natural language request. Expands as accordion — one section per head, each collapsible. Unavailable sections shown muted with reason. Domain language preserved.

### Constraints

- No page refresh during active session — session_id must survive client-side navigation
- Readable at 320px minimum width
- No browser-native date or time pickers

---

## Mobile Client Surface Spec

**Owns:** Same as web plus native input handling, offline data entry, local profile cache, background computation handling.

### Platform Targets

iOS and Android. React Native or Flutter recommended for solo developer building both simultaneously.

### Data Collection UI

```
Date of birth    → optional native date picker shortcut + free text accepted
Birth time       → free text only — no time picker
Birth city       → free text with native keyboard
                   Location permission never required — no GPS
I Ching opt-in   → native toggle or quick-reply buttons
```

### Background Computation Handling

```
App backgrounded during computation:
  → Session continues on backend
  → On foreground return: poll for completion
  → If complete: show reading immediately
  → If still computing: resume progress display

Push notification (optional for v0.1):
  → Notify when reading ready if backgrounded >60 seconds
  → Text: "Your reading is ready"
  → No reading content in notification
```

### Local Profile Cache

```
Cache rules:
  → Written only when S-15 confirms save
  → Read by S-16 as fast-path before API check
  → If cache and API disagree → API wins
  → Cleared if user deletes profile
  → Performance layer only — never substitute for server storage
```

### Offline Data Entry

```
Offline UI states:
  → "You're offline — enter your details and we'll
     begin your reading when you reconnect."
  → Data entry proceeds normally
  → Submit button → "Waiting for connection..."
  → On reconnect: submit automatically, show progress
```

### Summary and Trail Display

```
Summary:
  → Full-screen readable view
  → Swipe up to reveal confidence note
  → No pull-to-refresh

Trail:
  → Bottom sheet triggered by "Show me more" button
  → Each head is collapsible section within sheet
  → Dismissible by swipe down
```

### Constraints

- Never request location permission
- Never access contacts
- Never store reading content in local storage — only profile data cached

---

---

# Cascade Map

Use this map whenever a slice contract changes. Check every downstream reference before closing the change.

```
Change S-01  → check S-02, S-03, S-14
Change S-02  → check S-05, S-06, S-08, S-12
Change S-03  → check S-05, S-06, S-12
Change S-05  → check S-11, S-12, S-13
Change S-06  → check S-11, S-12, S-13
Change S-07  → check S-11, S-12, S-13
Change S-08  → check S-11, S-12, S-13
Change S-09  → check S-11, S-12, S-13
Change S-10  → check S-11, S-12, S-13
Change S-11  → check S-12, UI output layer
Change S-12  → check UI output layer
Change S-13  → check UI output layer
Change S-14  → check S-15, S-16
Change S-15  → check S-16
Change S-16  → check S-14
```

Update this map whenever a new slice is added.

---

---

# Living Spec Practices

---

## Practice 1 — Pre-Build Spec Check

Before starting any slice: read its contract, read its dependency contracts, write one sentence stating what done looks like. Then start. For head engines — validate Swiss Ephemeris returns the expected data shape before writing any business logic.

## Practice 2 — Divergence Log

See `DIVERGENCES.md`. Every divergence logged immediately with four fields: date, slice, what diverged, decision (fix code or update spec).

## Practice 3 — Weekly Spec Sync

Once a week: read every closed slice contract. Does built code still satisfy the done condition exactly? If not — slice goes back to in-progress. Priority checks: S-02 (approximate time confirmation), S-11 (anti-platitude enforcement), S-08 (Chinese calendar conversion).

## Practice 4 — Cascade Check

Every spec change triggers a cascade check using the map above. Takes ten minutes. Never change a slice in isolation.

## Practice 5 — Version Discipline

```
v0.x.patch  Clarifications, typo fixes, edge case additions
            that don't change behaviour
v0.x minor  Behaviour changes, new edge cases affecting
            existing slices, new spec sections
v1.0        System live and stable — all slices built,
            all done conditions verified
```

Changelog entry format: `vX.X — [one-line description]`
