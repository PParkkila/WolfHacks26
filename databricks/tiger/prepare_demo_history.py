# Databricks notebook source
"""Prepare isolated nine-day demo fixtures. Does NOT start a stream or train a model."""

import json
import re

from pyspark.sql import functions as F, Window

dbutils.widgets.text("fixture_id", "nine-day-v1")
fixture = dbutils.widgets.get("fixture_id")
if not re.fullmatch(r"[a-z0-9-]{1,50}", fixture):
    raise ValueError("fixture_id must be lowercase letters/digits/hyphens")
spark.conf.set("spark.sql.session.timeZone", "UTC")
SCHEMA = "workspace.wolfhacks_demo"
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
minute = spark.read.table("workspace.wolfhacks_silver.shared_sensor_minute_pilot")
valid = minute.where(
    F.col("acc_sample_ratio").between(.8, 1)
    & F.col("temperature_sample_ratio").between(.8, 1)
    & F.col("enmo_mean_g").isNotNull() & F.col("temperature_mean_c").isNotNull())

# HR is measured in BIG IDEAs only, not invented from IMU50 PPG.
hr = (spark.read.option("header", True)
      .csv("/Volumes/workspace/wolfhacks_raw/source_files/big_ideas/[0-9][0-9][0-9]/HR_*.csv")
      .select("*", F.col("_metadata.file_path").alias("source_file")))
hr = (hr.toDF("datetime_raw", "hr_raw", "source_file")
      .withColumn("participant_key", F.concat(F.lit("big_ideas:"),
          F.regexp_extract("source_file", r"/([0-9]{3})/[^/]+$", 1)))
      .withColumn("event_ts", F.coalesce(F.expr("try_cast(datetime_raw AS TIMESTAMP_NTZ)"),
          F.try_to_timestamp("datetime_raw", F.lit("M/d/yy H:mm")).cast("timestamp_ntz")))
      .withColumn("hr", F.expr("try_cast(hr_raw AS DOUBLE)")))
if hr.where("event_ts IS NULL").limit(1).count():
    raise ValueError("Unrecognized HR timestamp format; inspect source before demo preparation")
hr = (hr.withColumn("minute_ts", F.make_timestamp_ntz(F.year("event_ts"), F.month("event_ts"),
          F.dayofmonth("event_ts"), F.hour("event_ts"), F.minute("event_ts"), F.lit(0)))
      .where((F.col("hr") > 0) & (F.col("hr") < F.lit(float("inf"))) & ~F.isnan("hr"))
      .groupBy("participant_key", "minute_ts").agg(F.avg("hr").alias("hr_mean_bpm"),
                                                  F.count("*").alias("hr_samples"))
      .withColumn("hr_mean_bpm", F.when(F.col("hr_samples").between(48, 60), F.col("hr_mean_bpm")))
      .drop("hr_samples"))
signals = ["enmo_mean_g", "enmo_std_g", "enmo_p95_g", "temperature_mean_c", "hr_mean_bpm"]
valid = (valid.drop("hr_mean_bpm").join(hr, ["participant_key", "minute_ts"], "left")
         .withColumn("clock_minute", F.hour("minute_ts") * 60 + F.minute("minute_ts")))
if valid.groupBy("participant_key", "minute_ts").count().where("count <> 1").limit(1).count():
    raise ValueError("Source minute keys must be unique")
people = valid.groupBy("participant_key", "source_dataset", "subject_id", "unit_status").agg(
    F.min("minute_ts").alias("source_start"), F.max("minute_ts").alias("source_last"))
expected_people = {f"big_ideas:{i:03d}" for i in range(1, 17)} | {"imu50:00"}
if {r.participant_key for r in people.select("participant_key").collect()} != expected_people:
    raise ValueError("Unexpected roster: inspect before generating demo fixtures")

# One deterministic donor template per person. Prefer their most complete day;
# fill holes from their other days at the same clock minute. Keep sensor tuples
# together, never combine axes/HR/temperature from different participants.
day_counts = (valid.withColumn("source_day", F.to_date("minute_ts"))
              .groupBy("participant_key", "source_day").count().withColumnRenamed("count", "day_minutes"))
ranked = (valid.withColumn("source_day", F.to_date("minute_ts"))
          .join(day_counts, ["participant_key", "source_day"])
          .withColumn("donor_rank", F.row_number().over(Window.partitionBy("participant_key", "clock_minute")
              .orderBy(F.desc("day_minutes"), "minute_ts"))).where("donor_rank = 1"))
template = ranked.select("participant_key", "clock_minute", F.struct(
    F.col("minute_ts").alias("donor_ts"), *[F.col(c) for c in signals]).alias("donor"))
clock_grid = people.select("participant_key").crossJoin(spark.range(1440).select(F.col("id").cast("int").alias("clock_minute")))
template = clock_grid.join(template, ["participant_key", "clock_minute"], "left")
clock_order = Window.partitionBy("participant_key").orderBy("clock_minute")
template = template.withColumn("donor", F.coalesce(
    "donor", F.last("donor", ignorenulls=True).over(clock_order.rowsBetween(Window.unboundedPreceding, 0)),
    F.first("donor", ignorenulls=True).over(clock_order.rowsBetween(0, Window.unboundedFollowing))))

offsets = spark.range(9 * 1440).select(F.col("id").cast("int").alias("minute_offset"))
grid = (people.crossJoin(offsets)
        .withColumn("intended_source_ts", F.expr("timestampadd(MINUTE, minute_offset, source_start)"))
        .withColumn("clock_minute", F.hour("intended_source_ts") * 60 + F.minute("intended_source_ts")))
original = valid.select("participant_key", F.col("minute_ts").alias("intended_source_ts"),
                       F.struct(F.col("minute_ts").alias("donor_ts"), *signals).alias("original"))
filled = (grid.join(original, ["participant_key", "intended_source_ts"], "left")
          .join(template, ["participant_key", "clock_minute"], "left")
          .withColumn("is_synthetic", F.col("original").isNull())
          .withColumn("chosen", F.coalesce("original", "donor")))
bank = filled.select(
    F.lit(fixture).alias("fixture_id"),
    F.concat(F.lit("demo:"), F.col("participant_key")).alias("demo_participant_key"),
    F.col("participant_key").alias("source_participant_key"), "source_dataset", "subject_id", "unit_status",
    "minute_offset", "clock_minute", F.col("intended_source_ts").cast("string").alias("intended_source_clock"),
    F.col("chosen.donor_ts").cast("string").alias("donor_source_clock"),
    *[F.col(f"chosen.{c}").alias(c) for c in signals], "is_synthetic",
    F.when(~F.col("is_synthetic"), F.lit("observed_replay"))
     .when(F.col("intended_source_ts") > F.col("source_last"), F.lit("synthetic_extension"))
     .otherwise(F.lit("synthetic_gap_fill")).alias("provenance"),
    F.when(F.col("minute_offset") < 1440, "warmup")
     .when(F.col("minute_offset") < 8 * 1440, "history").otherwise("replay").alias("phase"),
    F.lit(True).alias("demo_only"), F.lit(False).alias("training_eligible"),
    F.lit("same-person-clock-template-v1").alias("generation_policy"),
)


def save(frame, name):
    # Replace only this explicitly named fixture partition, never other fixtures.
    (frame.write.format("delta").mode("overwrite").option("replaceWhere", f"fixture_id = '{fixture}'")
     .partitionBy("fixture_id").saveAsTable(f"{SCHEMA}.{name}"))


save(bank, "minute_bank")
bank = spark.read.table(f"{SCHEMA}.minute_bank").where(F.col("fixture_id") == fixture)
if bank.count() != len(expected_people) * 9 * 1440:
    raise ValueError("Incomplete nine-day fixture")
if bank.where("enmo_mean_g IS NULL OR temperature_mean_c IS NULL OR donor_source_clock IS NULL").limit(1).count():
    raise ValueError("Missing donor signal/provenance")
if bank.where("source_dataset = 'imu50' AND hr_mean_bpm IS NOT NULL").limit(1).count():
    raise ValueError("Must not fabricate IMU50 HR")

# Strictly historical, trailing windows; future replay day cannot enter metrics.
history = bank.where("minute_offset < 11520")
save(history, "history_minutes")
ordered = Window.partitionBy("fixture_id", "demo_participant_key").orderBy("minute_offset").rangeBetween(-1439, 0)
metrics = history
for name, expression in {
    "window_minutes": F.count("*"),
    "motion_mean_g": F.avg("enmo_mean_g"),
    "motion_std_g": F.stddev_samp("enmo_mean_g"),
    "motion_p90_g": F.percentile_approx("enmo_mean_g", .9, 1000),
    "temperature_mean_c_24h": F.avg("temperature_mean_c"),
    "temperature_std_c_24h": F.stddev_samp("temperature_mean_c"),
    "hr_mean_bpm_24h": F.avg("hr_mean_bpm"),
    "hr_minutes": F.count("hr_mean_bpm"),
    "motion_hr_correlation": F.corr("enmo_mean_g", "hr_mean_bpm"),
    "synthetic_minutes": F.sum(F.col("is_synthetic").cast("int")),
}.items():
    metrics = metrics.withColumn(name, expression.over(ordered))
metrics = (metrics.where("minute_offset >= 1440 AND (minute_offset + 1) % 60 = 0")
           .withColumn("window_end_offset_minutes", F.col("minute_offset") + 1)
           .withColumn("window_start_offset_minutes", F.col("window_end_offset_minutes") - 1440)
           .withColumn("synthetic_fraction", F.col("synthetic_minutes") / 1440)
           .withColumn("hr_coverage_fraction", F.col("hr_minutes") / 1440)
           .withColumn("wearable_risk_indicator", F.lit(None).cast("double"))
           .withColumn("risk_status", F.lit("pending_24h_model_not_a_glucose_measurement")))
metrics = metrics.select("fixture_id", "demo_participant_key", "source_participant_key", "source_dataset",
    "window_start_offset_minutes", "window_end_offset_minutes", "clock_minute", "unit_status",
    "window_minutes", "motion_mean_g", "motion_std_g", "motion_p90_g", "temperature_mean_c_24h",
    "temperature_std_c_24h", "hr_mean_bpm_24h", "hr_coverage_fraction", "motion_hr_correlation",
    "synthetic_minutes", "synthetic_fraction", "wearable_risk_indicator", "risk_status", "demo_only", "training_eligible")
save(metrics, "history_metrics_24h")
metrics = spark.read.table(f"{SCHEMA}.history_metrics_24h").where(F.col("fixture_id") == fixture)
if metrics.count() != len(expected_people) * 168 or metrics.where("window_minutes <> 1440").limit(1).count():
    raise ValueError("Expected seven full days of complete hourly trailing metrics per person")

manifest = (bank.groupBy("fixture_id", "demo_participant_key", "source_participant_key").agg(
    F.count("*").alias("total_minutes"), F.sum(F.col("is_synthetic").cast("int")).alias("synthetic_minutes"),
    F.sum(F.when(F.col("phase") == "replay", 1).otherwise(0)).alias("reserved_replay_minutes"))
    .withColumn("stream_enabled", F.lit(False))
    .withColumn("preloaded_days", F.lit(8)).withColumn("trend_days", F.lit(7))
    .withColumn("generation_policy", F.lit("same-person-clock-template-v1")))
save(manifest, "manifest")
dbutils.notebook.exit(json.dumps({"fixture_id": fixture, "participants": len(expected_people),
    "minutes_per_person": 12960, "precomputed_hourly_metrics_per_person": 168,
    "stream_enabled": False, "risk_status": "requires_separate_24h_model",
    "manifest": [row.asDict() for row in manifest.orderBy("demo_participant_key").collect()]}))
