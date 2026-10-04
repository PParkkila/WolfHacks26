"""Dashboard endpoints: thin shells over QueryService, scoped by the token.

Most widgets need only `POST /query`; the rest are conveniences for the common
cards. Every response is limited to what the caller may see and to windows that
end at or before the replay clock's "now"; live sensor readings ride on the
newest window once the clock has reached it.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated

import anyio
from fastapi import APIRouter, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

from agent.analysis.query import Order
from agent.api.deps import CurrentPrincipal, Queries, RuntimeDep
from agent.api.schemas import ClockCommand, ExplainResponse
from agent.clock import ClockState
from agent.domain.metrics import GLUCO_SCORE
from agent.query import (
    Catalog,
    CohortComparison,
    CohortOverview,
    ParticipantRow,
    QueryResult,
    QuerySpec,
)

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

router = APIRouter(tags=["dashboard"])


@router.get("/catalog")
def catalog(svc: Queries) -> Catalog:
    return svc.catalog()


@router.post("/query")
def run_query(spec: QuerySpec, svc: Queries) -> QueryResult:
    return svc.query(spec)


@router.get("/participants")
def participants(
    svc: Queries, sort_by: str = GLUCO_SCORE, order: Order = "asc"
) -> list[ParticipantRow]:
    return svc.participants(sort_by, order)


@router.get("/participants/{person_id}")
def participant(person_id: str, svc: Queries) -> ParticipantRow:
    return svc.participant(svc.resolve(person_id))


@router.get("/participants/{person_id}/explain")
def explain(
    person_id: str,
    svc: Queries,
    hours: Annotated[float, Query(gt=0, le=168)] = 24,
) -> ExplainResponse:
    pid = svc.resolve(person_id)
    return ExplainResponse(
        change=svc.explain_change(pid, hours),
        cohort_position=svc.cohort_position(pid) if svc.is_clinician else None,
    )


@router.get("/participants/{person_id}/compare")
def compare(person_id: str, metric: str, svc: Queries) -> CohortComparison:
    return svc.compare_to_cohort(svc.resolve(person_id), metric)


@router.get("/cohort")
def cohort(svc: Queries) -> CohortOverview:
    return svc.cohort_overview()


@router.get("/clock")
def clock_state(runtime: RuntimeDep, _: CurrentPrincipal) -> ClockState:
    return runtime.clock.state()


@router.post("/clock")
def control_clock(
    command: ClockCommand, runtime: RuntimeDep, _: CurrentPrincipal
) -> ClockState:
    clock = runtime.clock
    if command.action == "play":
        clock.play()
    elif command.action == "pause":
        clock.pause()
    elif command.action == "speed":
        if command.seconds_per_hour is None:
            raise HTTPException(422, "speed needs seconds_per_hour")
        clock.set_speed(command.seconds_per_hour)
    else:
        if command.to is None:
            raise HTTPException(422, "seek needs to")
        clock.seek(command.to)
    return clock.state()


@router.get("/stream")
async def stream(
    request: Request,
    runtime: RuntimeDep,
    svc: Queries,
    interval: Annotated[float, Query(ge=0.2, le=10)] = 1.0,
) -> EventSourceResponse:
    """Push a `tick` whenever the clock moves or the live readings change.

    Each tick carries the newly visible windows and everyone visible's live
    readings. `reset` is true when the clock jumped backwards (a seek): the UI
    should re-run its queries rather than append.
    """
    clock = runtime.clock

    async def ticks() -> AsyncIterator[dict[str, str]]:
        last = None
        last_key: tuple[object, ...] | None = None
        while not await request.is_disconnected():
            state = await anyio.to_thread.run_sync(clock.state)
            live = await anyio.to_thread.run_sync(svc.live_readings)
            live_at = max((r.sensor_time for r in live), default=None)
            key = (state.now, state.playing, state.seconds_per_hour, live_at)
            if key != last_key:
                now = state.now
                reset = last is not None and now is not None and now < last
                fresh = (
                    await anyio.to_thread.run_sync(svc.windows_between, last, now)
                    if last is not None and now is not None and now > last
                    else []
                )
                payload = {
                    "type": "tick",
                    "clock": state.model_dump(mode="json"),
                    "reset": reset,
                    "new_windows": [w.model_dump(mode="json") for w in fresh],
                    "live_at": live_at.isoformat() if live_at else None,
                    "live": [r.model_dump(mode="json") for r in live],
                }
                yield {"event": "tick", "data": json.dumps(payload)}
                last, last_key = now, key
            await asyncio.sleep(interval)

    return EventSourceResponse(ticks(), headers=SSE_HEADERS, ping=15)
