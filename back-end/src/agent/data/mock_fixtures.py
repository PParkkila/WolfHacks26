"""Fixtures for the mock source: who the participants are and how they move.

Each participant's Gluco Score follows a smooth daily rhythm around a baseline.
Pinned cases (PINNED) are the stories a demo or an eval asks about; `mock.py`
generates everyone else around them.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    baseline: float  # typical Gluco Score
    # Gluco Score points added per hour over the last `trend_hours` hours.
    trend_per_hour: float = 0.0
    trend_hours: int = 0
    has_hr: bool = True


PARTICIPANTS: tuple[str, ...] = (
    *(f"demo:big_ideas:{n:03d}" for n in range(1, 17)),
    "demo:imu50:00",
)

PINNED: dict[str, Profile] = {
    # Healthy for days, then a sharp drop over the last 8 hours.
    "demo:big_ideas:013": Profile(baseline=92.0, trend_per_hour=-10.0, trend_hours=8),
    # Steady improvement across the whole week.
    "demo:big_ideas:016": Profile(baseline=55.0, trend_per_hour=0.18, trend_hours=168),
    # Flat and healthy.
    "demo:big_ideas:010": Profile(baseline=84.0),
    # A device without a heart-rate sensor.
    "demo:imu50:00": Profile(baseline=45.0, has_hr=False),
}
