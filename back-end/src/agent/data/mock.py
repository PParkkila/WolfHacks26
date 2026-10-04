"""Seeded synthetic cohort so the agent can be built and evaluated without a DB.

The same seed always yields the same numbers. Pinned edge cases (see EDGE_CASES)
are what break an agent at demo time: low wear, low confidence, not scored, a
label contradicted by its features. Random draws are made before overrides are
applied, so editing one edge case never shifts anyone else's data.
"""

import math
from datetime import UTC, datetime, timedelta
from typing import TypedDict

import numpy as np

from agent.analysis.stats import compute_feature_stats
from agent.data.cache import StatsCache
from agent.data.mock_fixtures import (
    EDGE_CASES,
    FEATURES,
    PREVIOUS_EDGE_CASES,
    EdgeCase,
)
from agent.domain.models import (
    CohortGroup,
    FeatureStat,
    FeatureVector,
    RiskScore,
    WindowKey,
)
from agent.domain.ports import FEATURE_WINDOW_TOLERANCE

MODEL_VERSION = "mock-v0.1"
N_PEOPLE = 40
LATEST_END = datetime(2026, 10, 2, tzinfo=UTC)
WINDOW = timedelta(hours=24)
WINDOW_ENDS = (LATEST_END, LATEST_END - WINDOW)  # newest first


class Draws(TypedDict):
    """One window's random draws, before any pinned edge case overrides them."""

    score: float
    confidence: float
    wear: float
    missing: float
    z: dict[str, float]


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _at_window[T: (RiskScore, FeatureVector)](
    rows: list[T], window_end: datetime | None, tolerance: timedelta = timedelta(0)
) -> T | None:
    """The newest row (rows are newest first), or the one ending at `window_end`.

    With a tolerance, the closest row within it wins.
    """
    if window_end is None:
        return rows[0]
    near = [r for r in rows if abs(r.window_end - window_end) <= tolerance]
    return min(near, key=lambda r: abs(r.window_end - window_end), default=None)


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
        self._stats = StatsCache(self._compute_stats)

    # --- generation -------------------------------------------------------

    @staticmethod
    def _draw(rng: np.random.Generator, latent: float) -> Draws:
        score = _sigmoid(1.6 * latent + float(rng.normal(0, 0.4)))
        return Draws(
            score=score,
            confidence=float(
                np.clip(
                    0.6 + 0.35 * min(1.0, abs(score - 0.5) * 2) + rng.normal(0, 0.03),
                    0.6,
                    0.97,
                )
            ),
            wear=float(rng.uniform(17.0, 24.0)),
            missing=float(rng.uniform(1.0, 15.0)),
            z={
                name: spec.risk_sign * 1.0 * latent + float(rng.normal(0, 0.6))
                for name, spec in FEATURES.items()
            },
        )

    @staticmethod
    def _build(
        person_id: str, window_end: datetime, draws: Draws, pinned: EdgeCase | None
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
        return _at_window(rows, window_end) if rows else None

    def latest_scores(self) -> list[RiskScore]:
        return [rows[0] for rows in self._scores.values()]

    def get_history(self, person_id: str, limit: int = 10) -> list[RiskScore]:
        return list(self._scores.get(person_id, []))[:limit]

    # --- FeatureRepository ------------------------------------------------

    def get_features(self, key: WindowKey) -> FeatureVector | None:
        rows = self._features.get(key.person_id)
        return (
            _at_window(rows, key.window_end, FEATURE_WINDOW_TOLERANCE) if rows else None
        )

    # --- CohortStatsRepository --------------------------------------------

    def feature_stats(self, group: CohortGroup = "all") -> dict[str, FeatureStat]:
        return self._stats.get(group)

    def _compute_stats(self, group: CohortGroup) -> dict[str, FeatureStat]:
        people = [
            person_id
            for person_id, rows in self._scores.items()
            if group == "all" or rows[0].label == "at_risk"
        ]
        return compute_feature_stats(
            self._features[person_id][0] for person_id in people
        )

    # --- HealthProbe ------------------------------------------------------

    def ping(self) -> bool:
        return True

    def model_version(self) -> str | None:
        return MODEL_VERSION
