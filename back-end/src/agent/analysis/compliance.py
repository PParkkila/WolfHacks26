"""The compliance check every widget passes before anyone sees it.

A widget outlives a chat answer: it is pinned, refreshed and shown on a shared
screen. So before one is drawn (and on every refresh), this keeps a patient's
widget to their own series, replaces internal participant keys with display
names, and hides pooled cohort points built from too few people to stay
anonymous. It is code, not a prompt, so the model can neither skip it nor talk
its way past it.
"""

from agent.auth import Principal
from agent.query import QueryResult, Series

# Pooled cohort points from fewer people than this are hidden (small-cell rule).
MIN_COHORT_CELL = 3


def _suppress_small_cells(series: Series, metrics: list[str]) -> tuple[Series, int]:
    hidden = 0
    points = []
    for point in series.points:
        if point.get("participants", MIN_COHORT_CELL) < MIN_COHORT_CELL:
            hidden += 1
            point = {**point, **dict.fromkeys(metrics)}
        points.append(point)
    return series.model_copy(update={"points": points}), hidden


def sanitize(
    result: QueryResult, principal: Principal
) -> tuple[QueryResult, list[str]]:
    """The result with only what may be shown, plus one audit line per rule."""
    audit: list[str] = []
    series = list(result.series)

    if principal.role == "clinician":
        audit.append("Scope: clinician panel")
    else:
        own = [s for s in series if s.participant_id == principal.participant_id]
        removed = len(series) - len(own)
        series = own
        audit.append(
            "Scope: your own data only"
            + (f" ({removed} other series removed)" if removed else "")
        )

    keyed = sum(1 for s in series if s.participant_id is not None)
    series = [
        s.model_copy(update={"participant_id": s.display_name})
        if s.participant_id is not None
        else s
        for s in series
    ]
    if keyed:
        audit.append(f"{keyed} internal patient keys replaced with display names")

    hidden = 0
    cleaned: list[Series] = []
    for s in series:
        if s.participant_id is None:  # a pooled cohort series
            s, count = _suppress_small_cells(s, result.metrics)
            hidden += count
        cleaned.append(s)
    if result.group_by == "cohort":
        audit.append(
            f"{hidden} cohort points from fewer than {MIN_COHORT_CELL} people hidden"
            if hidden
            else f"Every cohort point pools at least {MIN_COHORT_CELL} people"
        )

    return result.model_copy(update={"series": cleaned}), audit
