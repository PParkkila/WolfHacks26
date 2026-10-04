"""Storage-agnostic records shared by data adapters, analysis and tools."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

RiskLabel = Literal["at_risk", "not_at_risk"]
CohortGroup = Literal["all", "at_risk"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class WindowKey(_Frozen):
    """Names one person's scoring window: the thing a score and its features share."""

    person_id: str
    window_end: datetime


class RiskScore(_Frozen):
    """One person's model output for one scoring window.

    A null score means "not scored", never zero.
    """

    person_id: str
    window_start: datetime
    window_end: datetime
    score: float | None
    label: RiskLabel | None
    confidence: float | None
    wear_time_hours: float | None
    missing_signal_pct: float | None  # percent of the window, 0-100
    model_version: str

    @property
    def key(self) -> WindowKey:
        return WindowKey(person_id=self.person_id, window_end=self.window_end)


class FeatureVector(_Frozen):
    """The feature values the model consumed for one person and window."""

    person_id: str
    window_end: datetime
    values: dict[str, float | None]

    @property
    def key(self) -> WindowKey:
        return WindowKey(person_id=self.person_id, window_end=self.window_end)


class FeatureStat(_Frozen):
    """Distribution summary of one feature over a cohort group."""

    feature_name: str
    mean: float
    stddev: float
    p50: float
