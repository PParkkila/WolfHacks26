# Databricks notebook source
"""Incrementally copy Tiger live events into a Databricks Bronze Delta table."""

# COMMAND ----------

from datetime import datetime, timedelta, timezone

from pyspark.sql import functions as F


spark.conf.set("spark.sql.session.timeZone", "UTC")

dbutils.widgets.text("tiger_host", "")
dbutils.widgets.text("tiger_port", "5432")
dbutils.widgets.text("tiger_database", "tsdb")
dbutils.widgets.text("secret_scope", "wolfhacks")
dbutils.widgets.text("user_secret_key", "tiger-user")
dbutils.widgets.text("password_secret_key", "tiger-password")
dbutils.widgets.text("target_table", "main.wolfhacks_bronze.sensor_events")
dbutils.widgets.text("lookback_minutes", "10")

tiger_host = dbutils.widgets.get("tiger_host").strip()
tiger_port = dbutils.widgets.get("tiger_port").strip()
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
# lookback also deliberately rereads recent rows; MERGE makes that idempotent.
end_at = datetime.now(timezone.utc) - timedelta(seconds=5)

start_sql = start_at.isoformat()
end_sql = end_at.isoformat()
source_query = f"""
    SELECT observed_at,
           received_at,
           sensor_id,
           event_id::text AS event_id,
           sequence_number,
           schema_version,
           raw_payload::text AS raw_payload
    FROM raw.sensor_events
    WHERE received_at >= TIMESTAMPTZ '{start_sql}'
      AND received_at < TIMESTAMPTZ '{end_sql}'
"""

jdbc_url = (
    f"jdbc:postgresql://{tiger_host}:{tiger_port}/{tiger_database}"
    "?sslmode=require"
)

incoming = (
    spark.read.format("jdbc")
    .option("url", jdbc_url)
    .option("dbtable", f"({source_query}) AS source_events")
    .option("user", tiger_user)
    .option("password", tiger_password)
    .option("driver", "org.postgresql.Driver")
    .option("fetchsize", "10000")
    .load()
    .withColumn("bronze_ingested_at", F.current_timestamp())
    .cache()
)

# COMMAND ----------

candidate_count = incoming.count()
if candidate_count == 0:
    print(f"No Tiger events between {start_sql} and {end_sql}.")
else:
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
    print(
        f"Merged {candidate_count:,} candidate events from "
        f"{start_sql} through {end_sql}."
    )

incoming.unpersist()
