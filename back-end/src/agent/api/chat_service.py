"""One chat turn: run the agent, stream Contract B events, never raise.

Every failure becomes a normal reply or an `error` event, because an exception
would kill the stream mid-answer.
"""

import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

from agents import Agent, InputGuardrailTripwireTriggered, MaxTurnsExceeded, Runner

from agent.analysis.grounding import ungrounded_numbers
from agent.api.sessions import SessionFactory
from agent.api.sse import StreamTranslator
from agent.domain.events import SseEvent
from agent.guardrails import decline_message
from agent.observability.trace import Outcome, Tracer

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
        outcome: Outcome = "cancelled"  # stays so if the client disconnects
        failure: str | None = None
        answer: list[str] = []
        ungrounded: list[str] = []
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
                        if event.name == "token":
                            answer.append(event.data["text"])
                        yield event
                outcome = "ok"
                ungrounded = ungrounded_numbers(
                    "".join(answer), message, *translator.tool_outputs
                )
                if ungrounded:
                    log.warning("answer states ungrounded numbers: %s", ungrounded)
            except InputGuardrailTripwireTriggered as exc:
                outcome = "declined"
                pending.append(SseEvent("token", {"text": decline_message(exc)}))
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

            done: dict[str, Any] = {"session_id": session_id}
            if ungrounded:  # additive: absent unless the check found something
                done["ungrounded_numbers"] = ungrounded
            pending.append(SseEvent("done", done))
            for event in pending:
                recorder.record(event)
                yield event
        finally:
            recorder.finish(outcome, failure, ungrounded)
