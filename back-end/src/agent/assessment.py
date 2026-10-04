"""Person-window assessment: one place that decides what a score is worth.

Looks a person's scoring window up and attaches the data-quality verdict and the
reliability (abstention) decision, so no caller re-derives them. Tools shape the
result into payloads; they never decide what counts as unreliable.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from agent.analysis.quality import (
    QualityAssessment,
    Reliability,
    ReliabilityPolicy,
    assess_quality,
    assess_reliability,
)
from agent.domain.models import RiskScore
from agent.domain.ports import RiskRepository


@dataclass(frozen=True)
class Assessment:
    score: RiskScore
    quality: QualityAssessment
    reliability: Reliability

    @property
    def person_id(self) -> str:
        return self.score.person_id

    @property
    def reliable(self) -> bool:
        return self.reliability.reliable


def _parse_window(window: str) -> datetime | None:
    """`latest` -> None (the repository picks the newest); else an ISO window end."""
    if window.strip().lower() in ("", "latest"):
        return None
    parsed = datetime.fromisoformat(window)  # ValueError on garbage, by design
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class Assessor:
    def __init__(self, risk: RiskRepository, policy: ReliabilityPolicy) -> None:
        self._risk = risk
        self._policy = policy

    def assess(self, person_id: str, window: str = "latest") -> Assessment | None:
        """The assessed window, or None if the person or window does not exist.

        Raises ValueError if `window` is neither "latest" nor an ISO-8601 time.
        """
        score = self._risk.get_score(person_id, _parse_window(window))
        return None if score is None else self._of(score)

    def assess_all(self) -> list[Assessment]:
        """Every person's newest window, including those not yet scored."""
        return [self._of(score) for score in self._risk.latest_scores()]

    def _of(self, score: RiskScore) -> Assessment:
        return Assessment(
            score=score,
            quality=assess_quality(score, self._policy),
            reliability=assess_reliability(score, self._policy),
        )
