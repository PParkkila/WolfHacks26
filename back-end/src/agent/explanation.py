"""Explaining a person's score from cohort deviations.

Owns the whole decision: refuse when the assessment is unreliable, otherwise
describe how unusual the person's features are and whether they contradict the
label. This is a cohort-deviation description, NOT model attribution.
"""

from dataclasses import dataclass

from agent.analysis.deviation import (
    FeatureDeviation,
    Tension,
    assess_tension,
    top_deviations,
)
from agent.analysis.quality import AbstainReason
from agent.assessment import Assessment
from agent.domain.ports import CohortStatsRepository, FeatureRepository

METHOD = "cohort_deviation"
CAVEAT = (
    "These are cohort deviations: how unusual each value is for this person. "
    "They are associations, not model attributions or causes."
)


@dataclass(frozen=True)
class Explanation:
    deviations: list[FeatureDeviation]
    tension: Tension


@dataclass(frozen=True)
class Withheld:
    """The assessment is unreliable, so no explanation is offered."""

    reason: AbstainReason


@dataclass(frozen=True)
class NoFeatures:
    """The person has a score but no stored feature vector for that window."""


class Explainer:
    def __init__(
        self,
        features: FeatureRepository,
        stats: CohortStatsRepository,
        top_n: int = 5,
    ) -> None:
        self._features = features
        self._stats = stats
        self._top_n = top_n

    def explain(self, assessment: Assessment) -> Explanation | Withheld | NoFeatures:
        reason = assessment.reliability.abstain_reason
        if reason is not None:
            return Withheld(reason)

        score = assessment.score
        vector = self._features.get_features(score.person_id, score.window_end)
        if vector is None:
            return NoFeatures()

        deviations = top_deviations(
            vector,
            self._stats.feature_stats("all"),
            self._stats.feature_stats("at_risk"),
            self._top_n,
        )
        return Explanation(deviations, assess_tension(score.label, deviations))
