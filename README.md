# LearnEnglish

Medical English practice platform for residents (MVP stack from `docs/brief.md` §10.1).

## Monorepo layout

| Path | Role |
|------|------|
| `backend/` | FastAPI API (`GET /health` today) |
| `frontend/` | Vite + React + TypeScript + Tailwind |
| `schemas/` | Shared JSON Schema (story 1.2+) |

## Prerequisites

- **Python** 3.12+ and [uv](https://docs.astral.sh/uv/) (`uv` on `PATH`; often `$HOME/.local/bin`)
- **Node.js** `^20.19.0 || >=22.12.0` (Vite 8 engines) and npm

## Backend

```bash
cd backend
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Health check:

```bash
curl -sf http://127.0.0.1:8000/health
# {"status":"ok","service":"learn-english-api"}
```

Tests:

```bash
cd backend
uv run pytest
```

## Frontend

```bash
cd frontend
npm install
npm run dev      # http://127.0.0.1:5173
npm run build    # production assets in frontend/dist
```

## Stack versions (scaffold)

Pinned via lockfiles — see `backend/uv.lock` and `frontend/package-lock.json`. At scaffold time:

- FastAPI + Uvicorn (Python ≥3.12)
- Vite 8 + React 19 + TypeScript + Tailwind CSS 4 (`@tailwindcss/vite`)
