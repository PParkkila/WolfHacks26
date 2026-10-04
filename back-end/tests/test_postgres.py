"""Adapter logic against a recording stub. Not a live-database test."""

from datetime import UTC, datetime
from decimal import Decimal

from agent.data.postgres import PostgresSource, to_window
from agent.domain.metrics import GLUCO_CHANGE, GLUCO_SCORE

END = datetime(2026, 10, 4, 7, tzinfo=UTC)
PUBLISHED = datetime(2026, 10, 4, 8, tzinfo=UTC)
PAYLOAD = {
    "source_dataset": "big_ideas",
    "window_minutes": 1440,
    "wearable_risk_indicator": 91.5,
    "risk_change_24h_points": Decimal("87.7"),
    "hr_mean_bpm_24h": 142.9,
    "motion_mean_g": 0.016,
    "temperature_mean_c_24h": "24.2",
    "motion_hr_correlation": None,
    "synthetic_fraction": 0.4,  # provenance: never read
    "demo_only": True,
}


class Recorder(PostgresSource):
    def __init__(self, rows, session_id: str | None = "s1"):
        super().__init__("postgresql://unused", session_id)
        self.rows = rows
        self.queries: list[tuple[str, tuple]] = []

    def _query(self, query, params=()):
        self.queries.append((query.as_string(), params))
        return self.rows


def test_to_window_inverts_risk_into_gluco_and_keeps_nulls():
    window = to_window("demo:big_ideas:013", END, PAYLOAD)
    assert window.values[GLUCO_SCORE] == 100 - 91.5
    assert window.values[GLUCO_CHANGE] == -87.7
    assert window.values["temperature_mean_c_24h"] == 24.2
    assert window.values["motion_hr_correlation"] is None
    assert window.values["motion_std_g"] is None  # absent, not zero
    assert "synthetic_fraction" not in window.values
    assert (END - window.window_start).total_seconds() == 24 * 3600
    assert window.source_dataset == "big_ideas"


def test_to_window_with_no_prediction():
    window = to_window("p", END, {"wearable_risk_indicator": True})
    assert window.values[GLUCO_SCORE] is None
    assert window.source_dataset == "unknown"


def test_fetch_since_is_a_schema_qualified_session_scoped_select():
    row = {
        "person_id": "demo:big_ideas:013",
        "window_end": END,
        "payload": PAYLOAD,
        "published_at": PUBLISHED,
    }
    source = Recorder([row])
    [published] = source.fetch_since(None)
    query, params = source.queries[0]
    assert query.startswith('SELECT "participant_key" AS person_id')
    assert '"gold"."dashboard_windows"' in query
    assert '"session_id" = %s' in query
    assert 'published_at" >=' not in query
    assert params == ("s1",)
    assert published.published_at == PUBLISHED

    source.fetch_since(PUBLISHED)
    query, params = source.queries[-1]
    assert '"published_at" >= %s' in query
    assert params == ("s1", PUBLISHED)


def test_session_defaults_to_the_most_recently_published():
    source = Recorder([{"session": "latest-run"}], session_id=None)
    assert source.session_id() == "latest-run"
    query, _ = source.queries[0]
    assert 'ORDER BY "published_at" DESC LIMIT 1' in query
    source.session_id()
    assert len(source.queries) == 1  # cached


def test_no_session_means_no_rows():
    assert Recorder([], session_id=None).fetch_since(None) == []


def test_write_check_names_the_table():
    source = Recorder([{"writable": False}])
    assert source.can_write() is False
    assert source.queries[0][1] == ("gold.dashboard_windows",) * 3
