"""Chat endpoints: one streamed turn, and the caller's own threads."""

from typing import Any

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from agent.api.dashboard import SSE_HEADERS
from agent.api.deps import CurrentPrincipal, RuntimeDep
from agent.api.schemas import ChatRequest, SessionId
from agent.api.sessions import ChatMessage, ChatThread
from agent.api.sse import sse_frame

router = APIRouter(tags=["chat"])


@router.post("/chat")
async def chat_turn(
    request: ChatRequest, runtime: RuntimeDep, principal: CurrentPrincipal
) -> EventSourceResponse:
    async def events():
        async for event in runtime.chat.stream(
            principal, request.session_id, request.message
        ):
            yield sse_frame(event)

    return EventSourceResponse(events(), headers=SSE_HEADERS)


@router.get("/chat/sessions")
def threads(runtime: RuntimeDep, principal: CurrentPrincipal) -> list[ChatThread]:
    return runtime.sessions.threads(principal.user_id)


@router.get("/chat/sessions/{session_id}")
async def thread(
    session_id: SessionId, runtime: RuntimeDep, principal: CurrentPrincipal
) -> list[ChatMessage]:
    if not runtime.sessions.owns(principal.user_id, session_id):
        raise HTTPException(404, "We couldn't find that conversation.")
    return await runtime.sessions.messages(principal.user_id, session_id)


@router.get("/tools")
def tools(runtime: RuntimeDep, principal: CurrentPrincipal) -> list[dict[str, Any]]:
    """The tools the caller's chatbot can use, with their JSON schemas."""
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.params_json_schema,
        }
        for tool in runtime.tools_for(principal)
    ]
