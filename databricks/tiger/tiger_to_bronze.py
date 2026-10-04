# Databricks notebook source
"""Incrementally copy Tiger live events into a Databricks Bronze table."""

# COMMAND ----------

# MAGIC %pip install "pg8000>=1.31,<2"

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

from datetime import datetime, timedelta, timezone
import re
import ssl
import json

import pg8000.native
from pyspark.sql.types import (
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

spark.conf.set("spark.sql.session.timeZone", "UTC")

dbutils.widgets.text("tiger_host", "")
dbutils.widgets.text("tiger_port", "5432")
dbutils.widgets.text("tiger_database", "tsdb")
dbutils.widgets.text("secret_scope", "wolfhacks")
dbutils.widgets.text("user_secret_key", "tiger-user")
dbutils.widgets.text("password_secret_key", "tiger-password")
dbutils.widgets.text("target_table", "workspace.wolfhacks_bronze.sensor_events")
dbutils.widgets.text("lookback_minutes", "10")

tiger_host = dbutils.widgets.get("tiger_host").strip()
tiger_port = int(dbutils.widgets.get("tiger_port"))
tiger_database = dbutils.widgets.get("tiger_database").strip()
secret_scope = dbutils.widgets.get("secret_scope").strip()
user_secret_key = dbutils.widgets.get("user_secret_key").strip()
password_secret_key = dbutils.widgets.get("password_secret_key").strip()
target_table = dbutils.widgets.get("target_table").strip()
lookback_minutes = int(dbutils.widgets.get("lookback_minutes"))

if not tiger_host:
    raise ValueError("Set the tiger_host job parameter")
if lookback_minutes < 1:
    raise ValueError("lookback_minutes must be at least 1")
if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*", target_table):
    raise ValueError("target_table must be an unquoted catalog.schema.table name")

tiger_user = dbutils.secrets.get(secret_scope, user_secret_key)
tiger_password = dbutils.secrets.get(secret_scope, password_secret_key)

# COMMAND ----------

latest = spark.sql(
    f"SELECT max(received_at) AS latest_received_at FROM {target_table}"
).first()["latest_received_at"]

if latest is None:
    start_at = datetime(1970, 1, 1, tzinfo=timezone.utc)
else:
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    start_at = latest - timedelta(minutes=lookback_minutes)

# Avoid racing an event transaction that is still committing. The next run's
# lookback deliberately rereads recent rows; MERGE makes that idempotent.
end_at = datetime.now(timezone.utc) - timedelta(seconds=5)

event_schema = StructType(
    [
        StructField("observed_at", TimestampType(), False),
        StructField("received_at", TimestampType(), False),
        StructField("sensor_id", StringType(), False),
        StructField("event_id", StringType(), False),
        StructField("sequence_number", LongType(), True),
        StructField("schema_version", IntegerType(), False),
        StructField("raw_payload", StringType(), False),
        StructField("bronze_ingested_at", TimestampType(), False),
    ]
)


def spark_timestamp(value):
    """Convert an aware PostgreSQL timestamp to a naive UTC Spark timestamp."""
    return value.astimezone(timezone.utc).replace(tzinfo=None)


select_events = """
    SELECT observed_at,
           received_at,
           sensor_id,
           event_id::text,
           sequence_number,
           schema_version,
           raw_payload::text
    FROM raw.sensor_events
    WHERE received_at >= :start_at
      AND received_at < :end_at
    ORDER BY received_at
"""

candidate_count = 0
batch_size = 10_000

connection = pg8000.native.Connection(
    host=tiger_host,
    port=tiger_port,
    database=tiger_database,
    user=tiger_user,
    password=tiger_password,
    ssl_context=ssl.create_default_context(),
    timeout=30,
)
try:
    connection.run("START TRANSACTION READ ONLY")
    connection.run(
        "DECLARE tiger_bronze_stream NO SCROLL CURSOR FOR " + select_events,
        start_at=start_at,
        end_at=end_at,
    )

    # FETCH bounds memory on the server and client; DB-API fetchmany alone
    # would not prevent this pure-Python driver buffering the full result.
    while rows := connection.run(f"FETCH FORWARD {batch_size} FROM tiger_bronze_stream"):
        ingested_at = datetime.now(timezone.utc).replace(tzinfo=None)
        normalized = [
            (
                spark_timestamp(row[0]),
                spark_timestamp(row[1]),
                row[2],
                row[3],
                row[4],
                row[5],
                row[6],
                ingested_at,
            )
            for row in rows
        ]
        incoming = spark.createDataFrame(normalized, event_schema)
        incoming.createOrReplaceTempView("tiger_sensor_events_increment")
        spark.sql(
            f"""
            MERGE INTO {target_table} AS target
            USING tiger_sensor_events_increment AS source
            ON target.sensor_id = source.sensor_id
               AND target.observed_at = source.observed_at
               AND target.event_id = source.event_id
            WHEN NOT MATCHED THEN INSERT *
            """
        )
        candidate_count += len(rows)
        print(f"Processed {candidate_count:,} candidate events...")
    connection.run("ROLLBACK")
finally:
    connection.close()

start_text = start_at.isoformat()
end_text = end_at.isoformat()
if candidate_count == 0:
    print(f"No Tiger events between {start_text} and {end_text}.")
else:
    print(
        f"Finished merging {candidate_count:,} candidate events from "
        f"{start_text} through {end_text}."
    )

dbutils.notebook.exit(json.dumps({
    "candidate_events": candidate_count,
    "target_table": target_table,
    "start_at": start_text,
    "end_at": end_text,
}))
