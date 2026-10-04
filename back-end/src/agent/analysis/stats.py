"""Derive cohort distributions from raw feature vectors."""

from collections.abc import Iterable

import numpy as np

from agent.domain.models import FeatureStat, FeatureVector

MIN_SAMPLES = 2


def compute_feature_stats(
    vectors: Iterable[FeatureVector],
) -> dict[str, FeatureStat]:
    """Per-feature mean, sample stddev and median; nulls are ignored.

    Used by the mock backend, and by the Postgres adapter when the data team does
    not provide `cohort_stats` or for the at-risk subgroup.
    """
    columns: dict[str, list[float]] = {}
    for vector in vectors:
        for name, value in vector.values.items():
            if value is not None:
                columns.setdefault(name, []).append(value)

    stats: dict[str, FeatureStat] = {}
    for name, column in columns.items():
        if len(column) < MIN_SAMPLES:
            continue
        data = np.asarray(column, dtype=float)
        stats[name] = FeatureStat(
            feature_name=name,
            mean=float(data.mean()),
            stddev=float(data.std(ddof=1)),
            p50=float(np.median(data)),
        )
    return stats
