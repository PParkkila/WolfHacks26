"""Runtime settings. The only module that reads environment variables."""

from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    data_backend: Literal["mock", "postgres"] = "mock"
    database_url: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"

    # No default on purpose: a missing model must fail at startup, not at 3 a.m.
    agent_model: str
    guardrail_model: str | None = None

    max_turns: int = 6
    mock_seed: int = 7
    statement_timeout_ms: int = 5_000

    session_db_path: Path = Path("var/sessions.sqlite")
    trace_path: Path = Path("var/trace.jsonl")

    @property
    def effective_guardrail_model(self) -> str:
        return self.guardrail_model or self.agent_model
