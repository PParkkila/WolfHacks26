# Databricks notebook source
"""Read-only connectivity/schema check. Never print connection credentials."""

# COMMAND ----------
# MAGIC %pip install "pg8000>=1.31,<2"

# COMMAND ----------
dbutils.library.restartPython()

# COMMAND ----------
import importlib.metadata
import json
import ssl
from contextlib import closing

import pg8000.native

dbutils.widgets.text("tiger_host", "")
dbutils.widgets.text("tiger_port", "5432")
dbutils.widgets.text("tiger_database", "tsdb")
dbutils.widgets.text("secret_scope", "wolfhacks")

scope = dbutils.widgets.get("secret_scope")
report = {}
try:
    with closing(pg8000.native.Connection(
        host=dbutils.widgets.get("tiger_host"),
        port=int(dbutils.widgets.get("tiger_port")),
        database=dbutils.widgets.get("tiger_database"),
        user=dbutils.secrets.get(scope, "tiger-user"),
        password=dbutils.secrets.get(scope, "tiger-password"),
        ssl_context=ssl.create_default_context(),
        timeout=30,
    )) as connection:
        connection.run("START TRANSACTION READ ONLY")
        connection.run("SET LOCAL statement_timeout = 30000")
        report["connection"] = "ok"
        report["timescaledb_version"] = connection.run(
            "SELECT extversion FROM pg_extension WHERE extname='timescaledb'"
        )
        report["raw_table"] = connection.run(
            "SELECT to_regclass('raw.sensor_events')::text"
        )[0][0]
        if report["raw_table"]:
            report["columns"] = connection.run(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema='raw' AND table_name='sensor_events' "
                "ORDER BY ordinal_position"
            )
            report["event_summary"] = connection.run(
                "SELECT count(*), min(observed_at), max(observed_at) "
                "FROM raw.sensor_events"
            )[0]
            report["hypertable"] = connection.run(
                "SELECT count(*) FROM timescaledb_information.hypertables "
                "WHERE hypertable_schema='raw' AND hypertable_name='sensor_events'"
            )[0][0]
        connection.run("ROLLBACK")
except (pg8000.native.DatabaseError, pg8000.native.InterfaceError, OSError) as error:
    # Return a useful category without emitting the connection string or secrets.
    message = str(error).lower()
    report["connection"] = "failed"
    report["error_type"] = type(error).__name__
    report["sqlstate"] = (
        error.args[0].get("C") if error.args and isinstance(error.args[0], dict) else None
    )
    report["reason"] = (
        "authentication_failed" if "password authentication failed" in message
        else "timeout" if "timeout" in message or "timed out" in message
        else "dns_resolution_failed" if "translate host name" in message or "resolve" in message
        else "connection_refused" if "refused" in message
        else "connection_failed"
    )

report["libraries"] = {}
for package in ("pyspark", "scikit-learn", "xgboost", "mlflow", "pg8000"):
    try:
        report["libraries"][package] = importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        report["libraries"][package] = None
dbutils.notebook.exit(json.dumps(report, default=str))
