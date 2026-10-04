"""In-memory copy of everyone's newest sensor readings, refreshed every second.

The live view is one small row per participant, so the store re-reads all of it
whenever a reader finds it older than `refresh_s`; polling never triggers any
computation upstream. When the readings show analytics newer than the window
store holds, the window store is told to refresh on its next read, so new
windows appear within about a second instead of waiting out its own period.
"""

import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime

from agent.domain.models import LiveReading
from agent.domain.ports import WindowSource
from agent.store import WindowStore

log = logging.getLogger(__name__)


class LiveStore:
    def __init__(
        self,
        source: WindowSource,
        windows: WindowStore,
        refresh_s: float = 1.0,
        time_source: Callable[[], float] = time.monotonic,
    ) -> None:
        self._source = source
        self._windows = windows
        self._refresh_s = refresh_s
        self._time = time_source
        self._lock = threading.Lock()
        self._readings: dict[str, LiveReading] = {}
        self._refreshed_at: float | None = None

    def refresh(self) -> None:
        readings = {r.person_id: r for r in self._source.fetch_live()}
        self._readings = readings
        self._refreshed_at = self._time()
        newest = max(
            (
                r.analytics_window_end
                for r in readings.values()
                if r.analytics_window_end
            ),
            default=None,
        )
        bounds = self._windows.data_range()
        if newest is not None and (bounds is None or newest > bounds[1]):
            self._windows.invalidate()

    def _current(self) -> dict[str, LiveReading]:
        """The readings, refreshed first if stale; a failed refresh keeps the old ones.

        Only one thread refreshes at a time; the others read what is there.
        """
        stale = (
            self._refreshed_at is None
            or self._time() - self._refreshed_at >= self._refresh_s
        )
        if stale and self._lock.acquire(blocking=False):
            try:
                self.refresh()
            except Exception:
                log.exception("live refresh failed; serving the previous readings")
                self._refreshed_at = self._time()  # back off until the next period
            finally:
                self._lock.release()
        return self._readings

    def reading(self, person_id: str) -> LiveReading | None:
        return self._current().get(person_id)

    def readings(self) -> list[LiveReading]:
        return list(self._current().values())

    def latest_sensor_time(self) -> datetime | None:
        return max((r.sensor_time for r in self._current().values()), default=None)
