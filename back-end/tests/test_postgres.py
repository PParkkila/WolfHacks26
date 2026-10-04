"""Adapter logic against a recording stub. Not a live-database test."""

from datetime import UTC, datetime
from decimal import Decimal

from agent.data.postgres import PostgresBackend

END = datetime(2026, 10, 2, tzinfo=UTC)


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
    vector = Recorder([row]).get_features("P1")
    assert vector is not None
    assert vector.values == {"resting_hr_bpm": 71.5, "steps": 9000.0, "hrv": None}


def test_stats_come_from_cohort_stats_view_and_are_cached():
    rows = [{"feature_name": "a", "mean": 1, "stddev": 2, "p25": 0, "p50": 1, "p75": 2}]
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
