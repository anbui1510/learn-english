from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.auth.router import router as auth_router
from app.auth.settings import AuthSettings, get_auth_settings


def create_app(settings: AuthSettings | None = None) -> FastAPI:
    resolved = settings or get_auth_settings()
    application = FastAPI(title="LearnEnglish API", version="0.1.0")

    session_secret = resolved.session_secret or "dev-session-secret-change-me"
    application.add_middleware(
        SessionMiddleware,
        secret_key=session_secret,
        same_site="lax",
        https_only=resolved.cookie_secure,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[resolved.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(auth_router)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "learn-english-api"}

    return application


app = create_app()
