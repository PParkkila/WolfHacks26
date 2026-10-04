import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from agents import FunctionTool
from agents.tool_context import ToolContext
from fastapi.testclient import TestClient
from support import PID

from agent.api.app import create_app
from agent.auth import CLINICIAN, patient
from agent.bootstrap import Runtime, build_runtime
from agent.clock import ReplayClock
from agent.config import Settings
from agent.data.mock import MockSource
from agent.query import QueryService
from agent.store import WindowStore
from agent.tools.registry import build_tools


@pytest.fixture(scope="session")
def source() -> MockSource:
    return MockSource(seed=7)


@pytest.fixture(scope="session")
def store(source: MockSource) -> WindowStore:
    return WindowStore(source, refresh_s=1e9)


@pytest.fixture(scope="session")
def clock(store: WindowStore) -> ReplayClock:
    """Disabled replay: "now" is the newest window."""
    return ReplayClock(store.data_range, enabled=False)


@pytest.fixture(scope="session")
def clinician(store: WindowStore, clock: ReplayClock) -> QueryService:
    return QueryService(store, clock, CLINICIAN)


@pytest.fixture(scope="session")
def me(store: WindowStore, clock: ReplayClock) -> QueryService:
    return QueryService(store, clock, patient(PID))


def _tools(svc: QueryService) -> dict[str, FunctionTool]:
    return {tool.name: tool for tool in build_tools(svc)}


async def _invoke(tools: dict[str, FunctionTool], name: str, **args: Any) -> Any:
    """Call a tool the way the SDK does: JSON arguments in, tool result out."""
    raw = json.dumps(args)
    ctx = ToolContext(
        context=None, tool_name=name, tool_call_id="t", tool_arguments=raw
    )
    return await tools[name].on_invoke_tool(ctx, raw)


@pytest.fixture(scope="session")
def clinician_tools(clinician: QueryService) -> dict[str, FunctionTool]:
    return _tools(clinician)


@pytest.fixture(scope="session")
def patient_tools(me: QueryService) -> dict[str, FunctionTool]:
    return _tools(me)


@pytest.fixture
def invoke_clinician(clinician_tools) -> Callable[..., Any]:
    return lambda name, **args: _invoke(clinician_tools, name, **args)


@pytest.fixture
def invoke_patient(patient_tools) -> Callable[..., Any]:
    return lambda name, **args: _invoke(patient_tools, name, **args)


def make_settings(tmp: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "agent_model": "test-model",
        "data_backend": "mock",
        "replay_enabled": False,
        "session_db_path": tmp / "sessions.sqlite",
        "trace_path": tmp / "trace.jsonl",
        **overrides,
    }
    return Settings(_env_file=None, **values)  # pyright: ignore[reportCallIssue]


@pytest.fixture
def runtime(tmp_path: Path, source: MockSource) -> Runtime:
    return build_runtime(make_settings(tmp_path), source=source)


@pytest.fixture
def client(runtime: Runtime) -> TestClient:
    return TestClient(create_app(runtime))


def auth(client: TestClient, persona_id: str) -> dict[str, str]:
    token = client.post("/auth/login", json={"persona_id": persona_id}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def as_clinician(client: TestClient) -> dict[str, str]:
    return auth(client, CLINICIAN.user_id)


@pytest.fixture
def as_patient(client: TestClient) -> dict[str, str]:
    return auth(client, f"patient:{PID}")
