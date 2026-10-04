"""Contract B event vocabulary, independent of the SDK and of HTTP framing."""

from dataclasses import dataclass, field
from typing import Any, Literal

EventName = Literal["token", "tool_start", "tool_end", "done", "error"]


@dataclass(frozen=True)
class SseEvent:
    name: EventName
    data: dict[str, Any] = field(default_factory=dict)


class EventHandler:
    """Consumes Contract B events. Override the `on_*` hooks you care about.

    `handle` is the one place that switches on `event.name`, so adding an event
    kind touches this class instead of every consumer.
    """

    def handle(self, event: SseEvent) -> None:
        match event.name:
            case "token":
                self.on_token(event.data)
            case "tool_start":
                self.on_tool_start(event.data)
            case "tool_end":
                self.on_tool_end(event.data)
            case "error":
                self.on_error(event.data)
            case "done":
                self.on_done(event.data)

    def on_token(self, data: dict[str, Any]) -> None:
        pass

    def on_tool_start(self, data: dict[str, Any]) -> None:
        pass

    def on_tool_end(self, data: dict[str, Any]) -> None:
        pass

    def on_error(self, data: dict[str, Any]) -> None:
        pass

    def on_done(self, data: dict[str, Any]) -> None:
        pass
