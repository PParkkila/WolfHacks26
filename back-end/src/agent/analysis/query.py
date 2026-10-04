"""Pure aggregation behind `/query` and the agents' query tools.

Windows in, plain points out: `{"t": datetime, "n": windows used, <metric>: value}`.
No I/O, no scope, no clock; `query.py` applies those before calling in here.
"""

import statistics
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any, Literal

from agent.domain.models import Window

Bucket = Literal["raw", "hour", "day", "all"]
Agg = Literal["mean", "median", "min", "max", "first", "last", "delta"]
GroupBy = Literal["participant", "cohort"]
Order = Literal["asc", "desc"]
Point = dict[str, Any]

BUCKETS: tuple[Bucket, ...] = ("raw", "hour", "day", "all")
AGGS: tuple[Agg, ...] = ("mean", "median", "min", "max", "first", "last", "delta")
DECIMALS = 4

_REDUCERS: dict[str, Callable[[list[float]], float]] = {
    "mean": statistics.fmean,
    "median": statistics.median,
    "min": min,
    "max": max,
    "first": lambda v: v[0],
    "last": lambda v: v[-1],
}


def aggregate(values: Sequence[float | None], agg: Agg) -> float | None:
    """Reduce values in time order; nulls are skipped, all-null gives None.

    `delta` is last minus first and needs at least two values.
    """
    present = [v for v in values if v is not None]
    if not present:
        return None
    if agg == "delta":
        return present[-1] - present[0] if len(present) >= 2 else None
    return _REDUCERS[agg](present)


def _bucket_key(t: datetime, bucket: Bucket) -> datetime | None:
    if bucket == "raw":
        return t
    if bucket == "hour":
        return t.replace(minute=0, second=0, microsecond=0)
    if bucket == "day":
        return t.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return None  # "all": one bucket


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, DECIMALS)


def participant_points(
    windows: Sequence[Window], metrics: Sequence[str], bucket: Bucket, agg: Agg
) -> list[Point]:
    """One participant's windows (oldest first) reduced to bucketed points.

    A bucket's `t` is its start (hour/day), the window end for "raw", and the
    newest window end for "all".
    """
    groups: dict[datetime | None, list[Window]] = {}
    for window in windows:
        groups.setdefault(_bucket_key(window.window_end, bucket), []).append(window)
    points: list[Point] = []
    for key, members in groups.items():
        point: Point = {"t": key or members[-1].window_end, "n": len(members)}
        for metric in metrics:
            point[metric] = _rounded(aggregate([w.value(metric) for w in members], agg))
        points.append(point)
    return points


def pool(
    per_participant: Sequence[Sequence[Point]],
    metrics: Sequence[str],
    agg: Agg,
    bucket: Bucket,
) -> list[Point]:
    """Combine participants' points bucket by bucket into one cohort series.

    Each participant is first reduced with `agg`; participants are then combined
    with the same reducer for min/max/median and with the mean otherwise (the
    cohort's mean daily delta, mean last value, ...).
    """
    combine: Agg = agg if agg in ("min", "max", "median") else "mean"
    groups: dict[datetime | None, list[Point]] = {}
    for points in per_participant:
        for point in points:
            key = None if bucket == "all" else point["t"]
            groups.setdefault(key, []).append(point)
    pooled: list[Point] = []
    for key in sorted(groups, key=lambda k: k or datetime.min.replace(tzinfo=UTC)):
        members = groups[key]
        point: Point = {
            "t": key or max(p["t"] for p in members),
            "n": sum(p["n"] for p in members),
            "participants": len(members),
        }
        for metric in metrics:
            point[metric] = _rounded(aggregate([p[metric] for p in members], combine))
        pooled.append(point)
    return pooled


def sort_key(points: Sequence[Point], metric: str) -> float | None:
    """The value a series is ranked by: its newest point's value."""
    return points[-1].get(metric) if points else None


def rank[T](
    items: Sequence[T], key: Callable[[T], float | None], order: Order
) -> list[T]:
    """Sort by key, nulls last whatever the order."""
    present = [i for i in items if key(i) is not None]
    missing = [i for i in items if key(i) is None]
    present.sort(key=lambda i: key(i) or 0.0, reverse=order == "desc")
    return present + missing


def downsample(points: Sequence[Point], max_points: int) -> list[Point]:
    """Evenly spaced points, always keeping the first and the newest."""
    if len(points) <= max_points or max_points < 2:
        return list(points)
    step = (len(points) - 1) / (max_points - 1)
    return [points[round(i * step)] for i in range(max_points)]
