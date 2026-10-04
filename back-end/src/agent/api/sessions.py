"""Conversation memory: the SDK's SQLite session, keyed by session_id."""

from collections.abc import Callable
from pathlib import Path

from agents import Session, SQLiteSession

SessionFactory = Callable[[str], Session]


def sqlite_session_factory(db_path: Path) -> SessionFactory:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return lambda session_id: SQLiteSession(session_id, db_path)
