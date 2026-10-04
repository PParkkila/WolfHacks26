"""Conversation memory bound to the signed-in user.

The SDK's SQLite session stores the turns under `<user_id>:<session_id>`, so one
user can never continue or read another's thread. A small index table in the
same file lists each user's threads for the UI.
"""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agents import Session, SQLiteSession
from pydantic import BaseModel

TITLE_LENGTH = 80


class ChatThread(BaseModel):
    session_id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ChatMessage(BaseModel):
    role: str
    text: str


def _text(content: Any) -> str:
    """The plain text of a message item's content (a string or content parts)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    return ""


def to_messages(items: list[Any]) -> list[ChatMessage]:
    """User and assistant messages from session items; tool calls are skipped."""
    messages: list[ChatMessage] = []
    for item in items:
        if not isinstance(item, dict) or item.get("role") not in ("user", "assistant"):
            continue
        if item.get("type", "message") != "message":
            continue
        text = _text(item.get("content"))
        if text:
            messages.append(ChatMessage(role=item["role"], text=text))
    return messages


class ChatSessions:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._path = db_path
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS chat_index ("
                "user_id TEXT NOT NULL, session_id TEXT NOT NULL, title TEXT NOT NULL, "
                "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
                "PRIMARY KEY (user_id, session_id))"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    @staticmethod
    def key(user_id: str, session_id: str) -> str:
        return f"{user_id}:{session_id}"

    def open(self, user_id: str, session_id: str) -> Session:
        return SQLiteSession(self.key(user_id, session_id), self._path)

    def touch(self, user_id: str, session_id: str, message: str) -> None:
        """Record activity; the first message becomes the thread's title."""
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO chat_index VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT (user_id, session_id) DO UPDATE SET updated_at = ?",
                (user_id, session_id, message[:TITLE_LENGTH], now, now, now),
            )

    def threads(self, user_id: str) -> list[ChatThread]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT session_id, title, created_at, updated_at FROM chat_index "
                "WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        return [
            ChatThread(session_id=r[0], title=r[1], created_at=r[2], updated_at=r[3])
            for r in rows
        ]

    def owns(self, user_id: str, session_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM chat_index WHERE user_id = ? AND session_id = ?",
                (user_id, session_id),
            ).fetchone()
        return row is not None

    async def messages(self, user_id: str, session_id: str) -> list[ChatMessage]:
        items = await self.open(user_id, session_id).get_items()
        return to_messages(list(items))
