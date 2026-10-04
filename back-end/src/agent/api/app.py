"""FastAPI wiring: auth, dashboard, chat (SSE) and health."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent.api import chat, dashboard, login
from agent.api.deps import install_error_handlers
from agent.api.schemas import Health
from agent.bootstrap import Runtime, build_runtime

log = logging.getLogger(__name__)


def create_app(runtime: Runtime) -> FastAPI:
    app = FastAPI(title="Gluco API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime.settings.allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.runtime = runtime
    install_error_handlers(app)
    for module in (login, dashboard, chat):
        app.include_router(module.router)

    @app.get("/health", tags=["health"])
    def health() -> Health:
        db = runtime.source.ping()
        try:
            windows, people = runtime.store.size(), len(runtime.store.participants())
            clock = runtime.clock.state()
        except Exception:
            log.exception("store unavailable")
            windows, people, clock = 0, 0, None
        return Health(
            db=db,
            llm=runtime.llm.is_ready(),
            windows=windows,
            participants=people,
            clock=clock,
        )

    return app


def create_default_app() -> FastAPI:
    """Factory for uvicorn: `uvicorn agent.api.app:create_default_app --factory`."""
    return create_app(build_runtime())
