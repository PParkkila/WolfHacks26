"""Storage-agnostic records shared by data adapters, analysis and tools."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

CohortGroup = Literal["all", "at_risk"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class RiskScore(_Frozen):
    """One person's model output for one scoring window.

    A null score means "not scored", never zero.
    """

    person_id: str
    window_start: datetime
    window_end: datetime
    score: float | None
    label: str | None
    confidence: float | None
    wear_time_hours: float | None
    missing_signal_pct: float | None  # percent of the window, 0-100
    model_version: str


class FeatureVector(_Frozen):
    """The feature values the model consumed for one person and window."""

    person_id: str
    window_end: datetime
    values: dict[str, float | None]


class FeatureStat(_Frozen):
    """Distribution summary of one feature over a cohort group."""

    feature_name: str
    mean: float
    stddev: float
    p25: float
    p50: float
    p75: float
