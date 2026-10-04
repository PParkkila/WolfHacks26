"""JSONL turn log. SDK tracing stays disabled because it uploads tool outputs.

The recorder is a plain consumer of Contract B events, so it needs no SDK types.
One line per turn: message, each tool call (args, rows, latency), answer, outcome.
"""

import json
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from agent.domain.events import EventHandler, SseEvent

# cancelled: the client disconnected before the turn finished.
Outcome = Literal["ok", "declined", "max_turns", "error", "cancelled"]


class TurnRecorder(Protocol):
    def record(self, event: SseEvent) -> None: ...

    def finish(
        self,
        outcome: Outcome,
        error: str | None = None,
        ungrounded: Sequence[str] = (),
    ) -> None: ...


class Tracer(Protocol):
    def start(self, session_id: str, message: str) -> TurnRecorder: ...


class _NullRecorder:
    def record(self, event: SseEvent) -> None:
        pass

    def finish(
        self,
        outcome: Outcome,
        error: str | None = None,
        ungrounded: Sequence[str] = (),
    ) -> None:
        pass


class NullTracer:
    def start(self, session_id: str, message: str) -> TurnRecorder:
        return _NullRecorder()


class _JsonlRecorder(EventHandler):
    def __init__(self, path: Path, session_id: str, message: str) -> None:
        self._path = path
        self._session_id = session_id
        self._message = message
        self._started = time.perf_counter()
        self._tokens: list[str] = []
        self._calls: list[dict[str, Any]] = []
        self._open_calls: dict[str, tuple[dict[str, Any], float]] = {}

    def record(self, event: SseEvent) -> None:
        self.handle(event)

    def on_token(self, data: dict[str, Any]) -> None:
        self._tokens.append(data["text"])

    def on_tool_start(self, data: dict[str, Any]) -> None:
        call = {"tool": data["tool"], "args": data["args"]}
        self._calls.append(call)
        self._open_calls[data["call_id"]] = (call, time.perf_counter())

    def on_tool_end(self, data: dict[str, Any]) -> None:
        now = time.perf_counter()
        call, started = self._open_calls.pop(data["call_id"], ({}, now))
        call.update(
            rows=data["rows"],
            summary=data["summary"],
            latency_ms=round((now - started) * 1000),
        )

    def finish(
        self,
        outcome: Outcome,
        error: str | None = None,
        ungrounded: Sequence[str] = (),
    ) -> None:
        line = {
            "ts": datetime.now(UTC).isoformat(),
            "session_id": self._session_id,
            "message": self._message,
            "tool_calls": self._calls,
            "answer": "".join(self._tokens),
            "latency_ms": round((time.perf_counter() - self._started) * 1000),
            "outcome": outcome,
            "error": error,
            "ungrounded_numbers": list(ungrounded),
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line) + "\n")


class JsonlTracer:
    def __init__(self, path: Path) -> None:
        self._path = path

    def start(self, session_id: str, message: str) -> TurnRecorder:
        return _JsonlRecorder(self._path, session_id, message)
