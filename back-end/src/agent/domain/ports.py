"""Narrow read-only data ports.

Tools and the API depend on these protocols, never on a concrete backend.
Each tool asks only for the port it needs (interface segregation).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from agent.domain.models import CohortGroup, FeatureStat, FeatureVector, RiskScore


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


class FeatureRepository(Protocol):
    def get_features(
        self, person_id: str, window_end: datetime | None = None
    ) -> FeatureVector | None: ...


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
