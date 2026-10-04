"""The LLM connection: the one module that knows which provider is behind the SDK.

Today that is Gemini through its OpenAI-compatible endpoint. Callers configure it
once at startup and ask `is_ready()`; nothing else names the provider. With a
single provider live this is a module, not a seam; add an adapter only if a
second provider ever runs alongside it.
"""

from agents import (
    set_default_openai_api,
    set_default_openai_client,
    set_tracing_disabled,
)
from openai import AsyncOpenAI
from pydantic import SecretStr

from agent.config import Settings


class LlmConnection:
    def __init__(self, api_key: SecretStr | None, base_url: str) -> None:
        self._api_key = api_key
        self._base_url = base_url

    @classmethod
    def from_settings(cls, settings: Settings) -> "LlmConnection":
        return cls(settings.gemini_api_key, settings.gemini_base_url)

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
            client = AsyncOpenAI(
                api_key=self._api_key.get_secret_value(), base_url=self._base_url
            )
            set_default_openai_client(client, use_for_tracing=False)
