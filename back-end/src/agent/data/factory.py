"""Composition point: the only module that knows both concrete sources."""

from agent.config import Settings
from agent.data.mock import MockSource
from agent.data.postgres import PostgresSource
from agent.domain.ports import WindowSource


def build_source(settings: Settings) -> WindowSource:
    if settings.effective_backend == "postgres":
        conninfo = settings.database_conninfo
        if conninfo is None:
            raise ValueError(
                "DATA_BACKEND=postgres requires DATABASE_URL or the PG* variables"
            )
        source = PostgresSource(
            conninfo, settings.dashboard_session_id, settings.statement_timeout_ms
        )
        source.check_read_only()
        return source
    return MockSource(seed=settings.mock_seed)
