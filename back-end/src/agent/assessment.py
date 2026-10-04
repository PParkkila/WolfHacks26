"""Person-window assessment: one place that decides what a score is worth.

Looks a person's scoring window up and attaches the data-quality verdict and the
reliability (abstention) decision, so no caller re-derives them. Tools shape the
result into payloads; they never decide what counts as unreliable.
"""

from dataclasses import dataclass
from datetime import datetime

from agent.analysis.quality import (
    AbstainReason,
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

    @property
    def abstain_reason(self) -> AbstainReason | None:
        return self.reliability.abstain_reason

    @property
    def risk(self) -> float | None:
        """The model's risk score, or None if the window was not scored."""
        return self.score.score

    @property
    def confidence(self) -> float | None:
        return self.score.confidence


class Assessor:
    def __init__(self, risk: RiskRepository, policy: ReliabilityPolicy) -> None:
        self._risk = risk
        self._policy = policy

    def assess(
        self, person_id: str, window_end: datetime | None = None
    ) -> Assessment | None:
        """The assessed window (latest if `window_end` is None), or None if the
        person or window does not exist."""
        score = self._risk.get_score(person_id, window_end)
        return None if score is None else self._assess_score(score)

    def assess_all(self) -> list[Assessment]:
        """Every person's newest window, including those not yet scored."""
        return [self._assess_score(score) for score in self._risk.latest_scores()]

    def _assess_score(self, score: RiskScore) -> Assessment:
        return Assessment(
            score=score,
            quality=assess_quality(score, self._policy),
            reliability=assess_reliability(score, self._policy),
        )
