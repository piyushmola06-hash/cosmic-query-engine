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

