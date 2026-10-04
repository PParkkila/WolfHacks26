"""Translate Agents SDK stream events into Contract B events.

This is the only module that depends on SDK stream-event classes. If the SDK's
streaming shape changes, only this file changes.
"""

import json
from typing import Any

from agents import RawResponsesStreamEvent, RunItemStreamEvent, StreamEvent

from agent.domain.events import SseEvent

TEXT_DELTA = "response.output_text.delta"
SUMMARY_LIMIT = 300


def _field(obj: Any, name: str) -> Any:
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


def _parse_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


class StreamTranslator:
    """Stateful per request: remembers which tool each call id belongs to."""

    def __init__(self) -> None:
        self._tool_by_call: dict[str, str] = {}

    def translate(self, event: StreamEvent) -> list[SseEvent]:
        if isinstance(event, RawResponsesStreamEvent):
            if event.data.type == TEXT_DELTA:
                return [SseEvent("token", {"text": event.data.delta})]
            return []
        if isinstance(event, RunItemStreamEvent):
            if event.name == "tool_called":
                return [self._tool_start(event.item)]
            if event.name == "tool_output":
                return [self._tool_end(event.item)]
        return []

    def _tool_start(self, item: Any) -> SseEvent:
        raw = item.raw_item
        tool = _field(raw, "name") or getattr(item, "tool_name", None) or "unknown"
        call_id = _field(raw, "call_id")
        if call_id:
            self._tool_by_call[call_id] = tool
        return SseEvent(
            "tool_start", {"tool": tool, "args": _parse_args(_field(raw, "arguments"))}
        )

    def _tool_end(self, item: Any) -> SseEvent:
        call_id = _field(item.raw_item, "call_id")
        tool = self._tool_by_call.get(call_id, "unknown")
        output = item.output
        if isinstance(output, dict):
            summary = output.get("summary") or output.get("error") or ""
            rows = output.get("rows", 0)
        else:
            summary, rows = str(output), 0
        return SseEvent(
            "tool_end",
            {"tool": tool, "summary": str(summary)[:SUMMARY_LIMIT], "rows": rows},
        )
