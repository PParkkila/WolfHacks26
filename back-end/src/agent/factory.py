"""Builds the Agent. Knows the SDK, but nothing about Postgres or prediabetes."""

from pathlib import Path

from agents import Agent, FunctionTool, InputGuardrail

PROMPT_PATH = Path(__file__).parent / "prompts" / "system.md"


def build_agent(
    *,
    model: str,
    tools: list[FunctionTool],
    input_guardrails: list[InputGuardrail],
) -> Agent:
    return Agent(
        name="risk_triage",
        instructions=PROMPT_PATH.read_text(encoding="utf-8"),
        model=model,
        tools=list(tools),  # the SDK wants list[Tool]; ours is list[FunctionTool]
        input_guardrails=list(input_guardrails),
    )
