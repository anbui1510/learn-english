# LearnEnglish

Medical English practice platform for residents (MVP stack from `docs/brief.md` §10.1).

## Monorepo layout

| Path | Role |
|------|------|
| `backend/` | FastAPI API (`/health`, Google OAuth session) |
| `frontend/` | Vite + React + TypeScript + Tailwind |
| `schemas/` | Shared JSON Schema (story 1.2+) |

## Prerequisites

- **Python** 3.12+ and [uv](https://docs.astral.sh/uv/) (`uv` on `PATH`; often `$HOME/.local/bin`)
- **Node.js** `^20.19.0 || >=22.12.0` (Vite 8 engines) and npm
- Google Cloud **OAuth 2.0 Web client** for local login (optional for API health / unit tests)

## Backend

```bash
cd backend
cp .env.example .env   # fill Google + JWT secrets for login
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

### Auth endpoints

| Method | Path | Behavior |
|--------|------|----------|
| `GET` | `/auth/google/login` | Redirect to Google (503 if env missing) |
| `GET` | `/auth/google/callback` | Exchange code → httpOnly JWT cookie → redirect to SPA |
| `GET` | `/auth/me` | Current user from cookie (`401` if anonymous) |
| `POST` | `/auth/logout` | Clear session cookie |

### Google OAuth setup (manual verify)

1. Create an OAuth 2.0 **Web application** client in Google Cloud Console.
2. Authorized redirect URI: `http://127.0.0.1:8000/auth/google/callback` (match `GOOGLE_REDIRECT_URI`).
3. Copy client id/secret into `backend/.env` along with long random `JWT_SECRET` and `SESSION_SECRET`.
4. Start API + frontend, open the SPA, click **Sign in with Google**, confirm `/auth/me`, then **Log out**.

## Frontend

```bash
cd frontend
cp .env.example .env   # optional; defaults to http://127.0.0.1:8000
npm install
npm run dev      # http://127.0.0.1:5173
npm run build    # production assets in frontend/dist
```

The SPA calls the API with `credentials: 'include'` so the httpOnly session cookie is sent cross-origin (CORS allows `FRONTEND_ORIGIN`).

## Stack versions (scaffold)

Pinned via lockfiles — see `backend/uv.lock` and `frontend/package-lock.json`. At scaffold time:

- FastAPI + Uvicorn + Authlib + PyJWT (Python ≥3.12)
- Vite 8 + React 19 + TypeScript + Tailwind CSS 4 (`@tailwindcss/vite`)
