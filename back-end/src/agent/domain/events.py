"""Contract B event vocabulary, independent of the SDK and of HTTP framing."""

import json
from dataclasses import dataclass, field
from typing import Any, Literal

EventName = Literal["token", "tool_start", "tool_end", "done", "error"]


@dataclass(frozen=True)
class SseEvent:
    name: EventName
    data: dict[str, Any] = field(default_factory=dict)

    def to_sse(self) -> dict[str, str]:
        """Shape accepted by sse-starlette: `event:` name plus a JSON `data:` line.

        `type` is repeated inside the payload so a client can dispatch on either.
        """
        return {
            "event": self.name,
            "data": json.dumps({"type": self.name, **self.data}),
        }
