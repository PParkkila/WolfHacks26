"""The metric catalog: every value a window carries and how to read it.

The single source for what the data adapters read, what `/catalog` returns, and
what the agents' tools and prompts call each value.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricSpec:
    label: str
    unit: str
    description: str
    # True: higher is better; False: lower is better; None: no direction.
    higher_is_better: bool | None


GLUCO_SCORE = "gluco_score"
GLUCO_CHANGE = "gluco_change_24h"

METRICS: dict[str, MetricSpec] = {
    GLUCO_SCORE: MetricSpec(
        "Gluco Score",
        "points (0-100)",
        "How closely the last 24 hours of wearable data resemble the study's "
        "healthier (lower-HbA1c) group. Higher is healthier. A model estimate, "
        "not a glucose reading or a diagnosis.",
        True,
    ),
    GLUCO_CHANGE: MetricSpec(
        "Gluco Score change (24 h)",
        "points",
        "Gluco Score now minus Gluco Score 24 hours earlier.",
        True,
    ),
    "hr_mean_bpm_24h": MetricSpec(
        "Mean heart rate",
        "bpm",
        "Mean heart rate over the last 24 hours.",
        None,
    ),
    "motion_mean_g": MetricSpec(
        "Mean movement",
        "g",
        "Mean wrist acceleration over the last 24 hours; higher means more movement.",
        True,
    ),
    "motion_std_g": MetricSpec(
        "Movement variability",
        "g",
        "How much wrist movement varied over the last 24 hours.",
        None,
    ),
    "motion_p90_g": MetricSpec(
        "Peak movement (90th percentile)",
        "g",
        "The level of wrist movement exceeded only 10% of the time in the last "
        "24 hours; a proxy for the more active moments of the day.",
        None,
    ),
    "temperature_mean_c_24h": MetricSpec(
        "Mean skin temperature",
        "°C",
        "Mean wrist skin temperature over the last 24 hours (not core body "
        "temperature).",
        None,
    ),
    "temperature_std_c_24h": MetricSpec(
        "Skin temperature variability",
        "°C",
        "How much wrist skin temperature varied over the last 24 hours.",
        None,
    ),
    "motion_hr_correlation": MetricSpec(
        "Movement-heart rate coupling",
        "correlation (-1 to 1)",
        "How closely heart rate followed movement over the last 24 hours.",
        None,
    ),
}

# Measured by the wearable, as opposed to the model's Gluco Score.
SENSOR_METRICS: tuple[str, ...] = tuple(
    name for name in METRICS if name not in (GLUCO_SCORE, GLUCO_CHANGE)
)


def unit_of(metric: str) -> str:
    return METRICS[metric].unit
