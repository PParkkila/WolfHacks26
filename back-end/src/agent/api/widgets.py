"""Widgets: refresh one built in chat, pin it, list pins, refresh one, unpin it."""

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from agent import widgets
from agent.api.deps import CurrentPrincipal, Queries, RuntimeDep
from agent.api.widget_store import PinnedWidget
from agent.query import QueryResult
from agent.widgets import WidgetSpec, WidgetStep

router = APIRouter(tags=["widgets"])


class WidgetData(PinnedWidget):
    result: QueryResult
    steps: list[WidgetStep]


class WidgetPreview(BaseModel):
    result: QueryResult
    steps: list[WidgetStep]


def _pinned(runtime: RuntimeDep, user_id: str, widget_id: str) -> PinnedWidget:
    pinned = runtime.widgets.get(user_id, widget_id)
    if pinned is None:
        raise HTTPException(404, "That widget isn't pinned.")
    return pinned


@router.get("/widgets")
def list_widgets(
    runtime: RuntimeDep, principal: CurrentPrincipal
) -> list[PinnedWidget]:
    return runtime.widgets.list(principal.user_id)


@router.post("/widgets/preview")
def preview_widget(spec: WidgetSpec, svc: Queries) -> WidgetPreview:
    """Rebuild a widget from its spec without pinning it (keeps chat widgets live)."""
    built = widgets.build(svc, spec)
    return WidgetPreview(result=built.result, steps=built.steps)


@router.post("/widgets", status_code=201)
def pin_widget(
    spec: WidgetSpec, runtime: RuntimeDep, principal: CurrentPrincipal, svc: Queries
) -> PinnedWidget:
    svc.query(spec.query)  # 403/400 before saving anything the caller can't see
    return runtime.widgets.add(principal.user_id, spec)


@router.get("/widgets/{widget_id}/data")
def widget_data(
    widget_id: str, runtime: RuntimeDep, principal: CurrentPrincipal, svc: Queries
) -> WidgetData:
    pinned = _pinned(runtime, principal.user_id, widget_id)
    built = widgets.build(svc, pinned.spec())
    return WidgetData(**pinned.model_dump(), result=built.result, steps=built.steps)


@router.delete("/widgets/{widget_id}", status_code=204)
def unpin_widget(
    widget_id: str, runtime: RuntimeDep, principal: CurrentPrincipal
) -> Response:
    if not runtime.widgets.delete(principal.user_id, widget_id):
        raise HTTPException(404, "That widget isn't pinned.")
    return Response(status_code=204)
