"""Builds the Agent. Knows the SDK, but nothing about Postgres or prediabetes."""

from pathlib import Path

from agents import Agent, FunctionTool, InputGuardrail

PROMPT_PATH = Path(__file__).parent / "prompts" / "system.md"


def load_instructions(path: Path = PROMPT_PATH) -> str:
    return path.read_text(encoding="utf-8")


def build_agent(
    *,
    model: str,
    tools: list[FunctionTool],
    input_guardrails: list[InputGuardrail],
    instructions: str | None = None,
) -> Agent:
    return Agent(
        name="risk_triage",
        instructions=instructions or load_instructions(),
        model=model,
        tools=list(tools),
        input_guardrails=list(input_guardrails),
    )
