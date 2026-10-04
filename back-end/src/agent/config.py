"""Runtime settings. The only module that reads environment variables."""

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    data_backend: Literal["mock", "postgres"] = "mock"
    database_url: SecretStr | None = None
    # Provider-neutral names; the old GEMINI_* variables still work. The default
    # endpoint is Gemini's OpenAI-compatible one, the provider in use today.
    llm_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("LLM_API_KEY", "GEMINI_API_KEY")
    )
    llm_base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta/openai/",
        validation_alias=AliasChoices("LLM_BASE_URL", "GEMINI_BASE_URL"),
    )

    # No default on purpose: a missing model must fail at startup, not at 3 a.m.
    agent_model: str
    guardrail_model: str | None = None

    # Browser origins allowed to call the API (a JSON list in the environment, or
    # ["*"] to open it up): the Vite dev server and the GitHub Pages deployment.
    allowed_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://pparkkila.github.io",
    ]

    max_turns: int = 6
    mock_seed: int = 7
    statement_timeout_ms: int = 5_000
    stats_ttl_s: float = 300.0  # how long Postgres cohort stats are cached

    session_db_path: Path = Path("var/sessions.sqlite")
    trace_path: Path = Path("var/trace.jsonl")

    @property
    def effective_guardrail_model(self) -> str:
        return self.guardrail_model or self.agent_model
