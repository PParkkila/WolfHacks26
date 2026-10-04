"""Adapter logic against a recording stub. Not a live-database test."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from agent.data.cache import StatsCache
from agent.data.postgres import PostgresBackend
from agent.domain.models import WindowKey
from agent.domain.ports import FEATURE_WINDOW_TOLERANCE

END = datetime(2026, 10, 2, tzinfo=UTC)
KEY = WindowKey(person_id="P1", window_end=END)


class Clock:
    now = 0.0

    def __call__(self) -> float:
        return Clock.now


class Recorder(PostgresBackend):
    def __init__(self, rows):
        super().__init__("postgresql://unused")
        self.rows = rows
        self.queries: list[tuple[str, tuple]] = []

    def _query(self, query, params=()):
        self.queries.append((query.as_string(), params))
        return self.rows


RISK_ROW = {
    "person_id": "P1",
    "window_start": END,
    "window_end": END,
    "score": Decimal("0.8"),
    "label": "at_risk",
    "confidence": 0.9,
    "wear_time_hours": 20,
    "missing_signal_pct": 4,
    "model_version": "v1",
}


def test_get_score_composes_read_only_select_with_bound_params():
    backend = Recorder([RISK_ROW])
    score = backend.get_score("P1", END)
    query, params = backend.queries[0]
    assert query.startswith('SELECT "person_id" AS "person_id"')
    assert 'FROM "risk_scores" WHERE "person_id" = %s AND "window_end" = %s' in query
    assert query.endswith('ORDER BY "window_end" DESC LIMIT 1')
    assert params == ("P1", END)
    assert score is not None
    assert score.score == 0.8


def test_get_score_missing_person_is_none():
    assert Recorder([]).get_score("P999") is None


def test_features_drop_metadata_and_non_numeric_columns():
    row = {
        "person_id": "P1",
        "window_start": END,
        "window_end": END,
        "resting_hr_bpm": Decimal("71.5"),
        "steps": 9000,
        "hrv": None,
        "feature_contributions": {"a": 1},
    }
    vector = Recorder([row]).get_features(KEY)
    assert vector is not None
    assert vector.values == {"resting_hr_bpm": 71.5, "steps": 9000.0, "hrv": None}


def test_features_reject_booleans_and_keep_numbers():
    row = {
        "person_id": "P1",
        "window_start": END,
        "window_end": END,
        "is_weekend": True,
        "steps": 9000,
    }
    vector = Recorder([row]).get_features(KEY)
    assert vector is not None
    assert vector.values == {"steps": 9000.0}


def test_features_match_the_window_within_a_tolerance_closest_first():
    backend = Recorder([])
    backend.get_features(KEY)
    query, params = backend.queries[0]
    assert 'FROM "person_features" WHERE "person_id" = %s' in query
    assert 'AND "window_end" BETWEEN %s AND %s' in query
    assert "ORDER BY abs(extract(epoch FROM" in query
    assert params == (
        "P1",
        END - FEATURE_WINDOW_TOLERANCE,
        END + FEATURE_WINDOW_TOLERANCE,
        END,
    )


def test_history_is_newest_first_and_limited():
    backend = Recorder([RISK_ROW])
    assert len(backend.get_history("P1", 3)) == 1
    query, params = backend.queries[0]
    assert query.endswith('ORDER BY "window_end" DESC LIMIT %s')
    assert params == ("P1", 3)


def test_writable_tables_are_reported_and_only_selects_are_issued():
    backend = Recorder([{"name": "risk_scores"}])
    assert backend.writable_tables() == ["risk_scores"]
    backend.check_read_only()  # warns, never raises
    assert all(q.lstrip().upper().startswith("SELECT") for q, _ in backend.queries)


def test_stats_are_reloaded_after_the_ttl():
    rows = [{"feature_name": "a", "mean": 1, "stddev": 2, "p50": 1}]
    backend = Recorder(rows)
    backend._stats = StatsCache(backend._load_stats, 60.0, clock=Clock())
    backend.feature_stats("all")
    backend.feature_stats("all")
    assert len(backend.queries) == 1
    Clock.now += timedelta(seconds=61).total_seconds()
    backend.feature_stats("all")
    assert len(backend.queries) == 2


def test_stats_come_from_cohort_stats_view_and_are_cached():
    rows = [{"feature_name": "a", "mean": 1, "stddev": 2, "p50": 1}]
    backend = Recorder(rows)
    assert backend.feature_stats("all")["a"].stddev == 2
    backend.feature_stats("all")
    assert len(backend.queries) == 1
    assert 'FROM "cohort_stats"' in backend.queries[0][0]


def test_only_selects_are_ever_issued():
    backend = Recorder([RISK_ROW])
    backend.get_score("P1")
    backend.latest_scores()
    backend.model_version()
    assert all(q.lstrip().upper().startswith("SELECT") for q, _ in backend.queries)
