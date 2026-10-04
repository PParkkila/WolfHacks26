"""Shared constants and helpers for tests (fixtures live in conftest.py)."""

PID = "demo:big_ideas:013"  # the pinned sharp drop in the mock data
OTHER = "demo:big_ideas:002"


class FakeTime:
    """A controllable monotonic clock, in seconds."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now
