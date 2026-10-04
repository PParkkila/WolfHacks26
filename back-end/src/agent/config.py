"""Runtime settings. The only module that reads environment variables."""

from datetime import datetime
from pathlib import Path
from typing import Literal

from psycopg.conninfo import make_conninfo
from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_AUTH_SECRET = "dev-only-pulsecast-secret-change-me"  # noqa: S105


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # None picks postgres when a database is configured, else the mock.
    data_backend: Literal["mock", "postgres"] | None = None
    database_url: SecretStr | None = None
    # libpq-style variables, used when DATABASE_URL is unset. pydantic-settings
    # reads .env without exporting it, so libpq would not see them on its own.
    pghost: str | None = None
    pgport: int | None = None
    pgdatabase: str | None = None
    pguser: str | None = None
    pgpassword: SecretStr | None = None
    pgsslmode: str | None = None
    # Which published replay to read; None means the most recently published.
    dashboard_session_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DASHBOARD_SESSION_ID", "DEMO_SESSION_ID"),
    )

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

    # Signs the demo login tokens. The default is for local development only.
    auth_secret: SecretStr = SecretStr(DEV_AUTH_SECRET)
    token_ttl_hours: float = 24.0

    # The replay clock walks through the published data so it looks live.
    replay_enabled: bool = True
    replay_start: datetime | None = None  # None: one day after the first window
    replay_seconds_per_hour: float = 5.0

    # Browser origins allowed to call the API (a JSON list in the environment, or
    # ["*"] to open it up): the Vite and Next.js dev servers and the GitHub Pages
    # deployment.
    allowed_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://pparkkila.github.io",
    ]

    max_turns: int = 8
    mock_seed: int = 7
    statement_timeout_ms: int = 5_000
    store_refresh_s: float = 10.0  # how often new published rows are picked up

    session_db_path: Path = Path("var/sessions.sqlite")
    trace_path: Path = Path("var/trace.jsonl")

    @property
    def effective_guardrail_model(self) -> str:
        return self.guardrail_model or self.agent_model

    @property
    def database_conninfo(self) -> str | None:
        if self.database_url is not None:
            return self.database_url.get_secret_value()
        if self.pghost is None:
            return None
        params = {
            "host": self.pghost,
            "port": self.pgport,
            "dbname": self.pgdatabase,
            "user": self.pguser,
            "password": self.pgpassword.get_secret_value() if self.pgpassword else None,
            "sslmode": self.pgsslmode,
        }
        return make_conninfo(**{k: v for k, v in params.items() if v is not None})

    @property
    def effective_backend(self) -> Literal["mock", "postgres"]:
        if self.data_backend is not None:
            return self.data_backend
        return "postgres" if self.database_conninfo else "mock"
