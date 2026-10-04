"""Read-only Postgres adapter for Contract A (TigerData).

Table and column names live in the two mappings below; when the data team's
schema drifts, that is the only code that changes. Every connection is opened
read-only with a statement timeout, and only SELECTs are ever issued.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import DictRow, dict_row

from agent.analysis.stats import compute_feature_stats
from agent.domain.models import CohortGroup, FeatureStat, FeatureVector, RiskScore

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
    "p25": "p25",
    "p50": "p50",
    "p75": "p75",
}
# Columns of person_features that are not feature values.
FEATURE_META_COLUMNS = frozenset({"person_id", "window_start", "window_end"})


def _select(columns: dict[str, str]) -> sql.Composed:
    return sql.SQL(", ").join(
        sql.SQL("{} AS {}").format(sql.Identifier(column), sql.Identifier(field))
        for field, column in columns.items()
    )


def _table(key: str) -> sql.Identifier:
    return sql.Identifier(TABLES[key])


def _to_vector(row: dict[str, Any]) -> FeatureVector:
    values = {
        name: None if value is None else float(value)
        for name, value in row.items()
        if name not in FEATURE_META_COLUMNS
        and (value is None or isinstance(value, int | float | Decimal))
    }
    return FeatureVector(
        person_id=row["person_id"], window_end=row["window_end"], values=values
    )


class PostgresBackend:
    """Implements every read port (risk, features, stats, health)."""

    def __init__(self, database_url: str, statement_timeout_ms: int = 5_000) -> None:
        self._url = database_url
        self._options = (
            "-c default_transaction_read_only=on "
            f"-c statement_timeout={statement_timeout_ms}"
        )
        self._stats: dict[CohortGroup, dict[str, FeatureStat]] = {}

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
        query = sql.SQL("SELECT {cols} FROM {table} WHERE {pid} = %s").format(
            cols=_select(RISK_COLUMNS),
            table=_table("risk"),
            pid=sql.Identifier(RISK_COLUMNS["person_id"]),
        )
        params: tuple[Any, ...] = (person_id,)
        if window_end is not None:
            query += sql.SQL(" AND {} = %s").format(
                sql.Identifier(RISK_COLUMNS["window_end"])
            )
            params += (window_end,)
        query += sql.SQL(" ORDER BY {} DESC LIMIT 1").format(
            sql.Identifier(RISK_COLUMNS["window_end"])
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

    # --- FeatureRepository ------------------------------------------------

    def get_features(
        self, person_id: str, window_end: datetime | None = None
    ) -> FeatureVector | None:
        query = sql.SQL("SELECT * FROM {table} WHERE person_id = %s").format(
            table=_table("features")
        )
        params: tuple[Any, ...] = (person_id,)
        if window_end is not None:
            query += sql.SQL(" AND window_end = %s")
            params += (window_end,)
        query += sql.SQL(" ORDER BY window_end DESC LIMIT 1")
        rows = self._query(query, params)
        return _to_vector(rows[0]) if rows else None

    def _latest_vectors(
        self, person_ids: list[str] | None = None
    ) -> list[FeatureVector]:
        query = sql.SQL("SELECT DISTINCT ON (person_id) * FROM {table}").format(
            table=_table("features")
        )
        params: tuple[Any, ...] = ()
        if person_ids is not None:
            query += sql.SQL(" WHERE person_id = ANY(%s)")
            params = (person_ids,)
        query += sql.SQL(" ORDER BY person_id, window_end DESC")
        return [_to_vector(row) for row in self._query(query, params)]

    # --- CohortStatsRepository --------------------------------------------

    def feature_stats(self, group: CohortGroup = "all") -> dict[str, FeatureStat]:
        if group not in self._stats:
            self._stats[group] = self._load_stats(group)
        return self._stats[group]

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
