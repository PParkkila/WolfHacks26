"""Composition root: wires settings, data, tools, agent and chat service."""

from dataclasses import dataclass

from agents import (
    FunctionTool,
    set_default_openai_api,
    set_default_openai_client,
    set_tracing_disabled,
)
from openai import AsyncOpenAI

from agent.analysis.quality import ReliabilityPolicy
from agent.api.chat_service import ChatService
from agent.api.sessions import sqlite_session_factory
from agent.config import Settings
from agent.data.factory import build_repositories
from agent.domain.ports import Repositories
from agent.factory import build_agent
from agent.guardrails import build_input_guardrails
from agent.observability.trace import JsonlTracer
from agent.tools.base import ToolDeps
from agent.tools.registry import build_tools


@dataclass(frozen=True)
class Runtime:
    settings: Settings
    repos: Repositories
    tools: list[FunctionTool]
    chat: ChatService


def configure_sdk(settings: Settings) -> None:
    # SDK tracing uploads tool outputs (person-level health data) to OpenAI.
    set_tracing_disabled(True)
    # Gemini's OpenAI-compat layer speaks Chat Completions, not Responses.
    set_default_openai_api("chat_completions")
    if settings.gemini_api_key is not None:
        client = AsyncOpenAI(
            api_key=settings.gemini_api_key.get_secret_value(),
            base_url=settings.gemini_base_url,
        )
        set_default_openai_client(client, use_for_tracing=False)


def build_runtime(settings: Settings | None = None) -> Runtime:
    settings = settings or Settings()  # pyright: ignore[reportCallIssue]
    configure_sdk(settings)

    repos = build_repositories(settings)
    tools = build_tools(ToolDeps(repos=repos, policy=ReliabilityPolicy()))
    agent = build_agent(
        model=settings.agent_model,
        tools=tools,
        input_guardrails=build_input_guardrails(settings.effective_guardrail_model),
    )
    chat = ChatService(
        agent=agent,
        sessions=sqlite_session_factory(settings.session_db_path),
        tracer=JsonlTracer(settings.trace_path),
        max_turns=settings.max_turns,
    )
    return Runtime(settings=settings, repos=repos, tools=tools, chat=chat)
