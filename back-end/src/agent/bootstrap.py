"""Composition root: wires settings, data, tools, agent and chat service."""

from dataclasses import dataclass

from agents import FunctionTool

from agent.analysis.quality import ReliabilityPolicy
from agent.api.chat_service import ChatService
from agent.api.sessions import sqlite_session_factory
from agent.config import Settings
from agent.data.factory import build_repositories
from agent.domain.ports import Repositories
from agent.factory import build_agent
from agent.guardrails import build_input_guardrails
from agent.llm import LlmConnection
from agent.observability.trace import JsonlTracer
from agent.tools.base import ToolDeps
from agent.tools.registry import build_tools


@dataclass(frozen=True)
class Runtime:
    settings: Settings
    llm: LlmConnection
    repos: Repositories
    tools: list[FunctionTool]
    chat: ChatService


def build_runtime(settings: Settings | None = None) -> Runtime:
    settings = settings or Settings()  # pyright: ignore[reportCallIssue]
    llm = LlmConnection.from_settings(settings)
    llm.configure()

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
    return Runtime(settings=settings, llm=llm, repos=repos, tools=tools, chat=chat)
