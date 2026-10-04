"""Conventions every tool follows.

- Returns a JSON-able dict, never prose.
- Carries `summary` and `rows` (read by the SSE layer for `tool_end`).
- Carries `model_version` and the `window` it used.
- Caps rows at MAX_ROWS and says so when it truncates.
- Never raises: a failure becomes `{"error": ...}` the agent can explain,
  because an exception would kill the stream mid-answer.
"""

import functools
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from agent.analysis.quality import ReliabilityPolicy
from agent.domain.models import RiskScore
from agent.domain.ports import Repositories

log = logging.getLogger(__name__)

MAX_ROWS = 200


@dataclass(frozen=True)
class ToolDeps:
    repos: Repositories
    policy: ReliabilityPolicy


def window_of(score: RiskScore) -> dict[str, str]:
    return {
        "start": score.window_start.isoformat(),
        "end": score.window_end.isoformat(),
    }


def result(
    *,
    summary: str,
    rows: int,
    model_version: str | None = None,
    window: dict[str, str] | None = None,
    **data: Any,
) -> dict[str, Any]:
    return {
        "summary": summary,
        "rows": rows,
        "model_version": model_version,
        "window": window,
        **data,
    }


def error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"error": message, "code": code, "rows": 0, "summary": message, **extra}


def not_found(person_id: str) -> dict[str, Any]:
    return error("not_found", f"No person with id {person_id!r} exists in this data.")


def cap_rows(rows: list[Any]) -> tuple[list[Any], dict[str, Any]]:
    """Truncate to MAX_ROWS; the second value is merged into the payload."""
    if len(rows) <= MAX_ROWS:
        return rows, {"truncated": False}
    return rows[:MAX_ROWS], {
        "truncated": True,
        "total_rows": len(rows),
        "row_limit": MAX_ROWS,
    }


def parse_window(window: str) -> datetime | None:
    """`latest` -> None (repositories pick the newest); otherwise an ISO window_end."""
    if window.strip().lower() in ("", "latest"):
        return None
    parsed = datetime.fromisoformat(window)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def safe_tool[F: Callable[..., dict[str, Any]]](fn: F) -> F:
    """Turn any exception into a structured error payload.

    Wraps without changing the signature, so the Agents SDK still derives the
    tool schema from the original type hints and docstring.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return fn(*args, **kwargs)
        except ValueError as exc:
            return error("bad_argument", str(exc))
        except Exception as exc:
            log.exception("tool %s failed", fn.__name__)
            return error(
                "internal_error",
                "The data source failed to answer this request; it may be retried.",
                detail=type(exc).__name__,
            )

    return wrapper  # type: ignore[return-value]
