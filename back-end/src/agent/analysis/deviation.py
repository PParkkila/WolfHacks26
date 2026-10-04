"""Cohort-deviation description of a person's features.

This describes how unusual a person is, feature by feature. It is NOT model
attribution: a feature can deviate strongly and contribute nothing to the score.
"""

import math
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from agent.domain.models import FeatureStat, FeatureVector

Direction = Literal["above", "below", "at"]


class FeatureDeviation(BaseModel):
    feature: str
    value: float
    cohort_median: float
    z_score: float
    percentile: float
    direction: Direction
    at_risk_median: float | None
    # True when the person deviates the same way the at-risk group does.
    aligned_with_at_risk: bool | None


@dataclass(frozen=True)
class Tension:
    """Whether the deviating features contradict the model's label."""

    present: bool
    aligned: int
    opposed: int


def z_score(value: float, stat: FeatureStat) -> float | None:
    if stat.stddev <= 0:
        return None
    return (value - stat.mean) / stat.stddev


def percentile_from_z(z: float) -> float:
    """Percentile under a normal approximation (cohort_stats has no full CDF)."""
    return 100.0 * 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _sign(x: float) -> int:
    return (x > 0) - (x < 0)


def describe_feature(
    name: str,
    value: float,
    stat: FeatureStat,
    at_risk_stat: FeatureStat | None = None,
) -> FeatureDeviation | None:
    z = z_score(value, stat)
    if z is None:
        return None

    aligned: bool | None = None
    at_risk_median = at_risk_stat.p50 if at_risk_stat else None
    if at_risk_median is not None:
        group_shift = _sign(at_risk_median - stat.p50)
        if group_shift != 0:
            aligned = _sign(value - stat.p50) == group_shift

    shift = _sign(value - stat.p50)
    direction: Direction = "above" if shift > 0 else "below" if shift < 0 else "at"
    return FeatureDeviation(
        feature=name,
        value=value,
        cohort_median=stat.p50,
        z_score=z,
        percentile=percentile_from_z(z),
        direction=direction,
        at_risk_median=at_risk_median,
        aligned_with_at_risk=aligned,
    )


def top_deviations(
    vector: FeatureVector,
    stats: dict[str, FeatureStat],
    at_risk_stats: dict[str, FeatureStat],
    n: int = 5,
) -> list[FeatureDeviation]:
    """The `n` features furthest from the cohort, by absolute z-score."""
    found = [
        d
        for name, value in vector.values.items()
        if value is not None and name in stats
        if (d := describe_feature(name, value, stats[name], at_risk_stats.get(name)))
    ]
    found.sort(key=lambda d: abs(d.z_score), reverse=True)
    return found[:n]


def assess_tension(label: str | None, deviations: list[FeatureDeviation]) -> Tension:
    """Flag a label that the person's top deviations argue against."""
    aligned = sum(d.aligned_with_at_risk is True for d in deviations)
    opposed = sum(d.aligned_with_at_risk is False for d in deviations)
    if label == "at_risk":
        present = opposed > aligned
    elif label == "not_at_risk":
        present = aligned > opposed
    else:
        present = False
    return Tension(present=present, aligned=aligned, opposed=opposed)
