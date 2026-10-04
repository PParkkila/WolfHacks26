"""In-memory copy of every published window, refreshed incrementally.

The dashboard data is small (one row per participant per hour), so the store
holds all of it and answers reads without a database round-trip. It re-reads
rows published since the last refresh at most every `refresh_s` seconds, so
rows Databricks publishes while the app runs show up without a restart.
"""

import bisect
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from agent.domain.models import Window
from agent.domain.ports import WindowSource

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Snapshot:
    """Immutable, so readers never need the lock."""

    by_person: dict[str, tuple[Window, ...]] = field(default_factory=dict)
    datasets: dict[str, str] = field(default_factory=dict)
    first_end: datetime | None = None
    last_end: datetime | None = None


class WindowStore:
    def __init__(
        self,
        source: WindowSource,
        refresh_s: float = 10.0,
        time_source: Callable[[], float] = time.monotonic,
    ) -> None:
        self._source = source
        self._refresh_s = refresh_s
        self._time = time_source
        self._lock = threading.Lock()
        self._rows: dict[tuple[str, datetime], Window] = {}
        self._last_published: datetime | None = None
        self._refreshed_at: float | None = None
        self._snapshot: _Snapshot | None = None

    # --- refresh ------------------------------------------------------------

    def refresh(self) -> int:
        """Merge newly published windows; returns how many rows arrived."""
        with self._lock:
            return self._refresh_locked()

    def _refresh_locked(self) -> int:
        published = self._source.fetch_since(self._last_published)
        for row in published:
            w = row.window
            self._rows[(w.person_id, w.window_end)] = w
            if self._last_published is None or row.published_at > self._last_published:
                self._last_published = row.published_at
        self._refreshed_at = self._time()
        if published or self._snapshot is None:
            self._snapshot = self._build_snapshot()
        return len(published)

    def invalidate(self) -> None:
        """Refresh on the next read rather than waiting out `refresh_s`."""
        self._refreshed_at = None

    def _build_snapshot(self) -> _Snapshot:
        by_person: dict[str, list[Window]] = {}
        for window in self._rows.values():
            by_person.setdefault(window.person_id, []).append(window)
        ordered = {
            pid: tuple(sorted(ws, key=lambda w: w.window_end))
            for pid, ws in sorted(by_person.items())
        }
        ends = [w.window_end for ws in ordered.values() for w in (ws[0], ws[-1])]
        return _Snapshot(
            by_person=ordered,
            datasets={pid: ws[-1].source_dataset for pid, ws in ordered.items()},
            first_end=min(ends, default=None),
            last_end=max(ends, default=None),
        )

    def _current(self) -> _Snapshot:
        """The snapshot, refreshed first if stale.

        The first load blocks and raises on failure. Later refreshes are best
        effort: if one fails, or another thread is already refreshing, readers
        keep the previous snapshot.
        """
        snapshot = self._snapshot
        stale = (
            snapshot is None
            or self._refreshed_at is None
            or self._time() - self._refreshed_at >= self._refresh_s
        )
        if not stale and snapshot is not None:
            return snapshot
        if snapshot is None:
            with self._lock:
                if self._snapshot is None:
                    self._refresh_locked()
            assert self._snapshot is not None
            return self._snapshot
        if self._lock.acquire(blocking=False):
            try:
                self._refresh_locked()
            except Exception:
                log.exception("store refresh failed; serving the previous data")
                self._refreshed_at = self._time()  # back off until the next period
            finally:
                self._lock.release()
        return self._snapshot or snapshot

    # --- reads ----------------------------------------------------------------

    def participants(self) -> list[str]:
        return list(self._current().by_person)

    def dataset_of(self, person_id: str) -> str | None:
        return self._current().datasets.get(person_id)

    def data_range(self) -> tuple[datetime, datetime] | None:
        snapshot = self._current()
        if snapshot.first_end is None or snapshot.last_end is None:
            return None
        return snapshot.first_end, snapshot.last_end

    def history(
        self,
        person_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Window]:
        """A participant's windows with start < window_end <= end, oldest first.

        `start` is exclusive so consecutive ranges never return a window twice.
        """
        windows = self._current().by_person.get(person_id, ())
        ends = [w.window_end for w in windows]
        lo = 0 if start is None else bisect.bisect_right(ends, start)
        hi = len(windows) if end is None else bisect.bisect_right(ends, end)
        return list(windows[lo:hi])

    def latest(self, person_id: str, as_of: datetime | None = None) -> Window | None:
        windows = self.history(person_id, end=as_of)
        return windows[-1] if windows else None

    def size(self) -> int:
        return sum(len(ws) for ws in self._current().by_person.values())
