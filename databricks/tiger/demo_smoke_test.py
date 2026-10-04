# Databricks notebook source
"""Finite demo replay: prepare, emit, refresh. No scheduler or continuous loop.

The producer writes directly to Tiger; this does NOT test the HTTP ingestion API.
Historical minute summaries are seeded separately, not claimed as live ingestion.
"""

# COMMAND ----------
# MAGIC %pip install "pg8000>=1.31,<2"

# COMMAND ----------
dbutils.library.restartPython()

# COMMAND ----------
from datetime import datetime, timedelta, timezone
import json
import math
import re
import ssl
import sys
import time

import pg8000.native
from pyspark.sql import functions as F

sys.path.insert(0, "/Workspace/Users/pbparkki@ncsu.edu/WolfHacks26/databricks/tiger")
from demo_replay_payload import event_for_minute

for key, default in {
    "mode": "prepare", "session_id": "submission-smoke-v1", "fixture_id": "nine-day-v1",
    "replay_start": "2026-10-04T04:00:00+00:00", "start_offset": "11520", "end_offset": "11580",
    "tiger_host": "hi70ycj0r6.b4t1dqdug8.tsdb.cloud.timescale.com", "tiger_port": "31994",
    "tiger_database": "tsdb", "secret_scope": "wolfhacks",
}.items():
    dbutils.widgets.text(key, default)
p = {key: dbutils.widgets.get(key) for key in (
    "mode", "session_id", "fixture_id", "replay_start", "start_offset", "end_offset",
    "tiger_host", "tiger_port", "tiger_database", "secret_scope")}
session, fixture = p["session_id"], p["fixture_id"]
if not all(re.fullmatch(r"[a-z0-9-]{1,50}", value) for value in (session, fixture)):
    raise ValueError("Session/fixture must use lowercase letters, digits, hyphens")
anchor = datetime.fromisoformat(p["replay_start"])
if anchor.tzinfo is None:
    raise ValueError("replay_start must be timezone-aware")
anchor = anchor.astimezone(timezone.utc)
start, end = int(p["start_offset"]), int(p["end_offset"])
if not 11520 <= start < end <= 12960 or start % 60 or end % 60 or end - start > 60:
    raise ValueError("Each finite batch must contain exactly one reserved replay hour")
spark.conf.set("spark.sql.session.timeZone", "UTC")
SCHEMA = "workspace.wolfhacks_demo"
signals = ["enmo_mean_g", "enmo_std_g", "enmo_p95_g", "temperature_mean_c", "hr_mean_bpm"]
minute_columns = ["session_id", "fixture_id", "demo_participant_key", "source_participant_key",
                  "source_dataset", "unit_status", "minute_offset", *signals, "is_synthetic"]
metric_columns = ["window_minutes", "motion_mean_g", "motion_std_g", "motion_p90_g",
                  "temperature_mean_c_24h", "temperature_std_c_24h", "hr_mean_bpm_24h",
                  "hr_coverage_fraction", "motion_hr_correlation", "synthetic_minutes",
                  "synthetic_fraction", "wearable_risk_indicator", "risk_status"]


def connect():
    return pg8000.native.Connection(
        host=p["tiger_host"], port=int(p["tiger_port"]), database=p["tiger_database"],
        user=dbutils.secrets.get(p["secret_scope"], "tiger-user"),
        password=dbutils.secrets.get(p["secret_scope"], "tiger-password"),
        ssl_context=ssl.create_default_context(), timeout=60)


def merge(frame, name, keys):
    frame.createOrReplaceTempView("demo_increment")
    spark.sql(f"CREATE TABLE IF NOT EXISTS {SCHEMA}.{name} USING DELTA AS SELECT * FROM demo_increment WHERE false")
    on = " AND ".join(f"t.{key} = s.{key}" for key in keys)
    spark.sql(f"MERGE INTO {SCHEMA}.{name} t USING demo_increment s ON {on} "
              "WHEN NOT MATCHED THEN INSERT *")


def dashboard(frame):
    return (frame.withColumn("session_id", F.lit(session))
            .withColumn("participant_key", F.col("demo_participant_key"))
            .withColumn("window_end", F.expr(
                f"timestampadd(MINUTE, window_end_offset_minutes - 11520, TIMESTAMP '{anchor.isoformat()}')"))
            .withColumn("demo_only", F.lit(True)).withColumn("training_eligible", F.lit(False))
            .withColumn("time_basis", F.lit("simulated_event_time"))
            .select("session_id", "fixture_id", "participant_key", "source_participant_key",
                    "source_dataset", "unit_status", "window_end_offset_minutes", "window_end",
                    *metric_columns, "demo_only", "training_eligible", "time_basis"))


def clean(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc).isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def publish():
    rows = (spark.table(f"{SCHEMA}.dashboard_windows").where(F.col("session_id") == session)
            .orderBy("participant_key", "window_end").limit(5001).collect())
    if not rows or len(rows) > 5000:
        raise ValueError("Unexpected dashboard size")
    records = [{k: clean(v) for k, v in row.asDict().items()} for row in rows]
    if any(r["window_minutes"] != 1440 or r["wearable_risk_indicator"] is not None for r in records):
        raise ValueError("Require full 24-hour windows and honest pending risk")
    connection = connect()
    try:
        connection.run("START TRANSACTION")
        connection.run("CREATE SCHEMA IF NOT EXISTS gold")
        connection.run("""CREATE TABLE IF NOT EXISTS gold.dashboard_windows (
            session_id TEXT NOT NULL, participant_key TEXT NOT NULL,
            window_end TIMESTAMPTZ NOT NULL, payload JSONB NOT NULL,
            published_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (session_id, participant_key, window_end))""")
        connection.run("""INSERT INTO gold.dashboard_windows (session_id, participant_key, window_end, payload)
            SELECT item->>'session_id', item->>'participant_key', (item->>'window_end')::timestamptz, item
            FROM jsonb_array_elements(CAST(:payload AS jsonb)) item
            ON CONFLICT (session_id, participant_key, window_end) DO NOTHING""",
            payload=json.dumps(records, allow_nan=False))
        connection.run("""CREATE OR REPLACE VIEW gold.dashboard_latest AS
            SELECT DISTINCT ON (session_id, participant_key) * FROM gold.dashboard_windows
            ORDER BY session_id, participant_key, window_end DESC""")
        count = connection.run("SELECT count(*) FROM gold.dashboard_windows WHERE session_id=:session",
                               session=session)[0][0]
        if count != len(records):
            raise ValueError("Tiger/Delta dashboard counts differ")
        latest = connection.run("SELECT payload::text FROM gold.dashboard_latest WHERE session_id=:session ORDER BY participant_key",
                                session=session)
        connection.run("COMMIT")
    except Exception:
        connection.run("ROLLBACK")
        raise
    finally:
        connection.close()
    return {"dashboard_rows": count, "participants": len(latest),
            "latest": [json.loads(row[0]) for row in latest],
            "example_trend": [r for r in records if r["participant_key"] == "demo:big_ideas:001"][-168:]}


# The persisted session prevents reruns from silently changing the event clock.
session_frame = spark.createDataFrame([(session, fixture, anchor.isoformat())],
                                     "session_id string, fixture_id string, replay_start string")
merge(session_frame, "replay_sessions", ["session_id"])
saved = spark.table(f"{SCHEMA}.replay_sessions").where(F.col("session_id") == session).first()
if saved.fixture_id != fixture or saved.replay_start != anchor.isoformat():
    raise ValueError("Existing session uses different fixture/anchor; choose a new session ID")

result = {"session_id": session, "mode": p["mode"], "continuous_stream_enabled": False,
          "transport": "direct_tiger_database_not_http", "risk_status": "pending_24h_model"}
if p["mode"] == "prepare":
    history = (spark.table(f"{SCHEMA}.history_minutes").where(F.col("fixture_id") == fixture)
               .withColumn("session_id", F.lit(session)).select(*minute_columns))
    if history.count() != 17 * 11520:
        raise ValueError("Expected 17 prepared demo participants with eight input days each")
    merge(history, "replay_minutes", ["session_id", "demo_participant_key", "minute_offset"])
    metrics = spark.table(f"{SCHEMA}.history_metrics_24h").where(F.col("fixture_id") == fixture)
    merge(dashboard(metrics), "dashboard_windows", ["session_id", "participant_key", "window_end"])
    result.update(publish())
elif p["mode"] == "emit":
    rows = (spark.table(f"{SCHEMA}.minute_bank").where(
        (F.col("fixture_id") == fixture) & (F.col("minute_offset") >= start) & (F.col("minute_offset") < end))
        .orderBy("minute_offset", "demo_participant_key").collect())
    if len(rows) != 17 * (end - start):
        raise ValueError("Incomplete reserved replay hour")
    events = [event_for_minute(row.asDict(), session, anchor) for row in rows]
    query = """INSERT INTO raw.sensor_events
        (observed_at, sensor_id, event_id, sequence_number, schema_version, raw_payload)
        SELECT (event->>'observed_at')::timestamptz, event->>'sensor_id', (event->>'event_id')::uuid,
               (event->>'sequence_number')::bigint, (event->>'schema_version')::integer, event
        FROM jsonb_array_elements(CAST(:payload AS jsonb)) event
        ON CONFLICT (sensor_id, observed_at, event_id) DO NOTHING RETURNING event_id"""
    connection = connect()
    try:
        payload = json.dumps(events, allow_nan=False)
        inserted = len(connection.run(query, payload=payload))
        retry_inserted = len(connection.run(query, payload=payload))
        if retry_inserted != 0:
            raise ValueError("Event retry was not idempotent")
    finally:
        connection.close()
    # The existing Bronze reader deliberately excludes the newest five seconds.
    time.sleep(6)
    result.update({"accepted": len(events), "inserted": inserted, "retry_inserted": retry_inserted,
                   "start_offset": start, "end_offset": end})
elif p["mode"] == "refresh":
    # Decode actual ingested events, never read the reserved minute bank here.
    events = spark.table("workspace.wolfhacks_bronze.sensor_events")
    get = lambda path: F.get_json_object("raw_payload", "$.measurements." + path)
    events = events.where((get("contract") == "demo_minute_summary_v1") & (get("demo.session_id") == session))
    live = events.select(
        F.lit(session).alias("session_id"), get("demo.fixture_id").alias("fixture_id"),
        F.concat(F.lit("demo:"), get("demo.source_participant_key")).alias("demo_participant_key"),
        get("demo.source_participant_key").alias("source_participant_key"),
        F.split(get("demo.source_participant_key"), ":").getItem(0).alias("source_dataset"),
        get("demo.unit_status").alias("unit_status"), F.col("sequence_number").cast("int").alias("minute_offset"),
        *[get(c).cast("double").alias(c) for c in signals], get("demo.is_synthetic").cast("boolean").alias("is_synthetic"))
    live = live.where((F.col("minute_offset") >= 11520) & (F.col("minute_offset") < end))
    if live.count() != 17 * (end - 11520):
        raise ValueError("Missing/duplicate Bronze replay events; do not publish incomplete windows")
    if live.groupBy("demo_participant_key", "minute_offset").count().where("count <> 1").limit(1).count():
        raise ValueError("Duplicate minute keys in Bronze")
    merge(live.select(*minute_columns), "replay_minutes", ["session_id", "demo_participant_key", "minute_offset"])
    trailing = spark.table(f"{SCHEMA}.replay_minutes").where(
        (F.col("session_id") == session) & (F.col("minute_offset") >= end - 1440) & (F.col("minute_offset") < end))
    metrics = trailing.groupBy("fixture_id", "demo_participant_key", "source_participant_key", "source_dataset", "unit_status").agg(
        F.count("*").alias("window_minutes"), F.avg("enmo_mean_g").alias("motion_mean_g"),
        F.stddev_samp("enmo_mean_g").alias("motion_std_g"), F.percentile_approx("enmo_mean_g", .9, 1000).alias("motion_p90_g"),
        F.avg("temperature_mean_c").alias("temperature_mean_c_24h"), F.stddev_samp("temperature_mean_c").alias("temperature_std_c_24h"),
        F.avg("hr_mean_bpm").alias("hr_mean_bpm_24h"), (F.count("hr_mean_bpm") / 1440).alias("hr_coverage_fraction"),
        F.corr("enmo_mean_g", "hr_mean_bpm").alias("motion_hr_correlation"),
        F.sum(F.col("is_synthetic").cast("int")).alias("synthetic_minutes"))
    metrics = (metrics.withColumn("synthetic_fraction", F.col("synthetic_minutes") / 1440)
               .withColumn("window_end_offset_minutes", F.lit(end))
               .withColumn("wearable_risk_indicator", F.lit(None).cast("double"))
               .withColumn("risk_status", F.lit("pending_24h_model_not_a_glucose_measurement")))
    merge(dashboard(metrics), "dashboard_windows", ["session_id", "participant_key", "window_end"])
    result.update(publish())
    result.update({"bronze_replay_events": live.count(), "latest_end_offset": end})
else:
    raise ValueError("mode must be prepare, emit, or refresh")

dbutils.notebook.exit(json.dumps(result, allow_nan=False))
