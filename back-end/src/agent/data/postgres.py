"""Read-only adapter for the dashboard rows Databricks publishes to Tiger.

Rows live in `gold.dashboard_windows` as (session_id, participant_key,
window_end, payload jsonb, published_at). The names below (TABLE, COLUMNS,
PAYLOAD_KEYS) are the only code that changes when the data team's schema drifts.

The model's risk index never leaves this module: it is turned into the Gluco
Score (100 - risk, higher is healthier) here. Provenance fields in the payload
(synthetic fraction, coverage, model version...) are not read.

Every connection is opened read-only with a statement timeout and only SELECTs
are issued. Use a role with SELECT only: `check_read_only` warns if it can write.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import DictRow, dict_row

from agent.domain.metrics import GLUCO_CHANGE, GLUCO_SCORE, SENSOR_METRICS
from agent.domain.models import Window
from agent.domain.ports import PublishedWindow

log = logging.getLogger(__name__)

TABLE = ("gold", "dashboard_windows")
# domain field -> column
COLUMNS = {
    "session": "session_id",
    "person_id": "participant_key",
    "window_end": "window_end",
    "payload": "payload",
    "published_at": "published_at",
}
# domain field -> payload key. Sensor metrics use their own names as keys.
PAYLOAD_KEYS = {
    "risk_index": "wearable_risk_indicator",
    "risk_change_24h": "risk_change_24h_points",
    "window_minutes": "window_minutes",
    "source_dataset": "source_dataset",
}
RISK_MAX = 100.0
DEFAULT_WINDOW_MINUTES = 1440


def _number(value: Any) -> float | None:
    """Numbers (or numeric strings) as float; anything else, booleans included, None."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float | Decimal):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def to_window(person_id: str, window_end: datetime, payload: dict[str, Any]) -> Window:
    """One published row as a domain Window, with the risk index inverted."""
    risk = _number(payload.get(PAYLOAD_KEYS["risk_index"]))
    risk_change = _number(payload.get(PAYLOAD_KEYS["risk_change_24h"]))
    minutes = _number(payload.get(PAYLOAD_KEYS["window_minutes"]))
    values: dict[str, float | None] = {
        GLUCO_SCORE: None if risk is None else RISK_MAX - risk,
        GLUCO_CHANGE: None if risk_change is None else -risk_change,
    }
    values.update({name: _number(payload.get(name)) for name in SENSOR_METRICS})
    return Window(
        person_id=person_id,
        source_dataset=str(payload.get(PAYLOAD_KEYS["source_dataset"]) or "unknown"),
        window_start=window_end - timedelta(minutes=minutes or DEFAULT_WINDOW_MINUTES),
        window_end=window_end,
        values=values,
    )


def _col(field: str) -> sql.Identifier:
    return sql.Identifier(COLUMNS[field])


def _table() -> sql.Identifier:
    return sql.Identifier(*TABLE)


class PostgresSource:
    """Implements WindowSource over Tiger."""

    def __init__(
        self,
        conninfo: str,
        session_id: str | None = None,
        statement_timeout_ms: int = 5_000,
    ) -> None:
        self._conninfo = conninfo
        self._session_id = session_id
        self._options = (
            "-c default_transaction_read_only=on "
            f"-c statement_timeout={statement_timeout_ms}"
        )

    def _query(
        self, query: sql.SQL | sql.Composed, params: tuple[Any, ...] = ()
    ) -> list[DictRow]:
        with psycopg.Connection[DictRow].connect(
            self._conninfo,
            autocommit=True,
            row_factory=dict_row,
            options=self._options,
        ) as conn:
            return conn.execute(query, params).fetchall()

    def session_id(self) -> str | None:
        """The configured session, else the most recently published one."""
        if self._session_id is None:
            rows = self._query(
                sql.SQL(
                    "SELECT {s} AS session FROM {t} ORDER BY {p} DESC LIMIT 1"
                ).format(s=_col("session"), t=_table(), p=_col("published_at"))
            )
            if rows:
                self._session_id = rows[0]["session"]
                log.info("reading dashboard session %s", self._session_id)
        return self._session_id

    def fetch_since(self, published_after: datetime | None) -> list[PublishedWindow]:
        session = self.session_id()
        if session is None:
            return []
        query = sql.SQL(
            "SELECT {pid} AS person_id, {end} AS window_end, {payload} AS payload, "
            "{pub} AS published_at FROM {t} WHERE {s} = %s"
        ).format(
            pid=_col("person_id"),
            end=_col("window_end"),
            payload=_col("payload"),
            pub=_col("published_at"),
            t=_table(),
            s=_col("session"),
        )
        params: tuple[Any, ...] = (session,)
        if published_after is not None:
            # >= rather than >: rows sharing the last timestamp may be new.
            query += sql.SQL(" AND {pub} >= %s").format(pub=_col("published_at"))
            params += (published_after,)
        query += sql.SQL(" ORDER BY {pub}").format(pub=_col("published_at"))
        return [
            PublishedWindow(
                window=to_window(row["person_id"], row["window_end"], row["payload"]),
                published_at=row["published_at"],
            )
            for row in self._query(query, params)
        ]

    def ping(self) -> bool:
        try:
            self._query(sql.SQL("SELECT 1"))
        except psycopg.Error:
            log.exception("database ping failed")
            return False
        return True

    def can_write(self) -> bool:
        rows = self._query(
            sql.SQL(
                "SELECT has_table_privilege(%s, 'INSERT') "
                "OR has_table_privilege(%s, 'UPDATE') "
                "OR has_table_privilege(%s, 'DELETE') AS writable"
            ),
            (".".join(TABLE),) * 3,
        )
        return bool(rows and rows[0]["writable"])

    def check_read_only(self) -> None:
        """Warn, never fail, if the role could write (sessions are read-only anyway)."""
        try:
            writable = self.can_write()
        except psycopg.Error:
            log.warning(
                "could not verify the database role is read-only", exc_info=True
            )
            return
        if writable:
            log.warning(
                "database role can write to %s; use a SELECT-only role", ".".join(TABLE)
            )
