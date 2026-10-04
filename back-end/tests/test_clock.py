from datetime import UTC, datetime, timedelta

import pytest
from support import FakeTime

from agent.clock import ReplayClock

START = datetime(2026, 9, 27, 5, tzinfo=UTC)
END = START + timedelta(hours=170)


def make(**kwargs) -> tuple[ReplayClock, FakeTime]:
    time = FakeTime()
    bounds = kwargs.pop("bounds", (START, END))
    clock = ReplayClock(lambda: bounds, time_source=time, **kwargs)
    return clock, time


def test_starts_one_day_in_on_first_use_and_advances_one_hour_per_period():
    clock, time = make(seconds_per_hour=5)
    time.now += 500  # an idle server does not run the replay ahead
    assert clock.now() == START + timedelta(hours=24)
    time.now += 10
    assert clock.now() == START + timedelta(hours=26)


def test_configured_start_is_clamped_to_the_data():
    clock, _ = make(start=START - timedelta(days=30))
    assert clock.now() == START


def test_pause_play_and_speed():
    clock, time = make(seconds_per_hour=5)
    clock.pause()
    time.now += 100
    assert clock.now() == START + timedelta(hours=24)
    clock.play()
    clock.set_speed(1)
    time.now += 3
    assert clock.now() == START + timedelta(hours=27)
    with pytest.raises(ValueError, match="positive"):
        clock.set_speed(0)


def test_seek_is_clamped_and_reported():
    clock, _ = make()
    clock.seek(END + timedelta(days=1))
    assert clock.now() == END
    clock.seek(START + timedelta(hours=5))
    assert clock.state().now == START + timedelta(hours=5)


def test_stops_at_the_newest_window():
    clock, time = make(seconds_per_hour=1)
    clock.now()
    time.now += 10_000
    state = clock.state()
    assert (state.now, state.playing, state.at_end) == (END, False, True)


def test_disabled_clock_is_always_the_newest_window():
    clock, time = make(enabled=False)
    assert clock.now() == END
    time.now += 100
    assert clock.state().playing is False


def test_no_data_means_no_now():
    clock, _ = make(bounds=None)
    assert clock.now() is None
