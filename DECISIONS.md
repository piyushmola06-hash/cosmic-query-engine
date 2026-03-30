# Decisions Log

This file records every significant architectural or technology decision made in this project.
Each entry explains what was decided and why — so future-you never has to reconstruct the reasoning.

---

## How to add an entry

```
## YYYY-MM-DD — [Decision title]
**Decision:** [What was decided]
**Reason:** [Why this option was chosen over alternatives]
**Alternatives considered:** [What else was evaluated]
**Revisit when:** [What circumstances would prompt revisiting this decision]
```

---

## Log

## 2026-03-30 — Backend-driven conversation architecture
**Decision:** The backend drives all data collection conversation logic. The frontend is a stateless display layer — it renders what the backend sends and forwards what the user types.
**Reason:** Single source of truth for S-01 conversation logic. Web and mobile surfaces remain stateless display layers with no conversation logic of their own. No risk of web and mobile drifting out of sync as the question sequence evolves. Offline data entry on mobile is simplified — the client queues messages and sends them when connectivity returns, never needing to know what question comes next.
**Alternatives considered:** Frontend-driven conversation where each surface knows the question sequence locally. Rejected because it duplicates logic across three surfaces and creates a maintenance burden every time the sequence changes.
**Revisit when:** Latency becomes noticeable on slow connections and local conversation logic would meaningfully improve perceived responsiveness.

---

## 2026-03-30 — Tech stack selection
**Decision:** Python + Django (backend), React + Vite (web frontend), Flutter (mobile).
**Reason:** Django chosen for mature ORM, excellent Python ecosystem, and strong pyswisseph integration for Swiss Ephemeris calculations. React + Vite chosen for fast development iteration and TypeScript support. Flutter chosen as the best single-codebase solution for iOS and Android for a solo developer — avoids maintaining two separate native codebases.
**Alternatives considered:** Node.js + Fastify (backend) — rejected because pyswisseph Python bindings are more mature than Node.js ephemeris options. Next.js (frontend) — rejected because SSR is unnecessary for a chat interface and adds complexity. React Native — considered alongside Flutter, Flutter chosen for stronger type safety and better performance on complex UI.
**Revisit when:** Team grows and Dart/Flutter expertise becomes a bottleneck, or if a key dependency becomes unavailable in the Flutter ecosystem.

---

## 2026-03-30 — I Ching only, Tarot deferred to v0.2
**Decision:** The optional sixth head in v0.1 is I Ching only. Tarot is deferred to v0.2. Changing lines and moving hexagram are deferred to v0.2. v0.1 produces a single primary hexagram from a deterministic seed hash.
**Reason:** Tarot requires a 78-card deck with upright/reversed meanings and spread positions — significantly more content and interaction design than I Ching. Scoping to I Ching only keeps v0.1 focused. The deterministic seed hash is simpler to implement than a traditional coin or yarrow stalk simulation and preserves the intentionality of the casting moment.
**Alternatives considered:** Including both Tarot and I Ching with user selection at opt-in. Rejected for v0.1 due to scope — two oracle systems with different interaction models would double the content and testing burden before any core system validation.
**Revisit when:** v0.1 is stable and the I Ching head is performing well in production.

---

## 2026-03-30 — Synthesis weights all heads equally regardless of data fidelity
**Decision:** All active heads contribute equally to synthesis. Degraded heads (e.g. Vedic with no birth time) are never silently de-weighted. Reduced confidence is communicated via the confidence note, not by suppressing a head's contribution.
**Reason:** Consistent with the transparency-first, never-block design philosophy. De-weighting degraded heads silently would be a form of silent guessing — the system making invisible judgment calls the user cannot see or challenge. Explicit confidence notes give the user the information to make their own judgment.
**Alternatives considered:** Weighted synthesis where degraded heads contribute proportionally less. Rejected because it introduces invisible editorial decisions into the output and violates the transparency principle.
**Revisit when:** User research shows that degraded head findings are consistently misleading synthesis output in a way that explicit confidence notes cannot adequately address.

---

## 2026-03-30 — Session-based auth for v0.1, full auth deferred
**Decision:** v0.1 uses session-based auth with cryptographically random UUIDs as session identifiers. Full account system (email/password, OAuth) is out of scope for v0.1.
**Reason:** Full auth adds significant complexity and is not required to validate the core reading experience. Profile persistence is keyed to a persistent device or browser identifier for v0.1 — sufficient for solo testing and early users.
**Alternatives considered:** Full email/password auth from day one. Rejected for v0.1 — adds user management, password reset, email verification overhead before the core product is validated.
**Revisit when:** Multiple users need persistent profiles across devices, or when the product moves from private testing to public access.
# Decisions Log

## 2026-03-30 — Backend-driven conversation architecture
Reason: Single source of truth for S-01 conversation logic.
Web and mobile remain stateless display layers.
No risk of surfaces drifting out of sync.
Offline data entry on mobile simplified — client queues
messages, never needs to know question sequence.
Revisit if latency becomes noticeable on slow connections.