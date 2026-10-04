import pytest
from agents.models import _openai_shared
from pydantic import SecretStr

from agent.llm import LlmConnection

BASE = "https://example.test/v1/"


@pytest.fixture(autouse=True)
def restore_sdk_globals(monkeypatch):
    monkeypatch.setattr(_openai_shared, "_default_openai_client", None)
    monkeypatch.setattr(_openai_shared, "_use_responses_by_default", True)


def test_is_ready_follows_key_presence_without_network():
    assert LlmConnection(SecretStr("k"), BASE).is_ready() is True
    assert LlmConnection(None, BASE).is_ready() is False


def test_configure_points_the_sdk_at_the_provider_over_chat_completions():
    LlmConnection(SecretStr("k"), BASE).configure()
    client = _openai_shared.get_default_openai_client()
    assert client is not None
    assert str(client.base_url) == BASE
    assert _openai_shared.get_use_responses_by_default() is False


def test_configure_without_key_installs_no_client():
    LlmConnection(None, BASE).configure()
    assert _openai_shared.get_default_openai_client() is None
