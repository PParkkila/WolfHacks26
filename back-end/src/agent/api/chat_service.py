"""One chat turn: run the agent, stream Contract B events, never raise.

Every failure becomes a normal reply or an `error` event, because an exception
would kill the stream mid-answer.
"""

import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

from agents import Agent, InputGuardrailTripwireTriggered, MaxTurnsExceeded, Runner

from agent.api.sessions import SessionFactory
from agent.api.sse import StreamTranslator
from agent.domain.events import SseEvent
from agent.guardrails import decline_message
from agent.observability.trace import Tracer

log = logging.getLogger(__name__)

MAX_TURNS_REPLY = (
    "I couldn't finish working that out within my step limit. "
    "Try a narrower question, for example about one person."
)

RunStreamed = Callable[..., Any]


class ChatService:
    def __init__(
        self,
        agent: Agent,
        sessions: SessionFactory,
        tracer: Tracer,
        max_turns: int,
        run_streamed: RunStreamed = Runner.run_streamed,
    ) -> None:
        self._agent = agent
        self._sessions = sessions
        self._tracer = tracer
        self._max_turns = max_turns
        self._run_streamed = run_streamed

    async def stream(self, session_id: str, message: str) -> AsyncIterator[SseEvent]:
        recorder = self._tracer.start(session_id, message)
        translator = StreamTranslator()
        outcome, failure = "cancelled", None  # stays so if the client disconnects
        pending: list[SseEvent] = []
        try:
            try:
                result = self._run_streamed(
                    self._agent,
                    message,
                    session=self._sessions(session_id),
                    max_turns=self._max_turns,
                )
                async for raw in result.stream_events():
                    for event in translator.translate(raw):
                        recorder.record(event)
                        yield event
                outcome = "ok"
            except InputGuardrailTripwireTriggered as exc:
                outcome = "declined"
                info = exc.guardrail_result.output.output_info
                pending.append(SseEvent("token", {"text": decline_message(info)}))
            except MaxTurnsExceeded:
                outcome = "max_turns"
                pending.append(SseEvent("token", {"text": MAX_TURNS_REPLY}))
            except Exception as exc:
                log.exception("chat turn failed")
                outcome, failure = "error", f"{type(exc).__name__}: {exc}"
                pending.append(
                    SseEvent(
                        "error",
                        {
                            "message": "Something went wrong answering that.",
                            "recoverable": True,
                        },
                    )
                )

            pending.append(SseEvent("done", {"session_id": session_id}))
            for event in pending:
                recorder.record(event)
                yield event
        finally:
            recorder.finish(outcome, failure)
