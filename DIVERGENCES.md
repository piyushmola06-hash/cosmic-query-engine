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
**Notes:** `django-cryptography` requires additional key management
infrastructure (Fernet keys, environment variable wiring) that is out of
scope for v0.1. Plain storage is acceptable for local development. Before
any production deployment these fields must be migrated to encrypted storage.
Field-level TODO comment added in `core/models.py`.

