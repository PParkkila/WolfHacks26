# Databricks notebook source
"""Export one model version's small Gold snapshots to Tiger, idempotently."""

# COMMAND ----------
# MAGIC %pip install "pg8000>=1.31,<2"

# COMMAND ----------
dbutils.library.restartPython()

# COMMAND ----------
from datetime import timezone
import json
import re
import ssl

import pg8000.native
from pyspark.sql import functions as F

dbutils.widgets.text("model_version", "")
dbutils.widgets.text("tiger_host", "")
dbutils.widgets.text("tiger_port", "5432")
dbutils.widgets.text("tiger_database", "tsdb")
dbutils.widgets.text("secret_scope", "wolfhacks")
version = dbutils.widgets.get("model_version")
if not re.fullmatch(r"[a-f0-9]{32}", version):
    raise ValueError("Supply the completed training run's model_version")
spark.conf.set("spark.sql.session.timeZone", "UTC")
scope = dbutils.widgets.get("secret_scope")

common = {
    "source_dataset": "TEXT NOT NULL", "subject_id": "TEXT NOT NULL",
    "participant_key": "TEXT NOT NULL", "observation_start": "TIMESTAMP NOT NULL",
    "observation_end": "TIMESTAMP NOT NULL", "model_name": "TEXT NOT NULL",
    "model_version": "TEXT NOT NULL", "feature_version": "TEXT NOT NULL",
    "inference_timestamp": "TIMESTAMPTZ NOT NULL", "evaluation": "TEXT NOT NULL",
    "unit_status": "TEXT NOT NULL", "outside_training_feature_range": "BOOLEAN NOT NULL",
    "interpretation": "TEXT NOT NULL",
}
tables = {
    "metabolic_risk_predictions": {
        **common, "risk_probability": "DOUBLE PRECISION NOT NULL CHECK (risk_probability BETWEEN 0 AND 1)",
        "risk_class": "INTEGER NOT NULL CHECK (risk_class IN (0,1))", "actual_label": "INTEGER",
    },
    "glucose_proxy_predictions": {
        **common, "predicted_glucose_metric": "DOUBLE PRECISION NOT NULL",
        "actual_glucose_metric": "DOUBLE PRECISION", "absolute_error": "DOUBLE PRECISION",
        "predictive_std": "DOUBLE PRECISION",
    },
}
pending = {}
for name, columns in tables.items():
    rows = (spark.read.table(f"workspace.wolfhacks_gold.{name}")
            .where(F.col("model_version") == version).select(*columns).limit(1001).collect())
    if not rows or len(rows) > 1000:
        raise ValueError("Expected a bounded non-empty subject prediction snapshot")
    records = [row.asDict() for row in rows]
    keys = [(r["participant_key"], r["evaluation"]) for r in records]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate Gold prediction keys")
    for record in records:
        record["inference_timestamp"] = record["inference_timestamp"].replace(tzinfo=timezone.utc)
        if record["source_dataset"] == "imu50":
            for field in ("actual_label", "actual_glucose_metric", "absolute_error"):
                if record.get(field) is not None:
                    raise ValueError("IMU50 actual outcomes must be NULL")
    pending[name] = records

connection = pg8000.native.Connection(
    host=dbutils.widgets.get("tiger_host"), port=int(dbutils.widgets.get("tiger_port")),
    database=dbutils.widgets.get("tiger_database"),
    user=dbutils.secrets.get(scope, "tiger-user"), password=dbutils.secrets.get(scope, "tiger-password"),
    ssl_context=ssl.create_default_context(), timeout=30,
)
try:
    connection.run("START TRANSACTION")
    connection.run("CREATE SCHEMA IF NOT EXISTS gold")
    counts = {}
    for name, columns in tables.items():
        definitions = ", ".join(f"{column} {kind}" for column, kind in columns.items())
        connection.run(f"CREATE TABLE IF NOT EXISTS gold.{name} ({definitions}, "
                       "PRIMARY KEY (model_version, participant_key, evaluation))")
        query = (f"INSERT INTO gold.{name} ({', '.join(columns)}) VALUES "
                 f"({', '.join(':' + column for column in columns)}) "
                 "ON CONFLICT (model_version, participant_key, evaluation) DO NOTHING")
        for record in pending[name]:
            connection.run(query, **record)
        count = connection.run(f"SELECT count(*) FROM gold.{name} WHERE model_version=:version", version=version)[0][0]
        if count != len(pending[name]):
            raise ValueError(f"Tiger row-count mismatch for {name}")
        counts[name] = count
    connection.run("COMMIT")
except Exception:
    connection.run("ROLLBACK")
    raise
finally:
    connection.close()
dbutils.notebook.exit(json.dumps({"model_version": version, "tiger_rows": counts}))
