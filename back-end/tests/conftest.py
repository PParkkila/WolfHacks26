import json
from collections.abc import Callable
from typing import Any

import pytest
from agents import FunctionTool
from agents.tool_context import ToolContext

from agent.analysis.quality import ReliabilityPolicy
from agent.data.mock import MockBackend
from agent.domain.ports import Repositories
from agent.tools.base import ToolDeps
from agent.tools.registry import build_tools


@pytest.fixture(scope="session")
def backend() -> MockBackend:
    return MockBackend(seed=7)


@pytest.fixture(scope="session")
def repos(backend: MockBackend) -> Repositories:
    return Repositories(risk=backend, features=backend, stats=backend, health=backend)


@pytest.fixture(scope="session")
def tools(repos: Repositories) -> dict[str, FunctionTool]:
    built = build_tools(ToolDeps.from_repos(repos, ReliabilityPolicy()))
    return {tool.name: tool for tool in built}


@pytest.fixture
def invoke(tools: dict[str, FunctionTool]) -> Callable[..., Any]:
    """Call a tool the way the SDK does: JSON arguments in, tool result out."""

    async def _invoke(name: str, **args: Any) -> dict[str, Any]:
        raw = json.dumps(args)
        ctx = ToolContext(
            context=None, tool_name=name, tool_call_id="t", tool_arguments=raw
        )
        return await tools[name].on_invoke_tool(ctx, raw)

    return _invoke
