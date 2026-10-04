"""Against the real Tiger database: `just test-live` (needs the database in .env).

Skipped in the normal run so `just test` stays offline.
"""

import os

import pytest

from agent.config import Settings
from agent.data.postgres import PostgresSource
from agent.domain.metrics import GLUCO_SCORE, LIVE_METRICS
from agent.store import WindowStore

settings = Settings(agent_model="unused")  # pyright: ignore[reportCallIssue]
pytestmark = pytest.mark.skipif(
    not os.environ.get("LIVE_DB") or settings.database_conninfo is None,
    reason="live database tests run with LIVE_DB=1 and a configured database",
)


@pytest.fixture(scope="module")
def source() -> PostgresSource:
    conninfo = settings.database_conninfo
    assert conninfo is not None
    return PostgresSource(conninfo, settings.dashboard_session_id)


def test_reads_published_windows(source):
    assert source.ping()
    assert source.can_write() is False
    store = WindowStore(source)
    assert len(store.participants()) >= 1
    for pid in store.participants():
        windows = store.history(pid)
        assert windows == sorted(windows, key=lambda w: w.window_end)
        scores = [w.value(GLUCO_SCORE) for w in windows]
        assert all(s is None or 0 <= s <= 100 for s in scores)


def test_live_readings_cover_the_panel(source):
    store = WindowStore(source)
    participants = set(store.participants())
    assert len(participants) >= 60
    readings = source.fetch_live()
    assert {r.person_id for r in readings} == participants
    for reading in readings:
        assert set(reading.values) == set(LIVE_METRICS)
        if ":imu50:" in reading.person_id:
            assert reading.values["latest_hr_bpm"] is None


def test_imu_device_has_no_heart_rate(source):
    store = WindowStore(source)
    imu = [pid for pid in store.participants() if ":imu50:" in pid]
    for pid in imu:
        assert all(w.value("hr_mean_bpm_24h") is None for w in store.history(pid))
