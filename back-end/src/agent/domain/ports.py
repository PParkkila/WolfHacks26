"""The read-only data port. The store depends on it, never on a concrete backend."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from agent.domain.models import LiveReading, Window


@dataclass(frozen=True)
class PublishedWindow:
    window: Window
    published_at: datetime


class WindowSource(Protocol):
    def fetch_since(self, published_after: datetime | None) -> list[PublishedWindow]:
        """Every window published at or after `published_after` (all if None).

        Re-published windows come back again; the caller merges by
        (person_id, window_end), so overlap is harmless.
        """
        ...

    def fetch_live(self) -> list[LiveReading]:
        """Every participant's newest sensor readings (one per participant)."""
        ...

    def ping(self) -> bool: ...
