"""Data-quality and abstention policy, kept as plain code rather than prompt text."""

from dataclasses import dataclass
from typing import Literal

from agent.domain.models import RiskScore

Verdict = Literal["good", "marginal", "insufficient"]
AbstainReason = Literal["not_scored", "insufficient_data_quality", "low_confidence"]


@dataclass(frozen=True)
class ReliabilityPolicy:
    min_confidence: float = 0.6
    insufficient_wear_hours: float = 10.0
    marginal_wear_hours: float = 16.0
    insufficient_missing_pct: float = 50.0
    marginal_missing_pct: float = 25.0


@dataclass(frozen=True)
class QualityAssessment:
    verdict: Verdict
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Reliability:
    reliable: bool
    abstain_reason: AbstainReason | None


def assess_quality(score: RiskScore, policy: ReliabilityPolicy) -> QualityAssessment:
    wear = score.wear_time_hours
    missing = score.missing_signal_pct
    if wear is None or missing is None:
        return QualityAssessment(
            "insufficient", ("wear time or missing share unknown",)
        )

    insufficient: list[str] = []
    marginal: list[str] = []
    if wear < policy.insufficient_wear_hours:
        insufficient.append(
            f"wear time {wear:.1f}h is below {policy.insufficient_wear_hours:g}h"
        )
    elif wear < policy.marginal_wear_hours:
        marginal.append(
            f"wear time {wear:.1f}h is below {policy.marginal_wear_hours:g}h"
        )
    if missing > policy.insufficient_missing_pct:
        insufficient.append(f"{missing:.0f}% of the window has no sensor data")
    elif missing > policy.marginal_missing_pct:
        marginal.append(f"{missing:.0f}% of the window has no sensor data")

    if insufficient:
        return QualityAssessment("insufficient", tuple(insufficient + marginal))
    if marginal:
        return QualityAssessment("marginal", tuple(marginal))
    return QualityAssessment("good", ())


def assess_reliability(score: RiskScore, policy: ReliabilityPolicy) -> Reliability:
    """Whether the model output for this window supports a judgement."""
    if score.score is None:
        return Reliability(False, "not_scored")
    if assess_quality(score, policy).verdict == "insufficient":
        return Reliability(False, "insufficient_data_quality")
    if score.confidence is None or score.confidence < policy.min_confidence:
        return Reliability(False, "low_confidence")
    return Reliability(True, None)
