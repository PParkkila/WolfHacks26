"""Storage-agnostic records shared by data adapters, analysis, API and tools."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Window(_Frozen):
    """One participant's trailing 24-hour summary, published hourly.

    `values` is keyed by the names in `domain.metrics.METRICS`. A missing value
    is None (for example heart rate on a device without a heart-rate sensor),
    never zero.
    """

    person_id: str
    source_dataset: str
    window_start: datetime
    window_end: datetime
    values: dict[str, float | None]

    def value(self, metric: str) -> float | None:
        return self.values.get(metric)


class FeatureStat(_Frozen):
    """Distribution summary of one metric over a group of windows."""

    feature_name: str
    mean: float
    stddev: float
    p50: float


class LiveReading(_Frozen):
    """One participant's newest sensor readings, refreshed every second.

    `values` is keyed by `domain.metrics.LIVE_METRICS`. `analytics_window_end` is
    the end of the newest published window, so a reader can tell when new
    analytics have landed.
    """

    person_id: str
    sensor_time: datetime
    analytics_window_end: datetime | None
    values: dict[str, float | None]
