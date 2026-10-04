"""Conventions every tool follows.

- Returns a JSON-able dict, never prose.
- Carries `summary` and `rows` (read by the SSE layer for `tool_end`) and `as_of`
  (the replay clock's "now", so the agent never guesses what "today" is).
- Series data goes under `chart`, in the same shape `POST /query` returns. The
  SSE layer forwards it as a `data` event so the UI can draw it inline, and the
  LLM reads its numbers from the same place.
- Never raises: a failure becomes `{"error": ...}` the agent can explain,
  because an exception would kill the stream mid-answer.
"""

import functools
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from agent.analysis.query import downsample
from agent.domain.errors import (
    AmbiguousPersonError,
    ForbiddenError,
    PersonNotFoundError,
    QueryError,
)
from agent.query import QueryResult

log = logging.getLogger(__name__)

MAX_ROWS = 200
CHART_POINTS = 48  # per series, for anything handed to the LLM
LLM_POINT_BUDGET = 240  # across all series of one tool result


def dump(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")


def chart(result: QueryResult, max_points: int = CHART_POINTS) -> dict[str, Any]:
    """A query result trimmed to a size the LLM can read.

    Each series keeps at most `max_points` evenly spaced points, and the whole
    chart at most LLM_POINT_BUDGET.
    """
    per_series = max(2, min(max_points, LLM_POINT_BUDGET // max(1, len(result.series))))
    trimmed = result.model_copy(
        update={
            "series": [
                s.model_copy(update={"points": downsample(s.points, per_series)})
                for s in result.series
            ]
        }
    )
    payload = dump(trimmed)
    payload["downsampled"] = any(len(s.points) > per_series for s in result.series)
    return payload


def require_points(result: QueryResult) -> QueryResult:
    """Raise when a query found nothing, so the agent hears why and can retry."""
    if not any(s.points for s in result.series):
        raise QueryError(
            "No data in that range.",
            data_available_until=result.as_of.isoformat() if result.as_of else None,
            hint="Use `hours` to look back from now instead of explicit dates.",
        )
    return result


def parse_time(value: str | None) -> datetime | None:
    """None or "" -> None; otherwise an ISO-8601 time (UTC if no zone given)."""
    if value is None or not value.strip():
        return None
    parsed = datetime.fromisoformat(value.strip())
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def result(
    *, summary: str, rows: int, as_of: datetime | None, **data: Any
) -> dict[str, Any]:
    return {
        "summary": summary,
        "rows": rows,
        "as_of": as_of.isoformat() if as_of else None,
        **data,
    }


def error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"error": message, "code": code, "rows": 0, "summary": message, **extra}


def safe_tool[F: Callable[..., dict[str, Any]]](fn: F) -> F:
    """Turn any exception into a structured error payload.

    Wraps without changing the signature, so the Agents SDK still derives the
    tool schema from the original type hints and docstring.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return fn(*args, **kwargs)
        except PersonNotFoundError as exc:
            return error(
                "not_found",
                f"No patient matches {exc.ref!r}.",
                suggestions=exc.suggestions,
            )
        except AmbiguousPersonError as exc:
            return error(
                "ambiguous",
                f"{exc.ref!r} matches several patients; ask which one.",
                candidates=exc.candidates,
            )
        except ForbiddenError as exc:
            return error("not_permitted", str(exc))
        except QueryError as exc:
            return error("bad_argument", str(exc), **exc.details)
        except ValueError as exc:
            return error("bad_argument", str(exc))
        except Exception as exc:
            log.exception("tool %s failed", fn.__name__)
            return error(
                "internal_error",
                "The data source could not answer this request right now; it may "
                "be retried.",
                detail=type(exc).__name__,
            )

    return wrapper  # type: ignore[return-value]


def grouping_phrase(bucket: str, agg: str) -> str:
    """ "mean per day", "latest value" ... for a tool summary."""
    if bucket == "raw":
        return "every reading"
    if bucket == "all":
        return f"{agg} over the whole range"
    return f"{agg} per {bucket}"


def week_summary(result: QueryResult, metric: str) -> dict[str, Any] | None:
    """First, newest, min, max and mean of one metric over a single-series result."""
    if not result.series:
        return None
    points = [p for p in result.series[0].points if p.get(metric) is not None]
    if not points:
        return None
    values = [p[metric] for p in points]
    low = min(points, key=lambda p: p[metric])
    high = max(points, key=lambda p: p[metric])
    return {
        "metric": metric,
        "from": points[0]["t"].isoformat(),
        "to": points[-1]["t"].isoformat(),
        "first": values[0],
        "newest": values[-1],
        "min": low[metric],
        "min_at": low["t"].isoformat(),
        "max": high[metric],
        "max_at": high["t"].isoformat(),
        "mean": round(sum(values) / len(values), 4),
        "points": len(values),
    }
