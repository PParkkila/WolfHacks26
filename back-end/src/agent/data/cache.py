"""Cohort-stats cache shared by every backend."""

import time
from collections.abc import Callable

from agent.domain.models import CohortGroup, FeatureStat

Stats = dict[str, FeatureStat]


class StatsCache:
    """Loads cohort stats on first use and reloads them after `ttl_s` seconds.

    `ttl_s=None` keeps them for the life of the process (fine for the mock, whose
    data never changes).
    """

    def __init__(
        self,
        load: Callable[[CohortGroup], Stats],
        ttl_s: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._load = load
        self._ttl_s = ttl_s
        self._clock = clock
        self._entries: dict[CohortGroup, tuple[float, Stats]] = {}

    def get(self, group: CohortGroup) -> Stats:
        entry = self._entries.get(group)
        if entry is None or self._expired(entry[0]):
            entry = (self._clock(), self._load(group))
            self._entries[group] = entry
        return entry[1]

    def _expired(self, loaded_at: float) -> bool:
        return self._ttl_s is not None and self._clock() - loaded_at >= self._ttl_s
