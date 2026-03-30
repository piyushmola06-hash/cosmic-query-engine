# CLAUDE.md — Cosmic Query Engine

This file is the primary context document for Claude Code.
Read this before touching any file in this project.
The full spec contract is in `SPEC.md`. This file is the operational briefing.

---

## What this project is

A multi-head esoteric query engine. The user asks a question about their future or
life direction. The system collects their birth data and runs it through six knowledge
heads — Vedic astrology, Western astrology, Numerology, Chinese astrology, Philosophy,
and optionally I Ching. It synthesises findings into a 1–2 paragraph honest reading.
No flattery. No hallucination. No false optimism.

Full feature spec: `SPEC.md`
Divergence log: `DIVERGENCES.md`

---

## Architecture overview

```
cosmic-query-engine/
├── backend/                  # Django API — owns all computation
│   ├── core/                 # Session management, data pool, S-14/15/16
│   ├── heads/                # One app per head engine
│   │   ├── vedic/            # S-05
│   │   ├── western/          # S-06
│   │   ├── numerology/       # S-07
│   │   ├── chinese/          # S-08
│   │   ├── philosophy/       # S-09
│   │   └── iching/           # S-10
│   ├── collection/           # S-01, S-02, S-03 — data collection layer
│   ├── synthesis/            # S-11, S-12, S-13 — synthesis and output
│   ├── api/                  # DRF viewsets and URL routing
│   ├── config/               # Django settings, WSGI, ASGI
│   └── manage.py
├── frontend/                 # React + Vite web client
│   ├── src/
│   │   ├── components/       # Chat UI, summary display, trail accordion
│   │   ├── hooks/            # useSession, useStream, useCollection
│   │   ├── pages/            # Session start, reading, trail
│   │   └── api/              # API client — thin wrapper over fetch
│   ├── index.html
│   └── vite.config.js
├── mobile/                   # Flutter client
│   ├── lib/
│   │   ├── screens/          # Chat, reading, trail bottom sheet
│   │   ├── widgets/          # Reusable UI components
│   │   ├── services/         # API client, local profile cache
│   │   └── models/           # Session, profile, reading data models
│   └── pubspec.yaml
├── SPEC.md                   # Full feature spec — source of truth
├── DIVERGENCES.md            # Divergence log — update on every deviation
├── DECISIONS.md              # Architectural decisions log
├── .env.example              # Required environment variables
└── CLAUDE.md                 # This file
```

---

## Tech stack

### Backend
- **Language:** Python 3.11+
- **Framework:** Django 5.x + Django REST Framework
- **Async:** Django Channels (for streaming synthesis output)
- **Ephemeris:** pyswisseph (Swiss Ephemeris Python bindings) — validate first before any head engine work
- **LLM:** Anthropic Claude API (server-side only — never called from client)
- **Database:** PostgreSQL (profile storage, session persistence)
- **Cache:** Redis (session context during active sessions)
- **Task queue:** Celery + Redis (parallel head engine execution)

### Web frontend
- **Framework:** React 18 + Vite
- **Language:** TypeScript
- **Styling:** Tailwind CSS
- **State:** Zustand (session state, reading state)
- **API:** Native fetch with streaming support

### Mobile
- **Framework:** Flutter 3.x (Dart)
- **State:** Riverpod
- **Local storage:** flutter_secure_storage (profile cache only)
- **API:** Dio (HTTP client with streaming support)

---

## Terminal commands

### Backend setup
```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example ../.env        # then fill in real values
python manage.py migrate
python manage.py runserver
```

### Backend tests
```bash
cd backend
python manage.py test             # run all tests
python manage.py test heads.vedic # run single app tests
```

### Celery worker (parallel head execution)
```bash
cd backend
celery -A config worker --loglevel=info
```

### Frontend setup
```bash
cd frontend
npm install
npm run dev                       # development server
npm run build                     # production build
npm run preview                   # preview production build
```

### Mobile setup
```bash
cd mobile
flutter pub get
flutter run                       # runs on connected device or emulator
flutter build apk                 # Android production build
flutter build ios                 # iOS production build
```

### Validate Swiss Ephemeris (run this before any head engine work)
```bash
cd backend
python -c "
import swisseph as swe
swe.set_ephe_path('./ephe')
jd = swe.julday(1990, 3, 15, 10.5)
result = swe.calc_ut(jd, swe.MOON)
print('Moon longitude:', result[0][0])
print('Swiss Ephemeris OK')
"
```

---

## Slice build order

Build in this exact order — dependencies flow downward:

```
1. S-01  Data collection layer         collection/
2. S-02  Birth time tier detection     collection/
3. S-03  Moon sign ambiguity           collection/
--- foundation complete ---
4. S-07  Numerology head               heads/numerology/   ← start here, no ephemeris
5. S-08  Chinese astrology head        heads/chinese/      ← no ephemeris
6. S-09  Philosophy head               heads/philosophy/   ← no ephemeris, LLM call
7. S-05  Vedic astrology head          heads/vedic/        ← requires pyswisseph
8. S-06  Western astrology head        heads/western/      ← requires pyswisseph
9. S-10  I Ching head                  heads/iching/       ← requires LLM call
--- heads complete ---
10. S-11  Synthesis layer              synthesis/          ← requires LLM call
11. S-12  Confidence note generator    synthesis/
12. S-13  Explainability trail         synthesis/
--- synthesis complete ---
13. S-14  Session context              core/
14. S-15  Profile save prompt          core/
15. S-16  Profile load and confirm     core/
--- session complete ---
16. API endpoints                      api/
17. Web frontend                       frontend/
18. Mobile client                      mobile/
```

---

## Coding conventions

### Python / Django
- PEP 8 strictly — use `black` for formatting, `flake8` for linting
- Type hints on all function signatures
- Docstrings on every class and public method
- Each slice maps to one Django app — never mix slice logic across apps
- Services pattern — business logic in `services.py`, not in views or models
- No logic in serializers — serializers serialise only
- Tests in `tests/` directory within each app — one test file per service

### TypeScript / React
- Strict TypeScript — no `any` types
- Functional components only — no class components
- Custom hooks for all API interaction — never call fetch directly from components
- Components are display-only — no business logic in components
- One component per file

### Flutter / Dart
- Riverpod for all state — no setState outside of local UI state
- Services layer for all API calls — screens never call API directly
- Models are immutable — use `copyWith` pattern
- All API response parsing in model `fromJson` factories

### Universal
- Every function that talks to an external service (ephemeris, LLM, database)
  must have an explicit failure path — no bare `try/except` that swallows errors
- Log every external call with its inputs and outputs at DEBUG level
- Every slice has a corresponding test that verifies its done condition exactly
- No magic numbers — all constants in a dedicated `constants.py` / `constants.ts`

---

## Slice contract discipline

Before building any slice:
1. Read its contract in `SPEC.md`
2. Read every contract listed in its inputs
3. Write one sentence: "This is done when..."
4. Only then open a code file

When implementation diverges from contract:
1. Stop
2. Open `DIVERGENCES.md`
3. Log the divergence with four fields: date, slice, what diverged, decision
4. Either fix the code or update the spec — never leave it unresolved

---

## Key constraints Claude Code must never violate

- LLM calls (Anthropic API) are made server-side only — never from frontend or mobile
- Swiss Ephemeris calculations are backend only — never on client
- The frontend is a stateless display layer — no conversation logic on client
- Session context lives in Redis — never in browser localStorage or Flutter local storage
- Profile data (birth info) may be cached locally on mobile — reading content never
- Birth time is always free text — never a time picker widget on any surface
- The synthesis summary is always prose — never a list, never uses the word "journey"

---

## Environment variables needed

See `.env.example` for the full list with descriptions.
Never commit `.env` to version control.
Never hardcode any key or secret anywhere in the codebase.

---

## External dependencies to validate before building

In priority order:

1. **pyswisseph** — validate moon and planetary calculations return expected shape
2. **Anthropic Claude API** — validate streaming response works server-side
3. **Redis** — validate session read/write latency is acceptable
4. **PostgreSQL** — validate profile read/write with encrypted fields
5. **Chinese calendar library** — validate lunisolar conversion for January/February dates
6. **Celery** — validate parallel task execution with mock head engines

Do not start a head engine until its dependency is validated.
