"""Dashboard widgets: what one is, and the pipeline that builds it.

The chat agent decides what to show (a kind and a few query arguments). The
stages here do the rest in code, the same way for a new widget and for every
refresh of a pinned one:

1. design:     turn the kind into a re-runnable QuerySpec (relative `hours`,
               never absolute times, so a pinned widget follows the clock);
2. fetch:      run it through the caller's QueryService (scope + replay clock);
3. compliance: `analysis.compliance.sanitize`;
4. bind:       return the spec with the data, so a pin can refresh itself.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agent.analysis.compliance import sanitize
from agent.domain.errors import QueryError
from agent.domain.metrics import metric_label
from agent.query import QueryResult, QueryService, QuerySpec

WidgetKind = Literal["trend", "ranking", "cohort_trend", "stat", "table", "heatmap"]
Stage = Literal["design", "fetch", "compliance", "bind"]

KIND_SHAPES: dict[WidgetKind, str] = {
    "trend": "Line chart",
    "ranking": "Ranked bars",
    "cohort_trend": "Panel average line",
    "stat": "Stat tile",
    "table": "Comparison table",
    "heatmap": "Heatmap by day",
}


class WidgetSpec(BaseModel):
    """What a pin stores: enough to rebuild the widget at any later time."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120)
    kind: WidgetKind
    query: QuerySpec


class WidgetStep(BaseModel):
    stage: Stage
    text: str


class BuiltWidget(BaseModel):
    spec: WidgetSpec
    result: QueryResult
    steps: list[WidgetStep]


def design(
    kind: WidgetKind,
    metrics: list[str],
    participants: list[str] | None,
    hours: float,
    agg: str | None,
    order: str,
    limit: int,
    panel: bool = False,
) -> QuerySpec:
    """The query that draws `kind` well.

    `panel` is true for a clinician, whose stat tile with no one named is the
    panel average; a patient's QueryService only ever sees themselves anyway.
    """
    participants = participants or None  # models send [] for "everyone"
    bucket = "hour" if hours <= 48 else "day"
    if kind == "stat":
        return QuerySpec(
            metrics=metrics[:1],
            participants=participants,
            hours=hours,
            bucket=bucket,
            agg=agg or "mean",  # pyright: ignore[reportArgumentType]
            group_by="cohort" if panel and participants is None else "participant",
        )
    if kind == "heatmap":
        return QuerySpec(
            metrics=metrics[:1],
            participants=participants,
            hours=hours,
            bucket="day",
            agg=agg or "mean",  # pyright: ignore[reportArgumentType]
            sort_by=None if participants else metrics[0],
            order=order,  # pyright: ignore[reportArgumentType]
            limit=None if participants else limit,
        )
    if kind in ("ranking", "table"):
        return QuerySpec(
            metrics=metrics,
            participants=participants,
            hours=hours,
            bucket="all",
            agg=agg or "last",  # pyright: ignore[reportArgumentType]
            sort_by=metrics[0],
            order=order,  # pyright: ignore[reportArgumentType]
            limit=limit,
        )
    if kind == "cohort_trend":
        return QuerySpec(
            metrics=metrics,
            hours=hours,
            bucket=bucket,
            agg=agg or "mean",  # pyright: ignore[reportArgumentType]
            group_by="cohort",
        )
    return QuerySpec(
        metrics=metrics,
        participants=participants,
        hours=hours,
        bucket=bucket,
        agg=agg or "mean",  # pyright: ignore[reportArgumentType]
        # Without named people, keep the chart readable: the `limit` lowest or
        # highest by their newest value.
        sort_by=None if participants else metrics[0],
        order=order,  # pyright: ignore[reportArgumentType]
        limit=None if participants else limit,
    )


def build(svc: QueryService, spec: WidgetSpec) -> BuiltWidget:
    """Run the fetch, compliance and bind stages for an already designed spec."""
    query = spec.query
    labels = ", ".join(metric_label(m) for m in query.metrics)
    steps = [
        WidgetStep(
            stage="design",
            text=f"{KIND_SHAPES[spec.kind]} of {labels}, last {query.hours or 168:g} h",
        )
    ]

    raw = svc.query(query)
    points = sum(len(s.points) for s in raw.series)
    if points == 0:
        raise QueryError(
            "No data in that range.",
            hint="Use a longer `hours` or another metric.",
        )
    steps.append(
        WidgetStep(
            stage="fetch",
            text=f"Fetched {points} data points across {len(raw.series)} series",
        )
    )

    clean, audit = sanitize(raw, svc.principal)
    steps.append(WidgetStep(stage="compliance", text="; ".join(audit)))
    steps.append(
        WidgetStep(
            stage="bind", text="Bound to a live query: refreshes as data streams in"
        )
    )
    return BuiltWidget(spec=spec, result=clean, steps=steps)
