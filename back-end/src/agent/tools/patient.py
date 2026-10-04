"""Patient tools: one person's own data and nothing else.

No tool takes a participant argument. Each is bound to the signed-in patient,
so neither the user nor a prompt injection can reach anyone else's data.
"""

from typing import Any, Literal

from agents import FunctionTool, function_tool

from agent.domain.metrics import GLUCO_SCORE, metric_label
from agent.query import QueryService, QuerySpec
from agent.tools.base import (
    chart,
    dump,
    grouping_phrase,
    parse_time,
    require_points,
    result,
    safe_tool,
    week_summary,
)


def build(svc: QueryService) -> list[FunctionTool]:
    me = svc.principal.participant_id
    if me is None:
        raise ValueError("patient tools need a patient principal")

    @function_tool
    @safe_tool
    def get_my_status() -> dict[str, Any]:
        """Your newest values (Gluco Score and every sensor metric) and your Gluco
        Score over the last 7 days."""
        latest = svc.participant(me)
        week = svc.query(QuerySpec(metrics=[GLUCO_SCORE], hours=168, bucket="hour"))
        return result(
            summary=f"Gluco Score {latest.values.get(GLUCO_SCORE)}",
            rows=1,
            as_of=svc.as_of(),
            latest=dump(latest),
            gluco_week=week_summary(week, GLUCO_SCORE),
            chart=chart(week),
        )

    @function_tool
    @safe_tool
    def explain_my_change(hours: float = 24) -> dict[str, Any]:
        """What changed alongside your Gluco Score.

        For the Gluco Score and every sensor metric: the newest value, the value
        `hours` earlier, the change, and how unusual the newest value is compared
        with your own last 7 days (z_vs_baseline: above about 2 or below about
        -2 is unusual for you). These are associations, not causes.

        Args:
            hours: How far back to compare (default 24).
        """
        report = svc.explain_change(me, hours)
        shown = [GLUCO_SCORE, *report.largest_shifts[:1]]
        trend = svc.query(
            QuerySpec(metrics=shown, hours=max(hours * 2, 48), bucket="hour")
        )
        gluco = next(c for c in report.changes if c.metric == GLUCO_SCORE)
        return result(
            summary=f"Gluco Score {gluco.then} -> {gluco.now} over {hours:g} h",
            rows=len(report.changes),
            as_of=svc.as_of(),
            change=dump(report),
            chart=chart(trend),
        )

    @function_tool
    @safe_tool
    def get_my_trend(
        metric: str = GLUCO_SCORE,
        hours: float = 168,
        bucket: Literal["hour", "day"] = "hour",
    ) -> dict[str, Any]:
        """How one of your metrics moved over a period: first, newest, lowest,
        highest and average, plus the series.

        Args:
            metric: A metric name from the catalog (default "gluco_score").
            hours: How many hours back from now (default 168, one week).
            bucket: "hour" or "day" averages.
        """
        trend = svc.query(
            QuerySpec(metrics=[metric], hours=hours, bucket=bucket, agg="mean")
        )
        return result(
            summary=f"{metric_label(metric)} over the last {hours:g} h",
            rows=sum(len(s.points) for s in trend.series),
            as_of=svc.as_of(),
            trend=week_summary(trend, metric),
            chart=chart(trend),
        )

    @function_tool
    @safe_tool
    def query_my_data(
        metrics: list[str],
        hours: float = 168,
        start: str | None = None,
        end: str | None = None,
        bucket: Literal["raw", "hour", "day", "all"] = "day",
        agg: Literal["mean", "median", "min", "max", "first", "last", "delta"] = "mean",
    ) -> dict[str, Any]:
        """Answer any other question about your own data with one structured query.

        Examples: your average heart rate per day this week (metrics=
        ["hr_mean_bpm_24h"], bucket="day"); your lowest Gluco Score each day
        (bucket="day", agg="min"); how much your movement changed over the
        last 3 days (hours=72, bucket="all", agg="delta").

        Args:
            metrics: Metric names from the catalog.
            hours: Look back this many hours from now when start is not given.
            start: ISO-8601 start (exclusive); overrides hours.
            end: ISO-8601 end (inclusive); defaults to now.
            bucket: "raw" (every hourly window), "hour", "day", or "all" (one value).
            agg: How to reduce each bucket. "delta" is last minus first.
        """
        answer = require_points(
            svc.query(
                QuerySpec(
                    metrics=metrics,
                    hours=hours,
                    start=parse_time(start),
                    end=parse_time(end),
                    bucket=bucket,
                    agg=agg,
                )
            )
        )
        return result(
            summary=(
                f"{', '.join(metric_label(m) for m in metrics)} "
                f"({grouping_phrase(bucket, agg)})"
            ),
            rows=sum(len(s.points) for s in answer.series),
            as_of=svc.as_of(),
            chart=chart(answer),
        )

    return [get_my_status, explain_my_change, get_my_trend, query_my_data]
