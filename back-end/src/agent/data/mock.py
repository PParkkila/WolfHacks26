"""Seeded synthetic windows in the real data's shape, for tests and offline work.

17 participants with the real key format, hourly 24-hour windows over the same
dates as the published replay. The same seed always yields the same numbers.
Random draws are made for everyone before pinned profiles apply, so editing one
pinned case never shifts anyone else's data.
"""

import math
from datetime import UTC, datetime, timedelta

import numpy as np

from agent.data.mock_fixtures import PARTICIPANTS, PINNED, Profile
from agent.domain.metrics import GLUCO_CHANGE, GLUCO_SCORE
from agent.domain.models import Window
from agent.domain.ports import PublishedWindow

FIRST_END = datetime(2026, 9, 27, 5, tzinfo=UTC)
HOURS = 171
WINDOW = timedelta(hours=24)
PUBLISHED_AT = datetime(2026, 10, 4, 8, tzinfo=UTC)


def _clip(value: float, low: float, high: float) -> float:
    return float(min(max(value, low), high))


class MockSource:
    """Implements WindowSource in memory."""

    def __init__(self, seed: int = 7) -> None:
        rng = np.random.default_rng(seed)
        draws = {
            pid: (float(rng.uniform(25, 85)), rng.normal(0, 1, size=(HOURS, 5)))
            for pid in PARTICIPANTS
        }
        self._windows = [
            window for pid in PARTICIPANTS for window in self._series(pid, *draws[pid])
        ]

    @staticmethod
    def _series(person_id: str, baseline: float, noise: np.ndarray) -> list[Window]:
        profile = PINNED.get(person_id, Profile(baseline=baseline))
        dataset = person_id.split(":")[1]
        scores: list[float] = []
        windows: list[Window] = []
        for hour in range(HOURS):
            end = FIRST_END + timedelta(hours=hour)
            into_trend = hour - (HOURS - profile.trend_hours)
            trend = profile.trend_per_hour * max(0, into_trend)
            daily = 4.0 * math.sin(2 * math.pi * hour / 24)
            score = _clip(
                profile.baseline + trend + daily + 2.0 * noise[hour, 0], 0, 100
            )
            scores.append(score)
            # Sensors loosely follow the score: lower score, higher HR, less movement.
            strain = (100.0 - score) / 100.0
            hr = 64.0 + 30.0 * strain + 2.0 * noise[hour, 1]
            motion = _clip(0.035 - 0.02 * strain + 0.003 * noise[hour, 2], 0.005, 0.08)
            temp = 33.0 + 0.4 * noise[hour, 3]
            values: dict[str, float | None] = {
                GLUCO_SCORE: round(score, 2),
                GLUCO_CHANGE: round(score - scores[hour - 24], 2)
                if hour >= 24
                else None,
                "hr_mean_bpm_24h": round(hr, 1) if profile.has_hr else None,
                "motion_mean_g": round(motion, 4),
                "motion_std_g": round(motion * 1.3, 4),
                "motion_p90_g": round(motion * 2.2, 4),
                "temperature_mean_c_24h": round(temp, 2),
                "temperature_std_c_24h": round(1.5 + 0.2 * noise[hour, 4], 2),
                "motion_hr_correlation": (
                    round(_clip(0.4 + 0.1 * noise[hour, 4], -1, 1), 3)
                    if profile.has_hr
                    else None
                ),
            }
            windows.append(
                Window(
                    person_id=person_id,
                    source_dataset=dataset,
                    window_start=end - WINDOW,
                    window_end=end,
                    values=values,
                )
            )
        return windows

    def fetch_since(self, published_after: datetime | None) -> list[PublishedWindow]:
        if published_after is not None and published_after > PUBLISHED_AT:
            return []
        return [PublishedWindow(w, PUBLISHED_AT) for w in self._windows]

    def ping(self) -> bool:
        return True
