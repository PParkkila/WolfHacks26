"""Lakeflow pilot: one BIG IDEAs subject, one row per observed ACC minute.

Add this source file to a serverless Lakeflow ETL pipeline with default catalog
``workspace`` and schema ``wolfhacks_silver``. This pilot reads the Volume
directly; the full pipeline will introduce Bronze Delta source tables first.
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F

SOURCE_ROOT = "/Volumes/workspace/wolfhacks_raw/source_files/big_ideas/001"
SUBJECT_ID = "001"
E4_COUNTS_PER_G = 64.0
EXPECTED_ACC_SAMPLES_PER_MINUTE = 32 * 60


def source_clock_minute(timestamp_col):
    """Truncate a source-clock TIMESTAMP_NTZ without converting it to UTC."""
    return F.make_timestamp_ntz(
        F.year(timestamp_col),
        F.month(timestamp_col),
        F.dayofmonth(timestamp_col),
        F.hour(timestamp_col),
        F.minute(timestamp_col),
        F.lit(0),
    )


@dp.materialized_view(
    name="activity_minute_pilot",
    table_properties={"delta.feature.timestampNtz": "supported"},
    comment=(
        "BIG IDEAs 001 minute-level movement and heart rate pilot. "
        "Timestamps are source-clock values with unknown timezone, not UTC."
    ),
)
@dp.expect("valid_motion_summary", "enmo_mean_g >= 0 AND enmo_p95_g >= 0")
@dp.expect(
    "valid_acc_coverage", "acc_coverage_fraction BETWEEN 0.0 AND 1.0"
)
def activity_minute_pilot():
    acc_csv = spark.read.option("header", True).csv(
        f"{SOURCE_ROOT}/ACC_{SUBJECT_ID}.csv"
    )
    hr_csv = spark.read.option("header", True).csv(
        f"{SOURCE_ROOT}/HR_{SUBJECT_ID}.csv"
    )

    # Source headers contain leading spaces, and HR may start with a BOM.
    acc_csv = acc_csv.toDF("datetime_raw", "acc_x_raw", "acc_y_raw", "acc_z_raw")
    hr_csv = hr_csv.toDF("datetime_raw", "hr_raw")

    # TIMESTAMP_NTZ preserves the dataset's shifted source clock. It must not
    # be interpreted as an actual UTC instant without timezone documentation.
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

    vector_g = F.sqrt(
        F.pow(F.col("acc_x") / E4_COUNTS_PER_G, 2)
        + F.pow(F.col("acc_y") / E4_COUNTS_PER_G, 2)
        + F.pow(F.col("acc_z") / E4_COUNTS_PER_G, 2)
    )
    acc = acc.withColumn(
        "enmo_g", F.greatest(vector_g - F.lit(1.0), F.lit(0.0))
    )
    acc_minute = (
        acc.withColumn("minute_ts", source_clock_minute(F.col("event_ts")))
        .groupBy("minute_ts")
        .agg(
            F.count("*").alias("acc_samples"),
            F.avg("enmo_g").alias("enmo_mean_g"),
            F.expr("percentile_approx(enmo_g, 0.95, 1000)").alias(
                "enmo_p95_g"
            ),
        )
        .withColumn(
            "acc_coverage_fraction",
            F.least(
                F.col("acc_samples") / F.lit(EXPECTED_ACC_SAMPLES_PER_MINUTE),
                F.lit(1.0),
            ),
        )
    )

    # The HR CSV stores only minute timestamps, with multiple rows per minute.
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

    # Keep all observed ACC minutes. A missing HR reading stays NULL, and
    # missing ACC minutes are not manufactured as zero activity.
    return (
        acc_minute.join(hr_minute, "minute_ts", "left")
        .withColumn("source_dataset", F.lit("big_ideas"))
        .withColumn("subject_id", F.lit(SUBJECT_ID))
        .withColumn("participant_key", F.lit(f"big_ideas:{SUBJECT_ID}"))
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
