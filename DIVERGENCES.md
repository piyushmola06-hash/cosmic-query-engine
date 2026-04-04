# Divergences Log

This file records every instance where implementation differs from the spec contract.
Every divergence is a conscious decision — not an accident.

---

## How to add an entry

```
## YYYY-MM-DD — [Slice ID]

**Slice:** S-XX — [Slice name]
**What diverged:** [Describe exactly how the implementation differs from the contract]
**Decision:** Fix code | Update spec
**Spec update:** [If updating spec — paste the new or revised spec language here]
**Notes:** [Optional — any context that explains the decision]
```

---

## Log

*(No entries yet — spec at v0.5, implementation not started)*

## 2026-03-30 — S-01

**Slice:** S-01 — Data Collection Layer
**What diverged:** Output field named `tarot_opted_in` in the 
spec JSON contract changed to `iching_opted_in` in implementation.
**Decision:** Update spec
**Spec update:** Field renamed from `tarot_opted_in` to 
`iching_opted_in` throughout S-01 output contract. Reason: spec 
text refers to I Ching throughout — Tarot is deferred to v0.2. 
The original field name was a copy-paste error in the spec.
**Notes:** First divergence logged. Process working correctly — 
Claude Code identified and flagged before proceeding.

## 2026-04-03 — S-15 / S-16

**Slice:** S-15 / S-16 — Profile Save and Load
**What diverged:** `full_birth_name` and `current_name` on `UserProfile`
are stored as plain `CharField` in v0.1. The spec implies encrypted storage
for sensitive personal data.
**Decision:** Fix code in v0.2
**Spec update:** No spec change — encryption is implied, not contracted.
## 2026-04-03 — API (Backend API Surface)

**Slice:** Backend API — POST /session/{id}/query
**What diverged:** Spec says "Streaming preferred" for synthesis summary. Implementation
uses standard `JsonResponse` (DRF `Response`). `StreamingHttpResponse` requires Django
Channels and async view support which is infrastructure-level work deferred beyond v0.1
backend slice.
**Decision:** Fix code in v0.2
**Spec update:** No spec change. Streaming is marked "preferred" not required.
**Notes:** v0.2 will wire Django Channels (already in requirements.txt) and convert
`QueryView` to an async streaming view returning SSE tokens.

## 2026-04-03 — API (Backend API Surface)

**Slice:** Backend API — POST /session/{id}/collect (collection_complete trigger)
**What diverged:** Spec says "When collection_complete: triggers all head engines
(S-05 through S-10, S-11, S-12)". Implementation triggers only S-02 and S-03 on
collection_complete. Head engines (S-07 through S-10) and synthesis (S-11, S-12) run
on POST /session/{id}/query instead.
**Decision:** Update spec interpretation
**Spec update:** The split is deliberate: S-02/S-03 are birth-data processors (run once
per session), head engines are query-specific (must re-run per query). S-11 needs the
query string which is better confirmed at query time. This interpretation aligns with
"data_pool reused, heads re-run per query" from S-14.
**Notes:** The collect endpoint cannot fully run S-11 because S-11 needs a confirmed
query string and the query endpoint is where the user submits their question for a
reading cycle.

## 2026-04-03 — API (Backend API Surface)

**Slice:** Backend API — S-05 (Vedic) and S-06 (Western) head engines
**What diverged:** Vedic and Western astrology heads are listed in MANDATORY_HEADS
but not yet built (require Swiss Ephemeris, deferred). When these heads are in
active_heads, `_run_head_engines` returns None for them. synthesis_notes will
reflect their exclusion.
**Decision:** Fix code in future slice (S-05, S-06)
**Spec update:** No spec change.
**Notes:** When S-05 and S-06 are built, `_run_head_engines` in `api/views.py` will
need the two `None` stubs replaced with actual calls.

**Notes:** `django-cryptography` requires additional key management
infrastructure (Fernet keys, environment variable wiring) that is out of
scope for v0.1. Plain storage is acceptable for local development. Before
any production deployment these fields must be migrated to encrypted storage.
Field-level TODO comment added in `core/models.py`.

## 2026-03-30 — S-06

**Slice:** S-06 — Western Astrology Head Engine
**What diverged:** swe.houses() returns a 0-indexed
12-element cusps tuple. Original code used cusps[i+1]
causing silent IndexError swallowing rising sign
computation entirely. Fixed to cusps[i].
**Decision:** Fix code
**Notes:** pyswisseph implementation detail not visible
from spec level. Tests now cover rising sign computation
explicitly for exact tier.
