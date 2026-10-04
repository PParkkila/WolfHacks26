# Databricks notebook source
"""Read-only BIG IDEAs activity/heart-rate pilot for one subject.

Import this file as a Databricks notebook and run it on serverless compute.
It creates a DataFrame and a temporary view, not a persistent table.
"""

from pathlib import Path

from pyspark.sql import functions as F

dbutils.widgets.text(
    "volume_root", "/Volumes/workspace/wolfhacks_raw/source_files"
)
dbutils.widgets.text("subject_id", "001")

volume_root = Path(dbutils.widgets.get("volume_root").strip())
subject_id = dbutils.widgets.get("subject_id").strip()
if not (len(subject_id) == 3 and subject_id.isdigit()):
    raise ValueError("subject_id must be a three-digit BIG IDEAs subject ID")

subject_root = volume_root / "big_ideas" / subject_id
acc_path = subject_root / f"ACC_{subject_id}.csv"
hr_path = subject_root / f"HR_{subject_id}.csv"
for path in (acc_path, hr_path):
    if not path.is_file():
        raise FileNotFoundError(f"Upload this source CSV first: {path}")

# The BIG IDEAs wristband is an Empatica E4: its raw ACC count of 64 is 1 g.
# Keep the conversion explicit; do not apply it to the different IMU50 device.
E4_COUNTS_PER_G = 64.0
EXPECTED_ACC_SAMPLES_PER_MINUTE = 32 * 60


def source_clock_minute(timestamp_col):
    """Truncate a source-clock TIMESTAMP_NTZ without assigning a timezone."""
    return F.make_timestamp_ntz(
        F.year(timestamp_col),
        F.month(timestamp_col),
        F.dayofmonth(timestamp_col),
        F.hour(timestamp_col),
        F.minute(timestamp_col),
        F.lit(0),
    )


acc_csv = spark.read.option("header", True).csv(str(acc_path))
hr_csv = spark.read.option("header", True).csv(str(hr_path))
if len(acc_csv.columns) != 4 or len(hr_csv.columns) != 2:
    raise ValueError(
        f"Unexpected CSV widths: ACC={acc_csv.columns}, HR={hr_csv.columns}"
    )

# Rename by position because the source headers have leading spaces and HR may
# include a UTF-8 byte-order mark. to_timestamp_ntz/try_cast reject bad values
# as NULL instead of silently treating text as a measurement.
acc_csv = acc_csv.toDF("datetime_raw", "acc_x_raw", "acc_y_raw", "acc_z_raw")
hr_csv = hr_csv.toDF("datetime_raw", "hr_raw")

acc = acc_csv.select(
    F.to_timestamp_ntz(
        F.col("datetime_raw"), F.lit("yyyy-MM-dd HH:mm:ss.SSSSSS")
    ).alias("event_ts"),
    F.expr("try_cast(acc_x_raw AS DOUBLE)").alias("acc_x"),
    F.expr("try_cast(acc_y_raw AS DOUBLE)").alias("acc_y"),
    F.expr("try_cast(acc_z_raw AS DOUBLE)").alias("acc_z"),
).where(
    F.col("event_ts").isNotNull()
    & F.col("acc_x").isNotNull()
    & F.col("acc_y").isNotNull()
    & F.col("acc_z").isNotNull()
)

acc = acc.withColumn(
    "vector_g",
    F.sqrt(
        F.pow(F.col("acc_x") / E4_COUNTS_PER_G, 2)
        + F.pow(F.col("acc_y") / E4_COUNTS_PER_G, 2)
        + F.pow(F.col("acc_z") / E4_COUNTS_PER_G, 2)
    ),
).withColumn(
    "enmo_g", F.greatest(F.col("vector_g") - F.lit(1.0), F.lit(0.0))
)

acc_minute = (
    acc.withColumn("minute_ts", source_clock_minute(F.col("event_ts")))
    .groupBy("minute_ts")
    .agg(
        F.count("*").alias("acc_samples"),
        F.avg("enmo_g").alias("enmo_mean_g"),
        F.expr("percentile_approx(enmo_g, 0.95, 1000)").alias("enmo_p95_g"),
    )
    .withColumn(
        "acc_coverage_fraction",
        F.least(
            F.col("acc_samples") / F.lit(EXPECTED_ACC_SAMPLES_PER_MINUTE),
            F.lit(1.0),
        ),
    )
)

# HR source timestamps have minute precision, even though some minutes contain
# multiple readings. Average within the minute; do not invent sub-minute times.
hr = hr_csv.select(
    F.to_timestamp_ntz(F.col("datetime_raw"), F.lit("M/d/yy H:mm")).alias(
        "event_ts"
    ),
    F.expr("try_cast(hr_raw AS DOUBLE)").alias("hr_bpm"),
).where(F.col("event_ts").isNotNull() & (F.col("hr_bpm") > 0))

hr_minute = (
    hr.withColumn("minute_ts", source_clock_minute(F.col("event_ts")))
    .groupBy("minute_ts")
    .agg(
        F.count("*").alias("hr_samples"),
        F.avg("hr_bpm").alias("hr_mean_bpm"),
    )
)

activity_minute = (
    acc_minute.join(hr_minute, "minute_ts", "left")
    .withColumn("source_dataset", F.lit("big_ideas"))
    .withColumn("subject_id", F.lit(subject_id))
    .withColumn("participant_key", F.lit(f"big_ideas:{subject_id}"))
    .select(
        "source_dataset",
        "subject_id",
        "participant_key",
        "minute_ts",
        "acc_samples",
        "acc_coverage_fraction",
        "enmo_mean_g",
        "enmo_p95_g",
        "hr_samples",
        "hr_mean_bpm",
    )
)

# A temporary view makes the preview easy to explore without writing Delta.
activity_minute.createOrReplaceTempView("activity_minute_pilot")

display(
    activity_minute.agg(
        F.count("*").alias("minutes_with_acc"),
        F.sum(F.when(F.col("hr_mean_bpm").isNotNull(), 1).otherwise(0)).alias(
            "minutes_with_acc_and_hr"
        ),
        F.min("minute_ts").alias("first_minute"),
        F.max("minute_ts").alias("last_minute"),
        F.expr("percentile_approx(acc_coverage_fraction, 0.5)").alias(
            "median_acc_coverage_fraction"
        ),
    )
)
display(activity_minute.orderBy("minute_ts").limit(20))
