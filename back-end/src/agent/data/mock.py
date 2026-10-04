"""Seeded synthetic cohort so the agent can be built and evaluated without a DB.

The same seed always yields the same numbers. Pinned edge cases (see EDGE_CASES)
are what break an agent at demo time: low wear, low confidence, not scored, a
label contradicted by its features. Random draws are made before overrides are
applied, so editing one edge case never shifts anyone else's data.
"""

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import numpy as np

from agent.analysis.stats import compute_feature_stats
from agent.domain.models import CohortGroup, FeatureStat, FeatureVector, RiskScore

MODEL_VERSION = "mock-v0.1"
N_PEOPLE = 40
LATEST_END = datetime(2026, 10, 2, tzinfo=UTC)
WINDOW = timedelta(hours=24)
WINDOW_ENDS = (LATEST_END, LATEST_END - WINDOW)  # newest first


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
    label: str | None
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


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


class MockBackend:
    """Implements every read port (risk, features, stats, health) in memory."""

    def __init__(self, seed: int = 7, n_people: int = N_PEOPLE) -> None:
        self._scores: dict[str, list[RiskScore]] = {}
        self._features: dict[str, list[FeatureVector]] = {}
        rng = np.random.default_rng(seed)
        for number in range(1, n_people + 1):
            person_id = f"P{number:03d}"
            # Draw first, override after, so pinned cases never shift other people.
            latent = float(rng.normal())
            windows = []
            for index, window_end in enumerate(WINDOW_ENDS):
                draws = self._draw(
                    rng, latent if index == 0 else latent + rng.normal(0, 0.35)
                )
                pinned = (EDGE_CASES if index == 0 else PREVIOUS_EDGE_CASES).get(
                    person_id
                )
                windows.append(self._build(person_id, window_end, draws, pinned))
            self._scores[person_id] = [score for score, _ in windows]
            self._features[person_id] = [vector for _, vector in windows]
        self._stats: dict[CohortGroup, dict[str, FeatureStat]] = {}

    # --- generation -------------------------------------------------------

    @staticmethod
    def _draw(rng: np.random.Generator, latent: float) -> dict:
        score = _sigmoid(1.6 * latent + float(rng.normal(0, 0.4)))
        return {
            "score": score,
            "confidence": float(
                np.clip(
                    0.6 + 0.35 * min(1.0, abs(score - 0.5) * 2) + rng.normal(0, 0.03),
                    0.6,
                    0.97,
                )
            ),
            "wear": float(rng.uniform(17.0, 24.0)),
            "missing": float(rng.uniform(1.0, 15.0)),
            "z": {
                name: spec.risk_sign * 1.0 * latent + float(rng.normal(0, 0.6))
                for name, spec in FEATURES.items()
            },
        }

    @staticmethod
    def _build(
        person_id: str, window_end: datetime, draws: dict, pinned: EdgeCase | None
    ) -> tuple[RiskScore, FeatureVector]:
        if pinned:
            score, label, confidence = pinned.score, pinned.label, pinned.confidence
            wear, missing = pinned.wear_time_hours, pinned.missing_signal_pct
            z = {**draws["z"], **pinned.z}
        else:
            score, confidence = draws["score"], draws["confidence"]
            label = "at_risk" if score >= 0.5 else "not_at_risk"
            wear, missing, z = draws["wear"], draws["missing"], draws["z"]

        risk = RiskScore(
            person_id=person_id,
            window_start=window_end - WINDOW,
            window_end=window_end,
            score=None if score is None else round(score, 3),
            label=label,
            confidence=None if confidence is None else round(confidence, 3),
            wear_time_hours=round(wear, 1),
            missing_signal_pct=round(missing, 1),
            model_version=MODEL_VERSION,
        )
        vector = FeatureVector(
            person_id=person_id,
            window_end=window_end,
            values={
                name: round(spec.mean + spec.sd * z[name], spec.decimals)
                for name, spec in FEATURES.items()
            },
        )
        return risk, vector

    # --- RiskRepository ---------------------------------------------------

    def get_score(
        self, person_id: str, window_end: datetime | None = None
    ) -> RiskScore | None:
        rows = self._scores.get(person_id)
        if not rows:
            return None
        if window_end is None:
            return rows[0]
        return next((r for r in rows if r.window_end == window_end), None)

    def latest_scores(self) -> list[RiskScore]:
        return [rows[0] for rows in self._scores.values()]

    # --- FeatureRepository ------------------------------------------------

    def get_features(
        self, person_id: str, window_end: datetime | None = None
    ) -> FeatureVector | None:
        rows = self._features.get(person_id)
        if not rows:
            return None
        if window_end is None:
            return rows[0]
        return next((v for v in rows if v.window_end == window_end), None)

    # --- CohortStatsRepository --------------------------------------------

    def feature_stats(self, group: CohortGroup = "all") -> dict[str, FeatureStat]:
        if group not in self._stats:
            people = [
                person_id
                for person_id, rows in self._scores.items()
                if group == "all" or rows[0].label == "at_risk"
            ]
            self._stats[group] = compute_feature_stats(
                self._features[person_id][0] for person_id in people
            )
        return self._stats[group]

    # --- HealthProbe ------------------------------------------------------

    def ping(self) -> bool:
        return True

    def model_version(self) -> str | None:
        return MODEL_VERSION
