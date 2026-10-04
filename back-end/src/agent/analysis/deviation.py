"""How unusual a value is against a distribution.

This describes, metric by metric, how far someone sits from a group (the cohort,
or their own history). It is NOT model attribution: a metric can deviate
strongly and contribute nothing to the Gluco Score.
"""

import math
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel

from agent.domain.models import FeatureStat

Direction = Literal["above", "below", "at"]


class FeatureDeviation(BaseModel):
    feature: str
    value: float
    median: float
    z_score: float
    percentile: float
    direction: Direction


def z_score(value: float, stat: FeatureStat) -> float | None:
    if stat.stddev <= 0:
        return None
    return (value - stat.mean) / stat.stddev


def percentile_from_z(z: float) -> float:
    """Percentile under a normal approximation (the stats carry no full CDF)."""
    return 100.0 * 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def describe_feature(
    name: str, value: float, stat: FeatureStat
) -> FeatureDeviation | None:
    z = z_score(value, stat)
    if z is None:
        return None
    shift = (value > stat.p50) - (value < stat.p50)
    direction: Direction = "above" if shift > 0 else "below" if shift < 0 else "at"
    return FeatureDeviation(
        feature=name,
        value=value,
        median=stat.p50,
        z_score=z,
        percentile=percentile_from_z(z),
        direction=direction,
    )


def top_deviations(
    values: Mapping[str, float | None],
    stats: Mapping[str, FeatureStat],
    n: int = 5,
) -> list[FeatureDeviation]:
    """The `n` metrics furthest from the group, by absolute z-score."""
    found = [
        d
        for name, value in values.items()
        if value is not None and name in stats
        if (d := describe_feature(name, value, stats[name]))
    ]
    found.sort(key=lambda d: abs(d.z_score), reverse=True)
    return found[:n]
