"""Composition point: the only module that knows both concrete backends."""

from agent.config import Settings
from agent.data.mock import MockBackend
from agent.data.postgres import PostgresBackend
from agent.domain.ports import Repositories


def build_repositories(settings: Settings) -> Repositories:
    if settings.data_backend == "postgres":
        if settings.database_url is None:
            raise ValueError("DATA_BACKEND=postgres requires DATABASE_URL")
        backend = PostgresBackend(
            settings.database_url.get_secret_value(), settings.statement_timeout_ms
        )
    else:
        backend = MockBackend(seed=settings.mock_seed)
    return Repositories(risk=backend, features=backend, stats=backend, health=backend)
