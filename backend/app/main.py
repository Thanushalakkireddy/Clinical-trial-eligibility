from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from contextlib import asynccontextmanager
from pydantic import BaseModel

from app.checkpoint import dispose_checkpointer
from app.config import settings
from app.database.session import dispose_database, persist_is_configured
from app.routers.assessments import router as assessments_router
from app.routers.contradiction import router as contradiction_router
from app.routers.decision import decision_router
from app.routers.exclusion import router as exclusion_router
from app.routers.inclusion import router as inclusion_router
from app.routers.patients import router as patients_router
from app.routers.rag import router as rag_router
from app.routers.trials import router as trials_router
from app.routers.workflow import router as workflow_router
from app.runtime_config import gemini_is_configured, require_runtime_config


class SecurityHeadersMiddleware:
    """Adds minimal production security headers to every response.

    Pure ASGI/middleware implementation with no third-party dependency.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = message.get("headers", [])
                extra = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"SAMEORIGIN"),
                    (b"referrer-policy", b"same-origin"),
                ]
                names = {h[0].lower() for h in headers}
                headers = headers + [h for h in extra if h[0] not in names]
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


class HealthResponse(BaseModel):
    status: str
    service: str
    gemini_configured: bool = False
    database_configured: bool = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Nothing to initialize eagerly at startup: the database engine and the
    # LangGraph checkpointer are created lazily on first use.
    yield
    # Controlled shutdown cleanup: close the checkpointer connection and dispose
    # the async engine pool so no PostgreSQL/SQLite handles leak across restarts.
    try:
        await dispose_checkpointer()
    finally:
        dispose_database()


def create_app() -> FastAPI:
    """FastAPI application factory.

    Normal application runs require real external services (Gemini, PostgreSQL)
    and fail fast with a clear configuration error when they are missing. The
    explicit test environment (``ENVIRONMENT=test``) is exempt so the automated
    suite can use isolated SQLite databases and mocked Gemini.
    """
    require_runtime_config(settings)

    # Debug mode is only safe for non-production environments. Forcing debug
    # off in production prevents FastAPI from returning tracebacks to clients
    # even if DEBUG is accidentally left enabled.
    safe_debug = settings.debug and settings.environment.lower() != "production"

    app = FastAPI(
        title=settings.app_name,
        description="Multi-Agent Clinical Trial Eligibility & Contradiction System API",
        version="0.1.0",
        debug=safe_debug,
        lifespan=lifespan,
    )

    # CORS Middleware configuration (origins are environment-configurable).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)

    # Mount API routers
    app.include_router(trials_router)
    app.include_router(patients_router)
    app.include_router(rag_router)
    app.include_router(inclusion_router)
    app.include_router(exclusion_router)
    app.include_router(contradiction_router)
    app.include_router(decision_router)
    app.include_router(workflow_router)
    app.include_router(assessments_router)

    @app.get("/health", response_model=HealthResponse, tags=["Health"])
    async def health_check() -> HealthResponse:
        """Health check endpoint.

        Reports availability as booleans only; never returns credentials or
        configuration values.
        """
        return HealthResponse(
            status="ok",
            service=settings.app_name,
            gemini_configured=gemini_is_configured(settings),
            database_configured=persist_is_configured(),
        )

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
