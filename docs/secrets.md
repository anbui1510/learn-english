# Secrets (API / OAuth)

## Where secrets live

| Secret | Used by | Where to set |
| --- | --- | --- |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | FastAPI OAuth | Backend host env / `backend/.env` (see `.env.example`) |
| `JWT_SECRET` / `SESSION_SECRET` | Session cookies | Backend host env |
| TTS / Gemini / Azure / GCS keys | Backend providers | Backend host env |
| `VITE_API_BASE_URL` | SPA build | Local/CI build env for Capacitor or Vite **only** (not Cursor App Secrets) |

OAuth client secrets must **never** ship in the frontend bundle or custom URI scheme.

## Cursor published web app

The published SPA is static. Cursor App Secrets **cannot** bind names starting with `VITE_` (reserved). Google OAuth keys therefore stay on the **API server**, not in Cursor Secrets for this frontend.

1. Open [Cursor Secrets](https://cursor.com/dashboard?tab=secrets) (or the Secrets panel when publishing).
2. Add values for names your **server** (or a future server function) actually reads — not `VITE_*`.
3. Ask the agent to `bind-app-secrets` for those names, or re-publish after binding.
4. Never paste secret values into chat.

For this repo today: point a production API at HTTPS, set `GOOGLE_*` / `JWT_*` there, and build the SPA with `VITE_API_BASE_URL=https://your-api.example` (Capacitor/CI). Dev keeps the localhost default automatically.

## Mobile OAuth handoff

Native login uses PKCE: the deep link carries only a one-time `code`. The `code_verifier` stays in `sessionStorage` and is sent to `POST /auth/exchange`. JWT and OAuth client secrets never appear in `com.learnenglish.app://…` URLs.
