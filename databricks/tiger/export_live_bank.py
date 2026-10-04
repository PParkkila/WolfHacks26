# Databricks notebook source
"""Export only the compact reserved demo day for the local fast sensor sender."""
import json
from pathlib import Path
from pyspark.sql import functions as F

frame = (spark.table("workspace.wolfhacks_demo.minute_bank")
         .where((F.col("fixture_id") == "overnight-v1") & (F.col("minute_offset") >= 11519)))
if frame.select("source_participant_key").distinct().count() != 66 or frame.count() != 66 * 1441:
    raise ValueError("Expected the frozen 66-person reserved day plus interpolation boundary")
path = Path("/Volumes/workspace/wolfhacks_raw/source_files/prepared_replay/overnight-v1/live_bank.jsonl")
with path.open("w") as output:
    for row in frame.orderBy("source_participant_key", "minute_offset").collect():
        output.write(json.dumps(row.asDict(), allow_nan=False) + "\n")
dbutils.notebook.exit(json.dumps({"participants": 66, "rows": 66 * 1441, "path": str(path), "bytes": path.stat().st_size}))
