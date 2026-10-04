from datetime import UTC, datetime, timedelta

from support import FakeTime

from agent.domain.models import Window
from agent.domain.ports import PublishedWindow
from agent.store import WindowStore

T0 = datetime(2026, 10, 1, tzinfo=UTC)


def w(person: str, hour: int, score: float) -> Window:
    end = T0 + timedelta(hours=hour)
    return Window(
        person_id=person,
        source_dataset="big_ideas",
        window_start=end - timedelta(hours=24),
        window_end=end,
        values={"gluco_score": score},
    )


class ScriptedSource:
    def __init__(self) -> None:
        self.rows: list[PublishedWindow] = []
        self.calls: list[datetime | None] = []
        self.fail = False

    def publish(self, window: Window, minute: int) -> None:
        self.rows.append(PublishedWindow(window, T0 + timedelta(minutes=minute)))

    def fetch_since(self, published_after):
        self.calls.append(published_after)
        if self.fail:
            raise RuntimeError("db down")
        return [
            r
            for r in self.rows
            if published_after is None or r.published_at >= published_after
        ]

    def ping(self) -> bool:
        return True


def test_reads_are_ordered_and_ranges_are_start_exclusive():
    source = ScriptedSource()
    for hour in (2, 0, 1):
        source.publish(w("a", hour, hour), 0)
    store = WindowStore(source)
    assert [x.window_end.hour for x in store.history("a")] == [0, 1, 2]
    after_first = store.history("a", start=T0, end=T0 + timedelta(hours=2))
    assert [x.window_end.hour for x in after_first] == [1, 2]
    assert (
        store.latest("a", as_of=T0 + timedelta(hours=1, minutes=30)).window_end.hour
        == 1
    )
    assert store.data_range() == (T0, T0 + timedelta(hours=2))


def test_refresh_is_incremental_and_republished_rows_overwrite():
    source = ScriptedSource()
    source.publish(w("a", 0, 10.0), 0)
    time = FakeTime()
    store = WindowStore(source, refresh_s=10, time_source=time)
    assert store.size() == 1

    source.publish(w("a", 0, 99.0), 5)  # same window, published again
    source.publish(w("b", 0, 50.0), 5)
    assert store.size() == 1  # not stale yet
    time.now += 10
    assert store.participants() == ["a", "b"]
    assert store.latest("a").value("gluco_score") == 99.0
    assert source.calls[-1] == T0  # asked only for rows since the last publish


def test_a_failed_refresh_keeps_serving_the_previous_data():
    source = ScriptedSource()
    source.publish(w("a", 0, 10.0), 0)
    time = FakeTime()
    store = WindowStore(source, refresh_s=1, time_source=time)
    assert store.size() == 1
    source.fail = True
    time.now += 5
    assert store.size() == 1
