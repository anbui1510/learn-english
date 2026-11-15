# LearnEnglish

Medical English practice platform for residents (MVP stack from `docs/brief.md` §10.1).

## Monorepo layout

| Path | Role |
|------|------|
| `backend/` | FastAPI API (`/health`, Google OAuth, roles) |
| `frontend/` | Vite + React + TypeScript + Tailwind |
| `schemas/` | Shared JSON Schema (story 1.2+) |

## Prerequisites

- **Python** 3.12+ and [uv](https://docs.astral.sh/uv/) (`uv` on `PATH`; often `$HOME/.local/bin`)
- **Node.js** `^20.19.0 || >=22.12.0` (Vite 8 engines) and npm
- Google Cloud **OAuth 2.0 Web client** for local login (optional for API health / unit tests)

## Backend

```bash
cd backend
cp .env.example .env   # fill Google + JWT secrets + BOOTSTRAP_ADMIN_EMAILS
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Health check:

```bash
curl -sf http://127.0.0.1:8000/health
# {"status":"ok","service":"learn-english-api"}
```

Tests (OAuth Google calls are mocked):

```bash
cd backend
uv run pytest
```

CI (`.github/workflows/ci.yml`) runs backend `pytest` and frontend `npm run build` on every push/PR.

### Auth endpoints

| Method | Path | Behavior |
|--------|------|----------|
| `GET` | `/auth/google/login` | Redirect to Google (503 if env missing) |
| `GET` | `/auth/google/callback` | Upsert user + httpOnly JWT cookie → SPA |
| `GET` | `/auth/me` | Current user + **role** from DB (`401` if anonymous) |
| `POST` | `/auth/logout` | Clear session cookie |

### Admin role endpoints

| Method | Path | Behavior |
|--------|------|----------|
| `GET` | `/admin/users` | List users (admin only) |
| `PATCH` | `/admin/users/{id}/role` | Assign `admin` / `editor` / `learner` + audit |
| `GET` | `/admin/users/{id}/role-audit` | who/when/old→new |

Roles persist in SQLite (`DATABASE_PATH`, default `backend/data/learn_english.sqlite3`). New Google users default to `learner`. Emails in `BOOTSTRAP_ADMIN_EMAILS` become `admin` on first login.

### Editor RBAC + Case ownership + PDF ingest

| Method | Path | Behavior |
|--------|------|----------|
| `GET` | `/editor/ping` | Editor/admin `200`; learner `403`; anonymous `401` |
| `POST` | `/editor/cases` | Create draft Case owned by caller (`owner_user_id`) |
| `POST` | `/editor/cases/upload` | Multipart PDF + title/ISBN/edition → Case draft + object key |
| `GET` | `/editor/cases` | List cases owned by caller |
| `GET` | `/editor/cases/{id}` | Case detail including extract job status |
| `POST` | `/editor/cases/{id}/extract` | Queue in-process fact extraction (owner/admin) |
| `GET` | `/editor/cases/{id}/facts` | List facts; optional `status` / `category` filters |
| `PATCH` | `/editor/cases/{id}/facts/{fact_id}` | Verify / reject / edit fact (+ status audit) |
| `POST` | `/editor/cases/{id}/publish` | Publish when ≥1 verified and 0 `needs_review` |
| `POST` | `/editor/cases/{id}/generate-dialogues` | Generate 1–3 CEFR dialogues from verified facts (`409` if draft) |
| `GET` | `/editor/cases/{id}/dialogues` | List generated dialogues for a Case |
| `GET` | `/editor/cases/{id}/download-url` | Time-limited signed URL (owner/admin); learner `403` |
| `GET` | `/editor/cases/{id}/pdf` | Session stream of PDF for owner/admin |
| `GET` | `/storage/local` | Local adapter signed-URL download |

**RBAC matrix:** learner → 403 on editor routes; editor and admin → allowed. Cases must be owned by an editor or admin user id. Shared contracts: `schemas/case.schema.json`, `schemas/clinical-fact.schema.json`.

**Storage:** local filesystem under `STORAGE_ROOT` by default. Set `GCS_BUCKET` (and install `google-cloud-storage`) to use GCS. `PDF_MAX_BYTES` defaults to 25 MB.

**Fact extraction:** parser port defaults to pypdf + clinical heading heuristics (Docling optional when installed). Facts default to `needs_review` and validate against the clinical-fact schema before write.

**Editorial workflow:** fact status may be `needs_review` | `verified` | `rejected` (audited). Publish sets `published_at` + `published_by_user_id`.

**Dialogue generation:** generator port defaults to a template builder from verified facts (set `GEMINI_API_KEY` for the Gemini adapter path). Contexts: `patient_family`, `colleague_sbar`, `expert_cme`. Each line cites `fact_ids`; optional `text_vi`; warns when estimated duration exceeds ~150s.

### Learner practice (epics 6–10)

| Method | Path | Behavior |
|--------|------|----------|
| `POST` | `/editor/cases/{id}/dialogues/{dialogue_id}/synthesize` | TTS utterances + word timestamps (synthetic CI default) |
| `GET` | `/learner/cases` | Published case library |
| `GET` | `/learner/cases/{id}/dialogues` | Dialogues for a published case |
| `GET` | `/learner/dialogues/{id}/lesson` | Karaoke playlist + citation metadata |
| `GET` | `/learner/dialogues/{id}/shadowing` | Exactly 10 shadowing cards |
| `GET`/`PATCH` | `/learner/profile` | 6-month path + lessons/week + CEFR package |
| `POST` | `/learner/completions` | Mark karaoke+shadowing complete |
| `POST` | `/learner/attempts/audio` | Upload LearningAttempt + optional PA score (synthetic default) |
| `POST` | `/learner/attempts/{id}/score` | Re-score an attempt against a dialogue line (rate-limited) |
| `GET` | `/learner/srs/queue` | Weak-phrase SRS cards due through T+1 (`horizon_days`) |
| `POST` | `/learner/srs/{id}/done` | Mark an SRS card complete |

TTS defaults to a silent-WAV synthetic engine (CI-safe). Set `USE_EDGE_TTS=true` and install optional `edge-tts` to use the async Edge adapter (falls back to synthetic on missing SDK/network errors).

**Pha 2 pronunciation:** upload/score returns pronunciation / completeness / prosody plus per-word green/yellow/red bands. Default engine is synthetic (CI-safe). Set `USE_AZURE_PA=true` + `AZURE_SPEECH_KEY` (optional `uv sync --group speech`) for Azure: WebM/other formats convert to 16 kHz mono PCM via ffmpeg, then Speech SDK Pronunciation Assessment; failures fall back to synthetic. `PA_DAILY_LIMIT` caps score calls per user/day.

**Pha 2 learning loop:** red/yellow PA words enqueue SRS cards for T+1. Role-play supports `read_along` vs `free_speech`; free speech adds synthetic empathy rubric + clinical disclaimer (`USE_GEMINI_EMPATHY` reserved).

**Pha 2 progression:** lesson completion awards virtual CME (+ role-play PA bonus). Rank ladder Medical Student → Chief of Staff. Editors set `module_slug` / unlock CME / unlock rank / prerequisite case (cycle-safe). Module CME threshold issues a shareable digital certificate with disclaimer.

**Pha 2 skill tree + replay:** `GET /learner/skill-tree` exposes Nhi đại cương → Tim mạch nhi locks; cases inherit module locks. Tap a red PA word to `.../words/{word}/replay` the AI TTS snippet.

**Pha 2 streak + PA cost log:** editors can require an N-day learning streak to unlock a case; `GET /admin/pa-usage` lists score calls/user/day with optional `PA_COST_PER_SCORE_USD` estimates.

**Pha 2 empathy coaching + cert share:** free-speech empathy below threshold returns `coaching_tip` + `sample_phrase` (play via `POST /learner/empathy/sample-audio`). Certificates expose a public `?cert=` share view and copy-link control.

**Pha 3 presentation sessions:** editors can generate `session_kind=presentation` (~10 min CME talk) with fact-bound expanded lines + per-line TTS chunking; learners see a progress bar on long playlists.

### Google OAuth setup (manual verify)

1. Create an OAuth 2.0 **Web application** client in Google Cloud Console.
2. Authorized redirect URI: `http://127.0.0.1:8000/auth/google/callback` (match `GOOGLE_REDIRECT_URI`).
3. Copy client id/secret into `backend/.env` with `JWT_SECRET`, `SESSION_SECRET`, and your email in `BOOTSTRAP_ADMIN_EMAILS`.
4. Start API + frontend, sign in, open the admin **User roles** panel, assign `editor` to another user, confirm their `/auth/me` shows `editor` (not admin).

## Frontend

```bash
cd frontend
cp .env.example .env   # optional; defaults to http://127.0.0.1:8000
npm install
npm run dev      # http://127.0.0.1:5173
npm run build    # production assets in frontend/dist
```

The SPA calls the API with `credentials: 'include'` so the httpOnly session cookie is sent cross-origin (CORS allows `FRONTEND_ORIGIN`). Admins see a role assignment table after sign-in.

## Stack versions (scaffold)

Pinned via lockfiles — see `backend/uv.lock` and `frontend/package-lock.json`. At scaffold time:

- FastAPI + Uvicorn + Authlib + PyJWT + SQLite users (Python ≥3.12)
- Vite 8 + React 19 + TypeScript + Tailwind CSS 4 (`@tailwindcss/vite`)
