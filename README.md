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
