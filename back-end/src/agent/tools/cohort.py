"""Cohort tools: where a person sits relative to everyone else."""

import difflib
from typing import Any

from agents import FunctionTool, function_tool

from agent.analysis.deviation import describe_feature
from agent.tools.base import ToolDeps, error, not_found, result, safe_tool, window_of


def build(deps: ToolDeps) -> list[FunctionTool]:
    repos = deps.repos

    @function_tool
    @safe_tool
    def compare_to_cohort(person_id: str, feature: str) -> dict[str, Any]:
        """Compare one feature of one person with the whole cohort.

        Returns the person's value, the cohort median, percentile and z-score.
        If the feature name is unknown, the error lists the available features.

        Args:
            person_id: The person's id, for example "P012".
            feature: Exact feature name, for example "resting_hr_bpm".
        """
        score = repos.risk.get_score(person_id)
        vector = (
            repos.features.get_features(person_id, score.window_end) if score else None
        )
        if score is None or vector is None:
            return not_found(person_id)

        stats = repos.stats.feature_stats("all")
        if feature not in stats:
            return error(
                "unknown_feature",
                f"No feature named {feature!r}.",
                available_features=sorted(stats),
                suggestions=difflib.get_close_matches(
                    feature, list(stats), n=3, cutoff=0.4
                ),
            )
        value = vector.values.get(feature)
        if value is None:
            return error("missing_value", f"{person_id} has no value for {feature!r}.")

        deviation = describe_feature(feature, value, stats[feature])
        if deviation is None:
            return error(
                "no_variation", f"{feature!r} does not vary across the cohort."
            )
        return result(
            summary=(
                f"{person_id} {feature}: {value} "
                f"vs cohort median {deviation.cohort_median:.2f}"
            ),
            rows=1,
            model_version=score.model_version,
            window=window_of(score),
            person_id=person_id,
            feature=feature,
            value=value,
            cohort_median=round(deviation.cohort_median, 2),
            cohort_mean=round(stats[feature].mean, 2),
            z_score=round(deviation.z_score, 2),
            percentile=round(deviation.percentile, 1),
            direction=deviation.direction,
            percentile_method="normal_approximation",
        )

    return [compare_to_cohort]
