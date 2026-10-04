"""Read-only adapter for the dashboard rows Databricks publishes to Tiger.

Analytics windows live in `gold.dashboard_windows` as (session_id,
participant_key, window_end, payload jsonb, published_at). The view
`gold.dashboard_live` holds one row per participant with the newest sensor
readings (updated every second) merged into the newest window's payload. The
names below (TABLE, LIVE_TABLE, COLUMNS, PAYLOAD_KEYS) are the only code that
changes when the data team's schema drifts.

The model's risk index never leaves this module: it is turned into the Gluco
Score (100 - risk, higher is healthier) here. Provenance fields in the payload
(synthetic fraction, coverage, model version...) are not read.

One connection, opened read-only with a statement timeout, is reused because
the live view is polled every second. Only SELECTs are issued. Use a role with
SELECT only: `check_read_only` warns if it can write.
"""

import logging
import threading
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import DictRow, dict_row

from agent.domain.metrics import GLUCO_CHANGE, GLUCO_SCORE, LIVE_METRICS, WINDOW_METRICS
from agent.domain.models import LiveReading, Window
from agent.domain.ports import PublishedWindow

log = logging.getLogger(__name__)

TABLE = ("gold", "dashboard_windows")
LIVE_TABLE = ("gold", "dashboard_live")
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
    "sensor_time": "latest_sensor_time",
    "window_end": "window_end",
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
    values.update({name: _number(payload.get(name)) for name in WINDOW_METRICS})
    return Window(
        person_id=person_id,
        source_dataset=str(payload.get(PAYLOAD_KEYS["source_dataset"]) or "unknown"),
        window_start=window_end - timedelta(minutes=minutes or DEFAULT_WINDOW_MINUTES),
        window_end=window_end,
        values=values,
    )


def _time(value: Any) -> datetime | None:
    """A timestamp or ISO string as an aware datetime; anything else None."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def to_live(
    person_id: str, payload: dict[str, Any], sensor_published_at: datetime
) -> LiveReading:
    """One live row; the sensor time falls back to when it was published."""
    return LiveReading(
        person_id=person_id,
        sensor_time=_time(payload.get(PAYLOAD_KEYS["sensor_time"]))
        or sensor_published_at,
        analytics_window_end=_time(payload.get(PAYLOAD_KEYS["window_end"])),
        values={name: _number(payload.get(name)) for name in LIVE_METRICS},
    )


def _col(field: str) -> sql.Identifier:
    return sql.Identifier(COLUMNS[field])


def _table(name: tuple[str, str] = TABLE) -> sql.Identifier:
    return sql.Identifier(*name)


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
        self._lock = threading.Lock()
        self._conn: psycopg.Connection[DictRow] | None = None

    def _connect(self) -> psycopg.Connection[DictRow]:
        if self._conn is None or self._conn.closed:
            self._conn = psycopg.Connection[DictRow].connect(
                self._conninfo,
                autocommit=True,
                row_factory=dict_row,
                options=self._options,
            )
        return self._conn

    def _query(
        self, query: sql.SQL | sql.Composed, params: tuple[Any, ...] = ()
    ) -> list[DictRow]:
        """Run one SELECT on the shared connection, reconnecting once if it broke."""
        with self._lock:
            conn = self._connect()
            try:
                return conn.execute(query, params).fetchall()
            except (psycopg.OperationalError, psycopg.InterfaceError):
                if not conn.closed:  # e.g. a statement timeout: not worth a retry
                    raise
            log.warning("database connection lost; reconnecting")
            return self._connect().execute(query, params).fetchall()

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

    def fetch_live(self) -> list[LiveReading]:
        session = self.session_id()
        if session is None:
            return []
        query = sql.SQL(
            "SELECT {pid} AS person_id, {payload} AS payload, sensor_published_at "
            "FROM {t} WHERE {s} = %s ORDER BY {pid}"
        ).format(
            pid=_col("person_id"),
            payload=_col("payload"),
            t=_table(LIVE_TABLE),
            s=_col("session"),
        )
        return [
            to_live(row["person_id"], row["payload"], row["sensor_published_at"])
            for row in self._query(query, (session,))
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
