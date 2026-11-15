from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.admin.router import router as admin_router
from app.auth.router import router as auth_router
from app.auth.settings import AuthSettings, get_auth_settings
from app.cases.service import get_case_repository
from app.dialogues.service import get_dialogue_repository
from app.editor.router import router as editor_router
from app.facts.service import get_fact_repository
from app.storage.router import router as storage_router
from app.users.service import get_user_repository


def create_app(settings: AuthSettings | None = None) -> FastAPI:
    resolved = settings or get_auth_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        get_user_repository()
        get_case_repository()
        get_fact_repository()
        get_dialogue_repository()
        yield

    application = FastAPI(
        title="LearnEnglish API",
        version="0.1.0",
        lifespan=lifespan,
    )

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
    application.include_router(admin_router)
    application.include_router(editor_router)
    application.include_router(storage_router)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "learn-english-api"}

    return application


app = create_app()
