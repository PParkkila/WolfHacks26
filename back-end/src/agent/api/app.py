"""FastAPI wiring for Contract B: POST /chat (SSE), GET /health, GET /tools."""

import logging
from typing import Annotated

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, StringConstraints
from sse_starlette.sse import EventSourceResponse

from agent.api.sse import sse_frame
from agent.bootstrap import Runtime, build_runtime

log = logging.getLogger(__name__)

SessionId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,128}$")]
Message = Annotated[str, StringConstraints(min_length=1, max_length=4000)]

# Stop proxies (nginx etc.) from buffering the stream, which looks like a freeze.
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


class ChatRequest(BaseModel):
    session_id: SessionId
    message: Message


def create_app(runtime: Runtime) -> FastAPI:
    app = FastAPI(title="PulseCast agent")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime.settings.allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.post("/chat")
    async def chat(request: ChatRequest) -> EventSourceResponse:
        async def events():
            async for event in runtime.chat.stream(request.session_id, request.message):
                yield sse_frame(event)

        return EventSourceResponse(events(), headers=SSE_HEADERS)

    @app.get("/health")
    def health() -> dict[str, object]:
        db = runtime.repos.health.ping()
        model_version = None
        if db:
            try:
                model_version = runtime.repos.health.model_version()
            except Exception:
                log.exception("model_version lookup failed")
        return {
            "db": db,
            "llm": runtime.llm.is_ready(),
            "model_version": model_version,
        }

    @app.get("/tools")
    def tools() -> list[dict[str, object]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.params_json_schema,
            }
            for tool in runtime.tools
        ]

    return app


def create_default_app() -> FastAPI:
    """Factory for uvicorn: `uvicorn agent.api.app:create_default_app --factory`."""
    return create_app(build_runtime())
