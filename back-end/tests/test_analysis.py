from datetime import UTC, datetime

import pytest

from agent.analysis.deviation import (
    assess_tension,
    describe_feature,
    percentile_from_z,
    top_deviations,
    z_score,
)
from agent.analysis.quality import ReliabilityPolicy, assess_quality, assess_reliability
from agent.analysis.stats import compute_feature_stats
from agent.domain.models import FeatureStat, FeatureVector, RiskScore

NOW = datetime(2026, 10, 2, tzinfo=UTC)
POLICY = ReliabilityPolicy()


def score(**overrides) -> RiskScore:
    base = {
        "person_id": "P001",
        "window_start": NOW,
        "window_end": NOW,
        "score": 0.8,
        "label": "at_risk",
        "confidence": 0.9,
        "wear_time_hours": 22.0,
        "missing_signal_pct": 5.0,
        "model_version": "t",
    }
    return RiskScore(**{**base, **overrides})


def stat(mean=10.0, sd=2.0, median=10.0) -> FeatureStat:
    return FeatureStat(
        feature_name="f",
        mean=mean,
        stddev=sd,
        p25=median - 1,
        p50=median,
        p75=median + 1,
    )


@pytest.mark.parametrize(
    ("wear", "missing", "verdict"),
    [
        (22, 5, "good"),
        (13, 5, "marginal"),
        (22, 30, "marginal"),
        (9, 5, "insufficient"),
        (22, 60, "insufficient"),
        (None, 5, "insufficient"),
    ],
)
def test_quality_verdicts(wear, missing, verdict):
    assessed = assess_quality(
        score(wear_time_hours=wear, missing_signal_pct=missing), POLICY
    )
    assert assessed.verdict == verdict


@pytest.mark.parametrize(
    ("overrides", "reliable", "reason"),
    [
        ({}, True, None),
        ({"score": None, "label": None, "confidence": None}, False, "not_scored"),
        ({"wear_time_hours": 6.0}, False, "insufficient_data_quality"),
        ({"confidence": 0.52}, False, "low_confidence"),
        ({"confidence": None}, False, "low_confidence"),
        ({"confidence": 0.6}, True, None),
    ],
)
def test_reliability(overrides, reliable, reason):
    result = assess_reliability(score(**overrides), POLICY)
    assert (result.reliable, result.abstain_reason) == (reliable, reason)


def test_z_score_and_percentile():
    assert z_score(14.0, stat()) == pytest.approx(2.0)
    assert z_score(14.0, stat(sd=0.0)) is None
    assert percentile_from_z(0.0) == pytest.approx(50.0)
    assert percentile_from_z(1.645) == pytest.approx(95.0, abs=0.1)


def test_describe_feature_alignment():
    at_risk = stat(median=12.0)
    above = describe_feature("f", 15.0, stat(), at_risk)
    below = describe_feature("f", 5.0, stat(), at_risk)
    assert above
    assert above.direction == "above"
    assert above.aligned_with_at_risk is True
    assert below
    assert below.direction == "below"
    assert below.aligned_with_at_risk is False
    flat = describe_feature("f", 15.0, stat(), stat())
    assert flat
    assert flat.aligned_with_at_risk is None


def test_top_deviations_orders_by_abs_z_and_skips_nulls():
    stats = {"a": stat(), "b": stat(), "c": stat()}
    vector = FeatureVector(
        person_id="P1", window_end=NOW, values={"a": 11.0, "b": 4.0, "c": None}
    )
    top = top_deviations(vector, stats, {}, n=5)
    assert [d.feature for d in top] == ["b", "a"]


def test_tension_flags_label_contradicted_by_features():
    at_risk = {"f": stat(median=12.0)}
    stats = {"f": stat()}
    protective = FeatureVector(person_id="P1", window_end=NOW, values={"f": 5.0})
    deviations = top_deviations(protective, stats, at_risk)
    assert assess_tension("at_risk", deviations).present is True
    assert assess_tension("not_at_risk", deviations).present is False
    assert assess_tension(None, deviations).present is False


def test_compute_feature_stats_ignores_nulls_and_thin_columns():
    vectors = [
        FeatureVector(
            person_id=f"P{i}", window_end=NOW, values={"a": float(i), "b": None}
        )
        for i in range(1, 6)
    ]
    stats = compute_feature_stats(vectors)
    assert set(stats) == {"a"}
    assert stats["a"].p50 == 3.0
    assert stats["a"].stddev == pytest.approx(1.5811, abs=1e-3)
