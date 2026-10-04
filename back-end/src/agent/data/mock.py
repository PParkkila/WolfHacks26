"""Seeded synthetic windows in the real data's shape, for tests and offline work.

17 participants with the real key format, hourly 24-hour windows over the same
dates as the published replay, plus live sensor readings that tick after the
newest window. The same seed always yields the same numbers.
Random draws are made for everyone before pinned profiles apply, so editing one
pinned case never shifts anyone else's data.
"""

import math
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import numpy as np

from agent.data.mock_fixtures import PARTICIPANTS, PINNED, Profile
from agent.domain.metrics import GLUCO_CHANGE, GLUCO_SCORE
from agent.domain.models import LiveReading, Window
from agent.domain.ports import PublishedWindow

FIRST_END = datetime(2026, 9, 27, 5, tzinfo=UTC)
HOURS = 171
WINDOW = timedelta(hours=24)
PUBLISHED_AT = datetime(2026, 10, 4, 8, tzinfo=UTC)


def _clip(value: float, low: float, high: float) -> float:
    return float(min(max(value, low), high))


class MockSource:
    """Implements WindowSource in memory."""

    def __init__(
        self, seed: int = 7, time_source: Callable[[], float] = time.monotonic
    ) -> None:
        self._time = time_source
        self._started = time_source()
        rng = np.random.default_rng(seed)
        draws = {
            pid: (float(rng.uniform(25, 85)), rng.normal(0, 1, size=(HOURS, 5)))
            for pid in PARTICIPANTS
        }
        self._windows = [
            window for pid in PARTICIPANTS for window in self._series(pid, *draws[pid])
        ]
        self._newest = {w.person_id: w for w in self._windows}

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
            hr_value = round(hr, 1) if profile.has_hr else None
            values: dict[str, float | None] = {
                GLUCO_SCORE: round(score, 2),
                GLUCO_CHANGE: round(score - scores[hour - 24], 2)
                if hour >= 24
                else None,
                "hr_mean_bpm_24h": hr_value,
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
                "latest_hr_bpm": hr_value,
                "latest_motion_g": round(motion, 4),
                "latest_skin_temperature_c": round(temp, 2),
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

    def fetch_live(self) -> list[LiveReading]:
        """Each newest window's readings with a gentle wobble, a second per second."""
        elapsed = int(self._time() - self._started)
        wobble = math.sin(elapsed / 10)
        readings: list[LiveReading] = []
        for pid, window in self._newest.items():
            hr = window.value("latest_hr_bpm")
            motion = window.value("latest_motion_g") or 0.0
            temp = window.value("latest_skin_temperature_c") or 0.0
            readings.append(
                LiveReading(
                    person_id=pid,
                    sensor_time=window.window_end + timedelta(seconds=elapsed),
                    analytics_window_end=window.window_end,
                    values={
                        "latest_hr_bpm": None
                        if hr is None
                        else round(hr + 3 * wobble, 1),
                        "latest_motion_g": round(
                            max(motion * (1 + 0.3 * wobble), 0), 4
                        ),
                        "latest_skin_temperature_c": round(temp + 0.1 * wobble, 2),
                    },
                )
            )
        return readings

    def ping(self) -> bool:
        return True
