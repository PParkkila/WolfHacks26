"""Fixtures for the mock backend: the feature set and the pinned edge cases.

These are what break an agent at demo time: low wear, low confidence, not scored,
a label contradicted by its features. Edit them here; `mock.py` generates everyone
else around them.
"""

from dataclasses import dataclass, field

from agent.domain.models import RiskLabel


@dataclass(frozen=True)
class FeatureSpec:
    mean: float
    sd: float
    risk_sign: int  # +1: higher values go with higher risk
    decimals: int


FEATURES: dict[str, FeatureSpec] = {
    "resting_hr_bpm": FeatureSpec(68.0, 8.0, +1, 1),
    "hrv_rmssd_ms": FeatureSpec(42.0, 12.0, -1, 1),
    "daily_step_count": FeatureSpec(7500.0, 2500.0, -1, 0),
    "sedentary_hours": FeatureSpec(9.5, 2.0, +1, 1),
    "nightly_activity_index": FeatureSpec(0.35, 0.12, -1, 2),
    "sleep_efficiency_pct": FeatureSpec(88.0, 5.0, -1, 1),
    "hr_recovery_bpm": FeatureSpec(22.0, 6.0, -1, 1),
    "movement_intensity_mg": FeatureSpec(28.0, 9.0, -1, 1),
}


@dataclass(frozen=True)
class EdgeCase:
    score: float | None
    label: RiskLabel | None
    confidence: float | None
    wear_time_hours: float
    missing_signal_pct: float
    z: dict[str, float] = field(default_factory=dict)  # feature z-scores to pin


EDGE_CASES: dict[str, EdgeCase] = {
    # Flagged, healthy data, the person the demo asks about.
    "P012": EdgeCase(
        0.87,
        "at_risk",
        0.91,
        22.5,
        4.0,
        {
            "resting_hr_bpm": 1.6,
            "nightly_activity_index": -1.45,
            "hrv_rmssd_ms": -1.0,
            "sedentary_hours": 1.1,
            "daily_step_count": -0.8,
        },
    ),
    # Not flagged, clean data.
    "P003": EdgeCase(0.12, "not_at_risk", 0.88, 23.0, 3.0),
    # Changed between windows (see PREVIOUS_EDGE_CASES).
    "P007": EdgeCase(
        0.66,
        "at_risk",
        0.80,
        21.0,
        6.0,
        {"resting_hr_bpm": 1.2, "hrv_rmssd_ms": -1.3, "sedentary_hours": 1.0},
    ),
    # Insufficient data quality (wear time under 10h).
    "P031": EdgeCase(0.72, "at_risk", 0.80, 6.5, 58.0),
    "P038": EdgeCase(0.31, "not_at_risk", 0.75, 8.2, 35.0),
    # Confidence near 0.5: must abstain.
    "P019": EdgeCase(0.52, "at_risk", 0.52, 21.0, 5.0),
    "P027": EdgeCase(0.47, "not_at_risk", 0.49, 20.0, 8.0),
    # Not yet scored.
    "P035": EdgeCase(None, None, None, 20.0, 6.0),
    # Labelled at risk, but every deviating feature points the protective way.
    "P024": EdgeCase(
        0.74,
        "at_risk",
        0.85,
        22.0,
        5.0,
        {
            "resting_hr_bpm": -1.5,
            "hrv_rmssd_ms": 1.4,
            "daily_step_count": 1.3,
            "sedentary_hours": -1.2,
            "nightly_activity_index": 1.1,
        },
    ),
    # Marginal data quality.
    "P014": EdgeCase(0.58, "at_risk", 0.74, 13.5, 12.0),
    "P021": EdgeCase(0.22, "not_at_risk", 0.83, 19.0, 31.0),
}

PREVIOUS_EDGE_CASES: dict[str, EdgeCase] = {
    "P007": EdgeCase(
        0.38,
        "not_at_risk",
        0.82,
        22.0,
        5.0,
        {"resting_hr_bpm": 0.1, "hrv_rmssd_ms": 0.2, "sedentary_hours": -0.1},
    ),
}
