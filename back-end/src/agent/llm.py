"""The LLM connection: the one module that knows which provider is behind the SDK.

Today that is Gemini through its OpenAI-compatible endpoint. Callers configure it
once at startup and ask `is_ready()`; nothing else names the provider. With a
single provider live this is a module, not a seam; add an adapter only if a
second provider ever runs alongside it.
"""

from collections.abc import AsyncIterator
from functools import cached_property
from typing import Any

from agents import (
    set_default_openai_api,
    set_default_openai_client,
    set_tracing_disabled,
)
from openai import AsyncOpenAI
from openai.resources.chat import AsyncChat
from openai.resources.chat.completions import AsyncCompletions
from openai.types.chat import ChatCompletionChunk
from pydantic import SecretStr

from agent.config import Settings


class ToolCallIndexFix:
    """Gives every streamed tool call its own index.

    Gemini's OpenAI-compatible stream sends parallel tool calls under the same
    index; the SDK groups deltas by index and would merge two calls into one with
    unparseable arguments ('{...}{...}'), which Gemini then rejects. A delta that
    carries a new call id starts a new index; deltas without an id continue the
    current call.
    """

    def __init__(self, stream: Any) -> None:
        self._stream = stream
        self._indexes: dict[str, int] = {}
        self._current: int | None = None

    def fix(self, chunk: ChatCompletionChunk) -> ChatCompletionChunk:
        for choice in chunk.choices:
            for call in choice.delta.tool_calls or []:
                if call.id:
                    self._current = self._indexes.setdefault(
                        call.id, len(self._indexes)
                    )
                if self._current is not None:
                    call.index = self._current
        return chunk

    def __aiter__(self) -> AsyncIterator[ChatCompletionChunk]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[ChatCompletionChunk]:
        async for chunk in self._stream:
            yield self.fix(chunk)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)


class _Completions(AsyncCompletions):
    async def create(self, **kwargs: Any) -> Any:  # type: ignore[override]
        response = await super().create(**kwargs)
        return ToolCallIndexFix(response) if kwargs.get("stream") is True else response


class _Chat(AsyncChat):
    @cached_property
    def completions(self) -> AsyncCompletions:  # type: ignore[override]
        return _Completions(self._client)


class GeminiCompatClient(AsyncOpenAI):
    """AsyncOpenAI with the tool-call index fix applied to streamed completions."""

    @cached_property
    def chat(self) -> AsyncChat:  # type: ignore[override]
        return _Chat(self)


class LlmConnection:
    def __init__(self, api_key: SecretStr | None, base_url: str) -> None:
        self._api_key = api_key
        self._base_url = base_url

    @classmethod
    def from_settings(cls, settings: Settings) -> "LlmConnection":
        return cls(settings.llm_api_key, settings.llm_base_url)

    def is_ready(self) -> bool:
        """True when a key is configured; never contacts the provider."""
        return self._api_key is not None

    def configure(self) -> None:
        """Point the Agents SDK at the provider. Call once, before any run."""
        # SDK tracing uploads tool outputs (person-level health data) to OpenAI.
        set_tracing_disabled(True)
        # The OpenAI-compat layer speaks Chat Completions, not Responses.
        set_default_openai_api("chat_completions")
        if self._api_key is not None:
            client = GeminiCompatClient(
                api_key=self._api_key.get_secret_value(), base_url=self._base_url
            )
            set_default_openai_client(client, use_for_tracing=False)
