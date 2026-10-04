"""The widget builder tools: one call runs the whole pipeline in `agent.widgets`.

Clinicians get `build_widget` (any kind, anyone on the panel). Patients get
`build_my_widget`, which, like every patient tool, takes no participant
argument: it can only ever chart the signed-in patient's own readings.
"""

from typing import Any, Literal

from agents import FunctionTool, function_tool

from agent import widgets
from agent.query import QueryService
from agent.tools.base import chart, dump, result, safe_tool


def _widget_result(svc: QueryService, spec: widgets.WidgetSpec) -> dict[str, Any]:
    built = widgets.build(svc, spec)
    return result(
        summary=f"Built widget {spec.title!r}",
        rows=sum(len(s.points) for s in built.result.series),
        as_of=svc.as_of(),
        chart=chart(built.result),
        widget={
            "title": spec.title,
            "kind": spec.kind,
            "query": spec.query.model_dump(mode="json", exclude_none=True),
            "steps": [dump(step) for step in built.steps],
        },
    )


def build_widget_tool(svc: QueryService) -> FunctionTool:
    @function_tool
    @safe_tool
    def build_widget(
        title: str,
        kind: Literal["trend", "ranking", "cohort_trend"],
        metrics: list[str],
        participants: list[str] | None = None,
        hours: float = 168,
        agg: Literal["mean", "median", "min", "max", "last", "delta"] | None = None,
        order: Literal["asc", "desc"] = "asc",
        limit: int = 5,
    ) -> dict[str, Any]:
        """Build a dashboard widget the user can pin. Use when they ask for a
        widget, or to track, monitor, pin or keep an eye on something.

        Runs a pipeline: design the query, fetch, compliance check, bind to live
        data. The app draws the widget under your answer with a Pin button.

        Args:
            title: A short title, e.g. "Lowest Gluco Scores now".
            kind: "trend" (values over time), "ranking" (who is highest or
                lowest; sorted bars), or "cohort_trend" (the panel average over
                time).
            metrics: Metric names from the catalog; a ranking sorts by the first.
            participants: For "trend" or "ranking": who to include (short refs
                are fine). Omit for the `limit` lowest (order="asc") or highest.
            hours: How far back from now (default 168, one week).
            agg: How values are reduced (default "last" for a ranking, "mean"
                otherwise).
            order: "asc" puts the lowest first, "desc" the highest.
            limit: How many people a ranking or an unnamed trend shows (1-20).
        """
        if not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20")
        spec = widgets.WidgetSpec(
            title=title,
            kind=kind,
            query=widgets.design(kind, metrics, participants, hours, agg, order, limit),
        )
        return _widget_result(svc, spec)

    return build_widget


def build_my_widget_tool(svc: QueryService) -> FunctionTool:
    @function_tool
    @safe_tool
    def build_my_widget(
        title: str,
        metrics: list[str],
        hours: float = 168,
        agg: Literal["mean", "median", "min", "max"] | None = None,
    ) -> dict[str, Any]:
        """Build a widget of your own readings over time, which you can pin to
        your page. Use when you're asked for a widget, or to track or keep an
        eye on something.

        Runs a pipeline: design the query, fetch your data, compliance check,
        bind to live data. The app draws it under your answer with a Pin button.

        Args:
            title: A short, friendly title, e.g. "My heart rate this week".
            metrics: Metric names from the catalog.
            hours: How far back from now (default 168, one week).
            agg: How each hour or day is reduced (default "mean").
        """
        spec = widgets.WidgetSpec(
            title=title,
            kind="trend",
            query=widgets.design("trend", metrics, None, hours, agg, "asc", 1),
        )
        return _widget_result(svc, spec)

    return build_my_widget
