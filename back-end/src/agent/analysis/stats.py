"""Derive distributions from metric values."""

from collections.abc import Iterable, Mapping

import numpy as np

from agent.domain.models import FeatureStat

MIN_SAMPLES = 2


def compute_feature_stats(
    rows: Iterable[Mapping[str, float | None]],
) -> dict[str, FeatureStat]:
    """Per-metric mean, sample stddev and median; nulls are ignored.

    A metric with fewer than MIN_SAMPLES values gets no entry.
    """
    columns: dict[str, list[float]] = {}
    for row in rows:
        for name, value in row.items():
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
