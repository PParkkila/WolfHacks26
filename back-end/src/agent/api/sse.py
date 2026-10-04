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


def sse_frame(event: SseEvent) -> dict[str, str]:
    """Shape accepted by sse-starlette: `event:` name plus a JSON `data:` line.

    `type` is repeated inside the payload so a client can dispatch on either.
    """
    return {
        "event": event.name,
        "data": json.dumps({"type": event.name, **event.data}),
    }


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
    """Stateful per request: the one place that pairs a tool call with its result.

    Both events carry the same `call_id`, so consumers (trace, frontend chips)
    never have to pair by tool name, which breaks on parallel calls to one tool.
    """

    def __init__(self) -> None:
        self._open_calls: dict[str, str] = {}  # call_id -> tool, oldest first
        self._generated = 0
        self.tool_outputs: list[Any] = []  # every result seen, for grounding checks

    def translate(self, event: StreamEvent) -> list[SseEvent]:
        if isinstance(event, RawResponsesStreamEvent):
            if event.data.type == TEXT_DELTA:
                return [SseEvent("token", {"text": event.data.delta})]
            return []
        if isinstance(event, RunItemStreamEvent):
            if event.name == "tool_called":
                return [self._tool_start(event.item)]
            if event.name == "tool_output":
                end = self._tool_end(event.item)
                return [end, *self._chart(end, event.item.output)]
        return []

    def _tool_start(self, item: Any) -> SseEvent:
        raw = item.raw_item
        tool = _field(raw, "name") or getattr(item, "tool_name", None) or "unknown"
        call_id = _field(raw, "call_id")
        if not call_id:
            self._generated += 1
            call_id = f"call-{self._generated}"
        self._open_calls[call_id] = tool
        return SseEvent(
            "tool_start",
            {
                "call_id": call_id,
                "tool": tool,
                "args": _parse_args(_field(raw, "arguments")),
            },
        )

    @staticmethod
    def _chart(end: SseEvent, output: Any) -> list[SseEvent]:
        """A `data` event when the tool returned series to draw.

        A built widget rides along as `widget` (title, kind, query, steps), so
        the UI can show its pipeline and pin it.
        """
        if not isinstance(output, dict) or not isinstance(output.get("chart"), dict):
            return []
        data = {
            "call_id": end.data["call_id"],
            "tool": end.data["tool"],
            "chart": output["chart"],
        }
        if isinstance(output.get("widget"), dict):
            data["widget"] = output["widget"]
        return [SseEvent("data", data)]

    def _tool_end(self, item: Any) -> SseEvent:
        call_id = _field(item.raw_item, "call_id")
        if call_id not in self._open_calls:
            # No usable id on the result: pair with the oldest open call, if any.
            call_id = next(iter(self._open_calls), call_id or "unknown")
        tool = self._open_calls.pop(call_id, "unknown")
        output = item.output
        self.tool_outputs.append(output)
        if isinstance(output, dict):
            summary = output.get("summary") or output.get("error") or ""
            rows = output.get("rows", 0)
        else:
            summary, rows = str(output), 0
        return SseEvent(
            "tool_end",
            {
                "call_id": call_id,
                "tool": tool,
                "summary": str(summary)[:SUMMARY_LIMIT],
                "rows": rows,
            },
        )
