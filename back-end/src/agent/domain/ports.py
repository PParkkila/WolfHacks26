"""Narrow read-only data ports.

Tools and the API depend on these protocols, never on a concrete backend.
Each tool asks only for the port it needs (interface segregation).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from agent.domain.models import (
    CohortGroup,
    FeatureStat,
    FeatureVector,
    RiskScore,
    WindowKey,
)

# A feature row belongs to a score's window if its `window_end` is this close.
# The pipeline stamps the two tables separately, so exact equality is too brittle.
FEATURE_WINDOW_TOLERANCE = timedelta(minutes=1)


class RiskRepository(Protocol):
    def get_score(
        self, person_id: str, window_end: datetime | None = None
    ) -> RiskScore | None:
        """The score for one window (latest if `window_end` is None), or None if
        the person or window does not exist."""
        ...

    def latest_scores(self) -> list[RiskScore]:
        """Each person's newest window, including rows that are not yet scored."""
        ...

    def get_history(self, person_id: str, limit: int = 10) -> list[RiskScore]:
        """A person's most recent windows, newest first (empty if unknown)."""
        ...


class FeatureRepository(Protocol):
    def get_features(self, key: WindowKey) -> FeatureVector | None:
        """The feature vector for the window a score names (`score.key`).

        A vector whose `window_end` is within FEATURE_WINDOW_TOLERANCE of the
        key's matches; the closest wins.
        """
        ...


class CohortStatsRepository(Protocol):
    def feature_stats(self, group: CohortGroup = "all") -> dict[str, FeatureStat]:
        """Per-feature distribution, keyed by feature name."""
        ...


class HealthProbe(Protocol):
    def ping(self) -> bool: ...

    def model_version(self) -> str | None: ...


@dataclass(frozen=True)
class Repositories:
    """The bundle handed to tool builders. One backend usually fills all four."""

    risk: RiskRepository
    features: FeatureRepository
    stats: CohortStatsRepository
    health: HealthProbe
