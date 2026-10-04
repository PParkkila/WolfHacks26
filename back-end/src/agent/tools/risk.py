"""Risk tools: the model's output for a person, why, and who ranks highest."""

from typing import Any

from agents import FunctionTool, function_tool

from agent.explanation import CAVEAT, METHOD, Explanation, NoFeatures, Withheld
from agent.tools.base import (
    MAX_ROWS,
    ToolDeps,
    cap_rows,
    error,
    model_output,
    require_assessment,
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
        When it is not reliable, `score`, `label` and `confidence` are null and
        `suppressed` is true: there is no finding to report.

        Args:
            person_id: The person's id, for example "P012".
            window: "latest" (default) or an ISO-8601 window end timestamp.
        """
        assessment = require_assessment(assessor, person_id, window)
        score = assessment.score
        if score.score is None:
            summary = f"{person_id}: not yet scored"
        elif not assessment.reliable:
            summary = f"{person_id}: result withheld ({assessment.abstain_reason})"
        else:
            summary = (
                f"{person_id}: {score.label} (score {score.score}, "
                f"confidence {score.confidence})"
            )
        return result(
            summary=summary,
            rows=1,
            model_version=score.model_version,
            window=window_of(score),
            person_id=person_id,
            scored=score.score is not None,
            wear_time_hours=score.wear_time_hours,
            missing_signal_pct=score.missing_signal_pct,
            **model_output(assessment),
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
        assessment = require_assessment(assessor, person_id)
        score = assessment.score
        window = window_of(score)

        match explainer.explain(assessment):
            case Withheld(reason):
                return result(
                    summary=f"{person_id}: explanation withheld ({reason})",
                    rows=0,
                    model_version=score.model_version,
                    window=window,
                    person_id=person_id,
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
                    **model_output(assessment),
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

        Only people whose result is reliable are ranked. Scored people whose
        result is not reliable are listed under `unranked` with the reason and
        no score: they are not candidates, and the answer should say so.

        Args:
            top_k: How many people to return (1-200).
            min_confidence: Exclude people whose confidence is below this (0-1).
        """
        if not 1 <= top_k <= MAX_ROWS:
            raise ValueError(f"top_k must be between 1 and {MAX_ROWS}")
        scored = [a for a in assessor.assess_all() if a.risk is not None]
        ranked = [
            a for a in scored if a.reliable and (a.confidence or 0.0) >= min_confidence
        ]
        ranked.sort(key=lambda a: (-(a.risk or 0.0), a.person_id))
        rows = ranked[:top_k]
        unranked, unranked_cap = cap_rows([a for a in scored if not a.reliable])
        return result(
            summary=(
                f"Top {len(rows)} of {len(ranked)} ranked people by risk score; "
                f"{len(unranked)} scored people not ranked (unreliable)"
            ),
            rows=len(rows),
            model_version=rows[0].score.model_version if rows else None,
            candidates=[
                {
                    "rank": rank,
                    "person_id": a.person_id,
                    "score": a.risk,
                    "label": a.score.label,
                    "confidence": a.confidence,
                    "window": window_of(a.score),
                    **verdict_fields(a),
                }
                for rank, a in enumerate(rows, start=1)
            ],
            scored_people=len(scored),
            unranked=[
                {
                    "person_id": a.person_id,
                    "window": window_of(a.score),
                    **verdict_fields(a),
                }
                for a in unranked
            ],
            **{f"unranked_{key}": value for key, value in unranked_cap.items()},
        )

    return [get_risk_label, explain_risk, rank_candidates]
