"""The replay clock: a simulated "now" that walks through the published data.

Everything the API and the agents show is limited to windows ending at or
before `now()`, so a finished replay looks like a live feed. One clock is shared
by every user, so a clinician and a patient side by side stay in sync.
"""

import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta

from pydantic import BaseModel

HOUR = timedelta(hours=1)


class ClockState(BaseModel):
    now: datetime | None
    playing: bool
    seconds_per_hour: float
    enabled: bool
    data_start: datetime | None
    data_end: datetime | None
    at_end: bool


class ReplayClock:
    """`now = anchor + real seconds elapsed / seconds_per_hour` simulated hours.

    The replay starts on first use, so a server left idle before a demo has not
    run ahead. It is clamped to the data: it pauses itself on reaching the newest
    window, and newer rows arriving later extend how far it can go. Disabled,
    `now()` is simply the newest window.
    """

    def __init__(
        self,
        data_range: Callable[[], tuple[datetime, datetime] | None],
        start: datetime | None = None,
        seconds_per_hour: float = 5.0,
        enabled: bool = True,
        time_source: Callable[[], float] = time.monotonic,
    ) -> None:
        if seconds_per_hour <= 0:
            raise ValueError("seconds_per_hour must be positive")
        self._range = data_range
        self._enabled = enabled
        self._speed = seconds_per_hour
        self._time = time_source
        self._lock = threading.Lock()
        self._start = start
        self._anchor_sim: datetime | None = None
        self._anchor_real = time_source()
        self._playing = True

    # --- reading ----------------------------------------------------------

    def now(self) -> datetime | None:
        with self._lock:
            return self._now_locked()

    def state(self) -> ClockState:
        with self._lock:
            now = self._now_locked()
            bounds = self._range()
            end = bounds[1] if bounds else None
            return ClockState(
                now=now,
                playing=self._playing and self._enabled,
                seconds_per_hour=self._speed,
                enabled=self._enabled,
                data_start=bounds[0] if bounds else None,
                data_end=end,
                at_end=now is not None and end is not None and now >= end,
            )

    # --- control ----------------------------------------------------------

    def play(self) -> None:
        with self._lock:
            self._rebase()
            self._playing = True

    def pause(self) -> None:
        with self._lock:
            self._rebase()
            self._playing = False

    def set_speed(self, seconds_per_hour: float) -> None:
        if seconds_per_hour <= 0:
            raise ValueError("seconds_per_hour must be positive")
        with self._lock:
            self._rebase()
            self._speed = seconds_per_hour

    def seek(self, to: datetime) -> None:
        with self._lock:
            bounds = self._range()
            if bounds:
                to = min(max(to, bounds[0]), bounds[1])
            self._anchor_sim, self._anchor_real = to, self._time()

    # --- internals (lock held) ---------------------------------------------

    def _now_locked(self) -> datetime | None:
        bounds = self._range()
        if bounds is None:
            return None
        start, end = bounds
        if not self._enabled:
            return end
        if self._anchor_sim is None:  # first use: anchor at the configured start
            initial = self._start or start + timedelta(hours=24)
            self._anchor_sim = min(max(initial, start), end)
            self._anchor_real = self._time()
        sim = self._anchor_sim
        if self._playing:
            elapsed = self._time() - self._anchor_real
            sim = sim + HOUR * (elapsed / self._speed)
        if sim >= end:
            # Stop at the newest data; newer rows let play() continue.
            self._anchor_sim, self._anchor_real = end, self._time()
            self._playing = False
            return end
        return sim

    def _rebase(self) -> None:
        """Fold elapsed time into the anchor before changing how time moves."""
        now = self._now_locked()
        if now is not None:
            self._anchor_sim, self._anchor_real = now, self._time()
