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
    # True: a seconds-old sensor reading rather than a 24-hour summary.
    live: bool = False


GLUCO_SCORE = "gluco_score"
GLUCO_CHANGE = "gluco_change_24h"

METRICS: dict[str, MetricSpec] = {
    GLUCO_SCORE: MetricSpec(
        "Gluco Score",
        "points out of 100",
        "How closely the last 24 hours of wearable data resemble people with "
        "healthier blood sugar. Higher is healthier. A model estimate, not a "
        "blood sugar reading or a diagnosis.",
        True,
    ),
    GLUCO_CHANGE: MetricSpec(
        "Gluco Score change (24 h)",
        "points",
        "How much the Gluco Score has moved compared with 24 hours ago.",
        True,
    ),
    "hr_mean_bpm_24h": MetricSpec(
        "Mean heart rate",
        "bpm",
        "Average heart rate over the last 24 hours.",
        None,
    ),
    "motion_mean_g": MetricSpec(
        "Average movement",
        "g",
        "How much your wrist moved on average over the last 24 hours; higher "
        "means more movement.",
        True,
    ),
    "motion_std_g": MetricSpec(
        "Movement variability",
        "g",
        "How much your wrist movement went up and down over the last 24 hours.",
        None,
    ),
    "motion_p90_g": MetricSpec(
        "Peak movement",
        "g",
        "How active your most active moments were over the last 24 hours "
        "(the movement level you were above only 10% of the time).",
        None,
    ),
    "temperature_mean_c_24h": MetricSpec(
        "Average skin temperature",
        "°C",
        "Average skin temperature at the wrist over the last 24 hours (not your "
        "core body temperature).",
        None,
    ),
    "temperature_std_c_24h": MetricSpec(
        "Skin temperature variability",
        "°C",
        "How much skin temperature at the wrist went up and down over the last "
        "24 hours.",
        None,
    ),
    "motion_hr_correlation": MetricSpec(
        "Movement and heart rate link",
        "-1 to 1",
        "How closely your heart rate followed your movement over the last 24 "
        "hours (closer to 1 means they moved together).",
        None,
    ),
    "latest_hr_bpm": MetricSpec(
        "Heart rate now",
        "bpm",
        "The most recent heart-rate reading from the wearable, updated every second.",
        None,
        live=True,
    ),
    "latest_motion_g": MetricSpec(
        "Movement now",
        "g",
        "The most recent wrist movement reading from the wearable, updated every "
        "second.",
        None,
        live=True,
    ),
    "latest_skin_temperature_c": MetricSpec(
        "Skin temperature now",
        "°C",
        "The most recent skin temperature reading at the wrist (not core body "
        "temperature), updated every second.",
        None,
        live=True,
    ),
}

# Readings the wearable streams every second.
LIVE_METRICS: tuple[str, ...] = tuple(
    name for name, spec in METRICS.items() if spec.live
)

# 24-hour summaries measured by the wearable, as opposed to the model's Gluco
# Score and the live readings.
SENSOR_METRICS: tuple[str, ...] = tuple(
    name
    for name, spec in METRICS.items()
    if name not in (GLUCO_SCORE, GLUCO_CHANGE) and not spec.live
)

# Every value a published window carries besides the Gluco Score: its payload
# also holds the live readings as they were when the window was computed.
WINDOW_METRICS: tuple[str, ...] = SENSOR_METRICS + LIVE_METRICS


def unit_of(metric: str) -> str:
    return METRICS[metric].unit


def metric_label(metric: str) -> str:
    """The readable name for a metric key; an unknown key is returned as given."""
    spec = METRICS.get(metric)
    return spec.label if spec else metric
