"""Read-only Postgres adapter for Contract A (TigerData).

Table and column names live in the mappings below (TABLES, RISK_COLUMNS,
FEATURE_COLUMNS, STAT_COLUMNS); when the data team's schema drifts, that is the
only code that changes. Every connection is opened read-only with a statement
timeout, and only SELECTs are ever issued. Run it with a role that has SELECT
only: `check_read_only` warns at startup if the role could write.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import DictRow, dict_row

from agent.analysis.stats import compute_feature_stats
from agent.data.cache import StatsCache
from agent.domain.models import (
    CohortGroup,
    FeatureStat,
    FeatureVector,
    RiskScore,
    WindowKey,
)
from agent.domain.ports import FEATURE_WINDOW_TOLERANCE

log = logging.getLogger(__name__)

TABLES = {
    "risk": "risk_scores",
    "features": "person_features",
    "stats": "cohort_stats",
}

# domain field -> database column
RISK_COLUMNS = {
    "person_id": "person_id",
    "window_start": "window_start",
    "window_end": "window_end",
    "score": "score",
    "label": "label",
    "confidence": "confidence",
    "wear_time_hours": "wear_time_hours",
    "missing_signal_pct": "missing_signal_pct",
    "model_version": "model_version",
}
STAT_COLUMNS = {
    "feature_name": "feature_name",
    "mean": "mean",
    "stddev": "stddev",
    "p50": "p50",
}
# person_features has one column per feature, so only the columns that identify
# the row are mapped. Every other numeric (non-boolean) column is a feature value,
# which means an extra numeric column added to the table must be named here.
FEATURE_COLUMNS = {
    "person_id": "person_id",
    "window_start": "window_start",
    "window_end": "window_end",
}
FEATURE_META_COLUMNS = frozenset(FEATURE_COLUMNS.values())


def _select(columns: dict[str, str]) -> sql.Composed:
    return sql.SQL(", ").join(
        sql.SQL("{} AS {}").format(sql.Identifier(column), sql.Identifier(field))
        for field, column in columns.items()
    )


def _table(key: str) -> sql.Identifier:
    return sql.Identifier(TABLES[key])


def _is_number(value: Any) -> bool:
    """True for ints, floats and decimals; booleans are flags, not measurements."""
    return isinstance(value, int | float | Decimal) and not isinstance(value, bool)


def _to_vector(row: dict[str, Any]) -> FeatureVector:
    values = {
        name: None if value is None else float(value)
        for name, value in row.items()
        if name not in FEATURE_META_COLUMNS and (value is None or _is_number(value))
    }
    return FeatureVector(
        person_id=row[FEATURE_COLUMNS["person_id"]],
        window_end=row[FEATURE_COLUMNS["window_end"]],
        values=values,
    )


def _for_person(
    *,
    select: sql.Composable,
    table: sql.Identifier,
    person_col: str,
    end_col: str,
    person_id: str,
    window_end: datetime | None,
    tolerance: timedelta = timedelta(0),
) -> tuple[sql.Composed, tuple[Any, ...]]:
    """One row for a person: the latest, or the window ending at `window_end`.

    With a non-zero `tolerance` the window matches within it and the closest wins.
    """
    person, end = sql.Identifier(person_col), sql.Identifier(end_col)
    query = sql.SQL("SELECT {select} FROM {table} WHERE {person} = %s").format(
        select=select, table=table, person=person
    )
    params: tuple[Any, ...] = (person_id,)
    order = sql.SQL("{end} DESC").format(end=end)
    if window_end is not None and tolerance:
        query += sql.SQL(" AND {end} BETWEEN %s AND %s").format(end=end)
        params += (window_end - tolerance, window_end + tolerance)
        order = sql.SQL("abs(extract(epoch FROM {end} - %s::timestamptz))").format(
            end=end
        )
        params += (window_end,)
    elif window_end is not None:
        query += sql.SQL(" AND {end} = %s").format(end=end)
        params += (window_end,)
    query += sql.SQL(" ORDER BY ") + order + sql.SQL(" LIMIT 1")
    return query, params


class PostgresBackend:
    """Implements every read port (risk, features, stats, health)."""

    def __init__(
        self,
        database_url: str,
        statement_timeout_ms: int = 5_000,
        stats_ttl_s: float | None = 300.0,
    ) -> None:
        self._url = database_url
        self._options = (
            "-c default_transaction_read_only=on "
            f"-c statement_timeout={statement_timeout_ms}"
        )
        self._stats = StatsCache(self._load_stats, stats_ttl_s)

    def _query(
        self, query: sql.SQL | sql.Composed, params: tuple[Any, ...] = ()
    ) -> list[DictRow]:
        with psycopg.Connection[DictRow].connect(
            self._url, autocommit=True, row_factory=dict_row, options=self._options
        ) as conn:
            return conn.execute(query, params).fetchall()

    # --- RiskRepository ---------------------------------------------------

    def get_score(
        self, person_id: str, window_end: datetime | None = None
    ) -> RiskScore | None:
        query, params = _for_person(
            select=_select(RISK_COLUMNS),
            table=_table("risk"),
            person_col=RISK_COLUMNS["person_id"],
            end_col=RISK_COLUMNS["window_end"],
            person_id=person_id,
            window_end=window_end,
        )
        rows = self._query(query, params)
        return RiskScore(**rows[0]) if rows else None

    def latest_scores(self) -> list[RiskScore]:
        query = sql.SQL(
            "SELECT DISTINCT ON ({pid}) {cols} FROM {table} ORDER BY {pid}, {end} DESC"
        ).format(
            pid=sql.Identifier(RISK_COLUMNS["person_id"]),
            cols=_select(RISK_COLUMNS),
            table=_table("risk"),
            end=sql.Identifier(RISK_COLUMNS["window_end"]),
        )
        return [RiskScore(**row) for row in self._query(query)]

    def get_history(self, person_id: str, limit: int = 10) -> list[RiskScore]:
        query = sql.SQL(
            "SELECT {cols} FROM {table} WHERE {pid} = %s ORDER BY {end} DESC LIMIT %s"
        ).format(
            cols=_select(RISK_COLUMNS),
            table=_table("risk"),
            pid=sql.Identifier(RISK_COLUMNS["person_id"]),
            end=sql.Identifier(RISK_COLUMNS["window_end"]),
        )
        return [RiskScore(**row) for row in self._query(query, (person_id, limit))]

    # --- FeatureRepository ------------------------------------------------

    def get_features(self, key: WindowKey) -> FeatureVector | None:
        query, params = _for_person(
            select=sql.SQL("*"),
            table=_table("features"),
            person_col=FEATURE_COLUMNS["person_id"],
            end_col=FEATURE_COLUMNS["window_end"],
            person_id=key.person_id,
            window_end=key.window_end,
            tolerance=FEATURE_WINDOW_TOLERANCE,
        )
        rows = self._query(query, params)
        return _to_vector(rows[0]) if rows else None

    def _latest_vectors(
        self, person_ids: list[str] | None = None
    ) -> list[FeatureVector]:
        pid = sql.Identifier(FEATURE_COLUMNS["person_id"])
        end = sql.Identifier(FEATURE_COLUMNS["window_end"])
        query = sql.SQL("SELECT DISTINCT ON ({pid}) * FROM {table}").format(
            pid=pid, table=_table("features")
        )
        params: tuple[Any, ...] = ()
        if person_ids is not None:
            query += sql.SQL(" WHERE {pid} = ANY(%s)").format(pid=pid)
            params = (person_ids,)
        query += sql.SQL(" ORDER BY {pid}, {end} DESC").format(pid=pid, end=end)
        return [_to_vector(row) for row in self._query(query, params)]

    # --- CohortStatsRepository --------------------------------------------

    def feature_stats(self, group: CohortGroup = "all") -> dict[str, FeatureStat]:
        return self._stats.get(group)

    def _load_stats(self, group: CohortGroup) -> dict[str, FeatureStat]:
        if group == "at_risk":
            ids = [s.person_id for s in self.latest_scores() if s.label == "at_risk"]
            return compute_feature_stats(self._latest_vectors(ids))
        try:
            rows = self._query(
                sql.SQL("SELECT {cols} FROM {table}").format(
                    cols=_select(STAT_COLUMNS), table=_table("stats")
                )
            )
        except psycopg.errors.UndefinedTable:
            log.warning("cohort_stats missing; computing from person_features")
            return compute_feature_stats(self._latest_vectors())
        return {row["feature_name"]: FeatureStat(**row) for row in rows}

    # --- HealthProbe ------------------------------------------------------

    def writable_tables(self) -> list[str]:
        """Configured tables the connecting role could write to (should be none)."""
        rows = self._query(
            sql.SQL(
                "SELECT c.relname AS name FROM pg_class c "
                "WHERE c.relname = ANY(%s) AND pg_table_is_visible(c.oid) "
                "AND (has_table_privilege(c.oid, 'INSERT') "
                "OR has_table_privilege(c.oid, 'UPDATE') "
                "OR has_table_privilege(c.oid, 'DELETE'))"
            ),
            (list(TABLES.values()),),
        )
        return sorted(row["name"] for row in rows)

    def check_read_only(self) -> None:
        """Warn, never fail, if the role could write (sessions are read-only anyway)."""
        try:
            writable = self.writable_tables()
        except psycopg.Error:
            log.warning(
                "could not verify the database role is read-only", exc_info=True
            )
            return
        if writable:
            log.warning(
                "database role can write to %s; use a SELECT-only role", writable
            )

    def ping(self) -> bool:
        try:
            self._query(sql.SQL("SELECT 1"))
        except psycopg.Error:
            log.exception("database ping failed")
            return False
        return True

    def model_version(self) -> str | None:
        rows = self._query(
            sql.SQL(
                "SELECT {col} AS model_version FROM {table} ORDER BY {end} DESC LIMIT 1"
            ).format(
                col=sql.Identifier(RISK_COLUMNS["model_version"]),
                table=_table("risk"),
                end=sql.Identifier(RISK_COLUMNS["window_end"]),
            )
        )
        return rows[0]["model_version"] if rows else None
