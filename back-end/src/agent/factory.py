"""Builds the role's Agent. Knows the SDK, but nothing about Postgres."""

from datetime import datetime
from pathlib import Path

from agents import Agent, FunctionTool, InputGuardrail

from agent.auth import Principal
from agent.domain.metrics import METRICS

PROMPTS = Path(__file__).parent / "prompts"


def metrics_table() -> str:
    return "\n".join(
        f"- `{name}` ({spec.label}, {spec.unit}): {spec.description}"
        for name, spec in METRICS.items()
    )


def instructions(principal: Principal, now: datetime | None) -> str:
    template = (PROMPTS / f"{principal.role}.md").read_text(encoding="utf-8")
    return (
        template.replace("{{METRICS}}", metrics_table())
        .replace("{{USER_NAME}}", principal.display_name)
        .replace("{{NOW}}", now.strftime("%Y-%m-%d %H:%M UTC") if now else "unknown")
    )


def build_agent(
    *,
    principal: Principal,
    now: datetime | None,
    model: str,
    tools: list[FunctionTool],
    input_guardrails: list[InputGuardrail],
) -> Agent:
    return Agent(
        name=f"{principal.role}_assistant",
        instructions=instructions(principal, now),
        model=model,
        tools=list(tools),  # the SDK wants list[Tool]; ours is list[FunctionTool]
        input_guardrails=list(input_guardrails),
    )
