"""Pinned widgets, per user, in the same SQLite file as the chat sessions.

Only the spec is stored, never data: a pinned widget is rebuilt (and checked
again) every time it is shown, so it follows the clock and the caller's scope.
"""

import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from agent.query import QuerySpec
from agent.widgets import WidgetKind, WidgetSpec


class PinnedWidget(BaseModel):
    id: str
    title: str
    kind: WidgetKind
    query: QuerySpec
    created_at: datetime

    def spec(self) -> WidgetSpec:
        return WidgetSpec(title=self.title, kind=self.kind, query=self.query)


class WidgetStore:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._path = db_path
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS pinned_widgets ("
                "id TEXT PRIMARY KEY, user_id TEXT NOT NULL, title TEXT NOT NULL, "
                "kind TEXT NOT NULL, query_json TEXT NOT NULL, "
                "created_at TEXT NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    @staticmethod
    def _row(row: tuple[str, str, str, str, str]) -> PinnedWidget:
        return PinnedWidget(
            id=row[0],
            title=row[1],
            kind=row[2],  # pyright: ignore[reportArgumentType]
            query=QuerySpec.model_validate_json(row[3]),
            created_at=datetime.fromisoformat(row[4]),
        )

    def list(self, user_id: str) -> list[PinnedWidget]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, title, kind, query_json, created_at FROM pinned_widgets "
                "WHERE user_id = ? ORDER BY created_at",
                (user_id,),
            ).fetchall()
        return [self._row(r) for r in rows]

    def get(self, user_id: str, widget_id: str) -> PinnedWidget | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, title, kind, query_json, created_at FROM pinned_widgets "
                "WHERE user_id = ? AND id = ?",
                (user_id, widget_id),
            ).fetchone()
        return self._row(row) if row else None

    def add(self, user_id: str, spec: WidgetSpec) -> PinnedWidget:
        pinned = PinnedWidget(
            id=uuid.uuid4().hex[:12],
            title=spec.title,
            kind=spec.kind,
            query=spec.query,
            created_at=datetime.now(UTC),
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO pinned_widgets VALUES (?, ?, ?, ?, ?, ?)",
                (
                    pinned.id,
                    user_id,
                    pinned.title,
                    pinned.kind,
                    pinned.query.model_dump_json(exclude_none=True),
                    pinned.created_at.isoformat(),
                ),
            )
        return pinned

    def delete(self, user_id: str, widget_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM pinned_widgets WHERE user_id = ? AND id = ?",
                (user_id, widget_id),
            )
        return cursor.rowcount > 0
