"""Data-quality tool: can this person's data support a judgement at all?"""

from typing import Any

from agents import FunctionTool, function_tool

from agent.tools.base import ToolDeps, not_found, result, safe_tool, window_of


def build(deps: ToolDeps) -> list[FunctionTool]:
    assessor = deps.assessor

    @function_tool
    @safe_tool
    def data_quality_check(person_id: str) -> dict[str, Any]:
        """Check whether a person's latest window has enough sensor data.

        Returns wear hours, the share of the window with no data, and a verdict of
        "good", "marginal" or "insufficient". An "insufficient" verdict means the
        data does not support a judgement.

        Args:
            person_id: The person's id, for example "P003".
        """
        assessment = assessor.assess(person_id)
        if assessment is None:
            return not_found(person_id)
        score, quality = assessment.score, assessment.quality
        return result(
            summary=f"{person_id}: data quality {quality.verdict}",
            rows=1,
            model_version=score.model_version,
            window=window_of(score),
            person_id=person_id,
            wear_time_hours=score.wear_time_hours,
            missing_signal_pct=score.missing_signal_pct,
            verdict=quality.verdict,
            reasons=list(quality.reasons),
        )

    return [data_quality_check]
