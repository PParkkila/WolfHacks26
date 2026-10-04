from datetime import UTC, datetime, timedelta

import pytest

from agent.analysis import query as q
from agent.analysis.deviation import (
    describe_feature,
    percentile_from_z,
    top_deviations,
    z_score,
)
from agent.analysis.ids import display_name, resolve_participant
from agent.analysis.stats import compute_feature_stats
from agent.domain.errors import AmbiguousPersonError, PersonNotFoundError
from agent.domain.models import FeatureStat, Window

STAT = FeatureStat(feature_name="hr", mean=70.0, stddev=10.0, p50=68.0)
KNOWN = [
    "demo:big_ideas:002",
    "demo:big_ideas:013",
    "demo:imu50:00",
    "demo:imu50:13",
]


def test_z_score_and_percentile():
    assert z_score(80.0, STAT) == 1.0
    assert z_score(80.0, STAT.model_copy(update={"stddev": 0.0})) is None
    assert percentile_from_z(0.0) == pytest.approx(50.0)
    assert percentile_from_z(1.645) == pytest.approx(95.0, abs=0.1)


def test_describe_feature_direction_is_against_the_median():
    above = describe_feature("hr", 69.0, STAT)
    assert above is not None
    assert (above.direction, above.median) == ("above", 68.0)
    at = describe_feature("hr", 68.0, STAT)
    assert at is not None
    assert at.direction == "at"


def test_top_deviations_orders_by_abs_z_and_skips_nulls_and_unknowns():
    stats = {"a": STAT, "b": STAT.model_copy(update={"feature_name": "b"})}
    found = top_deviations({"a": 75.0, "b": 40.0, "c": 1.0, "d": None}, stats, n=2)
    assert [d.feature for d in found] == ["b", "a"]


def test_compute_feature_stats_ignores_nulls_and_thin_columns():
    rows = [{"x": 1.0, "y": None, "z": 5.0}, {"x": 3.0, "y": 2.0}]
    stats = compute_feature_stats(rows)
    assert set(stats) == {"x"}
    assert stats["x"].mean == 2.0
    assert stats["x"].p50 == 2.0


def test_display_names():
    assert display_name("demo:big_ideas:013") == "Patient 013"
    assert display_name("demo:imu50:00") == "Patient IMU-00"


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("demo:big_ideas:013", "demo:big_ideas:013"),
        ("13", "demo:big_ideas:013"),
        ("013", "demo:big_ideas:013"),
        ("P013", "demo:big_ideas:013"),
        ("participant 13", "demo:big_ideas:013"),
        ("big_ideas:013", "demo:big_ideas:013"),
        ("Patient 013", "demo:big_ideas:013"),
        ("IMU-13", "demo:imu50:13"),
        ("Patient IMU-13", "demo:imu50:13"),
        ("IMU-00", "demo:imu50:00"),
        ("0", "demo:imu50:00"),
    ],
)
def test_resolve_participant(ref, expected):
    assert resolve_participant(ref, KNOWN) == expected


def test_resolve_unknown_and_ambiguous():
    with pytest.raises(PersonNotFoundError):
        resolve_participant("99", KNOWN)
    with pytest.raises(PersonNotFoundError):
        resolve_participant("nobody", KNOWN)
    with pytest.raises(AmbiguousPersonError) as exc:
        resolve_participant("2", ["demo:big_ideas:002", "demo:other:2"])
    assert len(exc.value.candidates) == 2
    with pytest.raises(AmbiguousPersonError):
        resolve_participant("imu50", KNOWN)  # more than one IMU participant


# --- pure query --------------------------------------------------------------

T0 = datetime(2026, 9, 30, 22, tzinfo=UTC)


def window(hour: int, value: float | None, person: str = "p") -> Window:
    end = T0 + timedelta(hours=hour)
    return Window(
        person_id=person,
        source_dataset="big_ideas",
        window_start=end - timedelta(hours=24),
        window_end=end,
        values={"v": value},
    )


@pytest.mark.parametrize(
    ("agg", "expected"),
    [
        ("mean", 2.0),
        ("median", 2.0),
        ("min", 1.0),
        ("max", 3.0),
        ("first", 1.0),
        ("last", 3.0),
        ("delta", 2.0),
    ],
)
def test_aggregate(agg, expected):
    assert q.aggregate([1.0, None, 2.0, 3.0], agg) == expected


def test_aggregate_edge_cases():
    assert q.aggregate([None, None], "mean") is None
    assert q.aggregate([5.0], "delta") is None


def test_day_buckets_split_at_utc_midnight():
    windows = [window(h, float(h)) for h in range(4)]  # 22:00, 23:00 | 00:00, 01:00
    points = q.participant_points(windows, ["v"], "day", "mean")
    assert [(p["t"].day, p["n"], p["v"]) for p in points] == [(30, 2, 0.5), (1, 2, 2.5)]


def test_all_bucket_is_one_point_stamped_with_the_newest_window():
    windows = [window(h, float(h)) for h in range(4)]
    [point] = q.participant_points(windows, ["v"], "all", "delta")
    assert (point["t"], point["n"], point["v"]) == (windows[-1].window_end, 4, 3.0)


def test_raw_bucket_keeps_every_window():
    windows = [window(h, float(h)) for h in range(3)]
    assert len(q.participant_points(windows, ["v"], "raw", "mean")) == 3


def test_pool_combines_participants_per_bucket():
    a = q.participant_points([window(0, 1.0), window(1, 3.0)], ["v"], "hour", "max")
    b = q.participant_points([window(0, 5.0)], ["v"], "hour", "max")
    pooled = q.pool([a, b], ["v"], "max", "hour")
    assert [(p["participants"], p["v"]) for p in pooled] == [(2, 5.0), (1, 3.0)]
    mean_pooled = q.pool([a, b], ["v"], "first", "hour")
    assert mean_pooled[0]["v"] == 3.0  # mean of the participants' first values


def test_rank_puts_nulls_last_in_both_orders():
    items = [("a", 2.0), ("b", None), ("c", 5.0)]
    asc = q.rank(items, lambda i: i[1], "asc")
    desc = q.rank(items, lambda i: i[1], "desc")
    assert [i[0] for i in asc] == ["a", "c", "b"]
    assert [i[0] for i in desc] == ["c", "a", "b"]


def test_downsample_keeps_first_and_last():
    points = [{"t": i} for i in range(100)]
    thin = q.downsample(points, 10)
    assert len(thin) == 10
    assert (thin[0]["t"], thin[-1]["t"]) == (0, 99)
    assert q.downsample(points[:5], 10) == points[:5]
