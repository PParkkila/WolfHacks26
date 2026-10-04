"""The single list of tool groups. Adding a tool group is one line here."""

from collections.abc import Callable

from agents import FunctionTool

from agent.tools import cohort, quality, risk
from agent.tools.base import ToolDeps

ToolGroup = Callable[[ToolDeps], list[FunctionTool]]

TOOL_GROUPS: tuple[ToolGroup, ...] = (risk.build, cohort.build, quality.build)


def build_tools(deps: ToolDeps) -> list[FunctionTool]:
    return [tool for group in TOOL_GROUPS for tool in group(deps)]
