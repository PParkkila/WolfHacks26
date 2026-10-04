# Databricks notebook source
"""Morning-only registration of compact local outputs. No raw CSV reprocessing."""
import hashlib
import json
from pathlib import Path

from pyspark.sql import functions as F

ROOT = Path("/Volumes/workspace/wolfhacks_raw/source_files/prepared_replay/overnight-v1/imu50")
SCHEMA = "workspace.wolfhacks_demo"
FIXTURE = "overnight-v1"
base_bank = spark.table(f"{SCHEMA}.minute_bank").where("fixture_id = 'nine-day-v1'")
base_metrics = spark.table(f"{SCHEMA}.history_metrics_24h").where("fixture_id = 'nine-day-v1'")
if base_bank.select("source_participant_key").distinct().count() != 17:
    raise ValueError("Existing fallback fixture must contain the verified 17 participants")
bank = base_bank.withColumn("fixture_id", F.lit(FIXTURE))
metrics = base_metrics.withColumn("fixture_id", F.lit(FIXTURE))
added = []
for folder in sorted(ROOT.iterdir()) if ROOT.exists() else []:
    if not folder.is_dir() or folder.name == "00" or not (folder/"manifest.json").exists():
        continue
    record = json.loads((folder/"manifest.json").read_text())
    subject = record["subject_id"]
    if folder.name != subject or subject not in {f"{i:02d}" for i in range(1, 50)}:
        raise ValueError("Invalid prepared participant")
    for name, info in record["files"].items():
        if name not in {"real_minutes.parquet", "minute_bank.parquet", "history_metrics.json"}:
            raise ValueError("Invalid manifest file")
        path = folder/name
        if path.stat().st_size != info["bytes"] or hashlib.sha256(path.read_bytes()).hexdigest() != info["sha256"]:
            raise ValueError(f"Prepared-file integrity check failed: {subject}/{name}")
    extra = spark.read.schema(base_bank.schema).parquet(str(folder/"minute_bank.parquet"))
    if extra.count() != 12960 or extra.where(F.col("source_participant_key") != f"imu50:{subject}").limit(1).count():
        raise ValueError("Incomplete/incorrect participant bank")
    # Select the exact persisted history schema; additional local score metadata
    # is recomputed/persisted by the session's pinned publisher.
    raw_metrics = json.loads((folder/"history_metrics.json").read_text())
    if len(raw_metrics) != 168:
        raise ValueError("Incomplete history")
    values = []
    for row in raw_metrics:
        if row["source_participant_key"] != f"imu50:{subject}":
            raise ValueError("Incorrect history participant")
        values.append(tuple(row[field.name] for field in base_metrics.schema))
    extra_metrics = spark.createDataFrame(values, base_metrics.schema)
    bank = bank.unionByName(extra)
    metrics = metrics.unionByName(extra_metrics)
    added.append(subject)
roster = sorted({f"big_ideas:{i:03d}" for i in range(1, 17)} | {"imu50:00"} | {f"imu50:{s}" for s in added})
# Freeze the roster. A later import cannot quietly add people to an active session.
spark.sql(f"CREATE TABLE IF NOT EXISTS {SCHEMA}.fixture_rosters (fixture_id STRING, roster_json STRING) USING DELTA")
existing = spark.table(f"{SCHEMA}.fixture_rosters").where(F.col("fixture_id") == FIXTURE).first()
if existing and json.loads(existing.roster_json) != roster:
    raise ValueError("Fixture roster already frozen; use a new fixture for additional participants")


def save(frame, name):
    (frame.write.format("delta").mode("overwrite").option("replaceWhere", f"fixture_id = '{FIXTURE}'")
     .partitionBy("fixture_id").saveAsTable(f"{SCHEMA}.{name}"))


# Materialize before replacing partitions in the same source table.
bank.write.format("delta").mode("overwrite").saveAsTable(f"{SCHEMA}.overnight_bank_staging")
metrics.write.format("delta").mode("overwrite").saveAsTable(f"{SCHEMA}.overnight_metrics_staging")
save(spark.table(f"{SCHEMA}.overnight_bank_staging"), "minute_bank")
save(spark.table(f"{SCHEMA}.overnight_metrics_staging"), "history_metrics_24h")
saved_bank = spark.table(f"{SCHEMA}.minute_bank").where(F.col("fixture_id") == FIXTURE)
save(saved_bank.where("minute_offset < 11520"), "history_minutes")
if saved_bank.count() != 12960 * len(roster):
    raise ValueError("Final fixture size mismatch")
if not existing:
    spark.createDataFrame([(FIXTURE, json.dumps(roster))], "fixture_id string, roster_json string").write.mode("append").saveAsTable(f"{SCHEMA}.fixture_rosters")
dbutils.notebook.exit(json.dumps({"fixture_id": FIXTURE, "participants": len(roster), "new_imu50_subjects": added,
                                 "processing": "local raw preprocessing; Databricks compact registration"}))
