"""Risk tools: the model's output for a person, why, and who ranks highest."""

from typing import Any

from agents import FunctionTool, function_tool

from agent.explanation import CAVEAT, METHOD, Explanation, NoFeatures, Withheld
from agent.tools.base import (
    MAX_ROWS,
    ToolDeps,
    cap_rows,
    error,
    not_found,
    result,
    safe_tool,
    verdict_fields,
    window_of,
)


def _rounded(values: dict[str, Any], digits: int = 2) -> dict[str, Any]:
    return {
        k: round(v, digits) if isinstance(v, float) else v for k, v in values.items()
    }


def build(deps: ToolDeps) -> list[FunctionTool]:
    assessor, explainer = deps.assessor, deps.explainer

    @function_tool
    @safe_tool
    def get_risk_label(person_id: str, window: str = "latest") -> dict[str, Any]:
        """Get the model's risk score, label and confidence for one person.

        Also returns wear time, the data-quality verdict, and whether the result
        is reliable enough to support a judgement (`reliable`, `abstain_reason`).

        Args:
            person_id: The person's id, for example "P012".
            window: "latest" (default) or an ISO-8601 window end timestamp.
        """
        assessment = assessor.assess(person_id, window)
        if assessment is None:
            return not_found(person_id)
        score = assessment.score
        scored = score.score is not None
        return result(
            summary=(
                f"{person_id}: {score.label} (score {score.score}, "
                f"confidence {score.confidence})"
                if scored
                else f"{person_id}: not yet scored"
            ),
            rows=1,
            model_version=score.model_version,
            window=window_of(score),
            person_id=person_id,
            scored=scored,
            score=score.score,
            label=score.label,
            confidence=score.confidence,
            wear_time_hours=score.wear_time_hours,
            missing_signal_pct=score.missing_signal_pct,
            **verdict_fields(assessment),
        )

    @function_tool
    @safe_tool
    def explain_risk(person_id: str) -> dict[str, Any]:
        """Describe which of a person's features deviate most from the cohort.

        Returns the top 5 features by absolute z-score with value, cohort median,
        percentile and direction, and whether each deviates the way the cohort's
        at-risk group does. This is a cohort-deviation description (method
        "cohort_deviation"), NOT model attribution. If `tension` is true, the
        features argue against the person's label and that must be said.
        Withheld when the result is not reliable.

        Args:
            person_id: The person's id, for example "P012".
        """
        assessment = assessor.assess(person_id)
        if assessment is None:
            return not_found(person_id)
        score = assessment.score
        window = window_of(score)

        match explainer.explain(assessment):
            case Withheld(reason):
                return result(
                    summary=f"{person_id}: explanation withheld ({reason})",
                    rows=0,
                    model_version=score.model_version,
                    window=window,
                    method=METHOD,
                    abstain=True,
                    abstain_reason=reason,
                )
            case NoFeatures():
                return error(
                    "no_features", f"No feature vector stored for {person_id}."
                )
            case Explanation(deviations, tension):
                return result(
                    summary=(
                        f"{person_id}: {len(deviations)} most unusual features "
                        "vs cohort"
                    ),
                    rows=len(deviations),
                    model_version=score.model_version,
                    window=window,
                    method=METHOD,
                    person_id=person_id,
                    label=score.label,
                    score=score.score,
                    confidence=score.confidence,
                    top_features=[_rounded(d.model_dump()) for d in deviations],
                    tension=tension.present,
                    aligned_with_at_risk_group=tension.aligned,
                    opposed_to_at_risk_group=tension.opposed,
                    caveat=CAVEAT,
                )

    @function_tool
    @safe_tool
    def rank_candidates(top_k: int = 10, min_confidence: float = 0.0) -> dict[str, Any]:
        """Rank scored people by risk score, highest first.

        Each row says whether the result is `reliable`; unreliable rows should be
        flagged, not presented as firm candidates.

        Args:
            top_k: How many people to return (1-200).
            min_confidence: Exclude people whose confidence is below this (0-1).
        """
        if not 1 <= top_k <= MAX_ROWS:
            raise ValueError(f"top_k must be between 1 and {MAX_ROWS}")
        scored = [
            a
            for a in assessor.assess_all()
            if a.score.score is not None
            and (a.score.confidence or 0.0) >= min_confidence
        ]
        scored.sort(key=lambda a: (-(a.score.score or 0.0), a.person_id))
        rows, truncation = cap_rows(scored[:top_k])
        return result(
            summary=f"Top {len(rows)} of {len(scored)} scored people by risk score",
            rows=len(rows),
            model_version=rows[0].score.model_version if rows else None,
            candidates=[
                {
                    "rank": rank,
                    "person_id": a.person_id,
                    "score": a.score.score,
                    "label": a.score.label,
                    "confidence": a.score.confidence,
                    "window_end": a.score.window_end.isoformat(),
                    **verdict_fields(a),
                }
                for rank, a in enumerate(rows, start=1)
            ],
            scored_people=len(scored),
            **truncation,
        )

    return [get_risk_label, explain_risk, rank_candidates]
