"""Bronze -> shared minute motion/temperature for staged participants.

IMU50 g/Celsius are user-authorized inferences, NOT documented export units.
Do not use device IDs, cohort IDs, or unit-status columns as model features.
This preserves all CSV values in Bronze and original ordered files in the
Volume. Minute aggregation is order-independent; waveform/PPG processing must
read those ordered originals, not invent order from a Spark row identifier.
"""

from functools import reduce

from pyspark import pipelines as dp
from pyspark.sql import functions as F

ROOT = "/Volumes/workspace/wolfhacks_raw/source_files"
BRONZE = "workspace.wolfhacks_bronze"
SILVER = "workspace.wolfhacks_silver"
UNIT_POLICY_VERSION = "sensor-units-v1-provisional"
NTZ_PROPERTIES = {"delta.feature.timestampNtz": "supported"}

# Scaling is fixed from physical-unit evidence, not fit to cohort statistics
# or model outcomes. No distribution matching or per-subject gain adjustment.
SOURCES = {
    "big_ideas": {
        "subject": None, "acc_scale_to_g": 1.0 / 64.0, "acc_hz": 32,
        "temperature_hz": 4.0, "unit_status": "documented_e4",
        "acc_file": "big_ideas/[0-9][0-9][0-9]/ACC_*.csv",
        "temperature_file": "big_ideas/[0-9][0-9][0-9]/TEMP_*.csv",
        "acc_fields": ["datetime_raw", "acc_x_raw", "acc_y_raw", "acc_z_raw"],
    },
    "imu50": {
        "subject": "00", "acc_scale_to_g": 1.0, "acc_hz": 128,
        "temperature_hz": 1.0 / 60.0, "unit_status": "inferred_g_celsius",
        "acc_file": "imu50/00/00_imu.csv",
        "temperature_file": "imu50/00/00_temperature.csv",
        "acc_fields": ["datetime_raw", "acc_x_raw", "acc_y_raw", "acc_z_raw",
                       "gyro_x_raw", "gyro_y_raw", "gyro_z_raw"],
    },
}


def register_raw(dataset, kind, relative_path, fields, subject):
    # Function arguments bind each source independently of the registration loop.
    @dp.materialized_view(
        name=f"{BRONZE}.{dataset}_{kind}_pilot",
        comment="Original CSV field values; no unit conversion or row deduplication.",
    )
    def raw_csv():
        source = (spark.read.option("header", True).option("inferSchema", False)
                  .option("mode", "FAILFAST").csv(f"{ROOT}/{relative_path}"))
        if len(source.columns) != len(fields):
            raise ValueError(f"Unexpected column count for {relative_path}")
        return (
            source.select("*", F.col("_metadata.file_path").alias("source_file"))
            .toDF(*fields, "source_file")
            .withColumn("source_dataset", F.lit(dataset))
            .withColumn("subject_id", F.lit(subject) if subject else
                        F.regexp_extract("source_file", r"/([0-9]{3})/[^/]+$", 1))
            .withColumn("participant_key", F.concat(F.lit(f"{dataset}:"), F.col("subject_id")))
        )


for dataset, spec in SOURCES.items():
    register_raw(dataset, "acc", spec["acc_file"], spec["acc_fields"], spec["subject"])
    register_raw(dataset, "temperature", spec["temperature_file"],
                 ["datetime_raw", "temperature_raw"], spec["subject"])


def minute_key(column):
    return F.make_timestamp_ntz(F.year(column), F.month(column), F.dayofmonth(column),
                                F.hour(column), F.minute(column), F.lit(0))


def finite(column):
    return column.isNotNull() & ~F.isnan(column) & (F.abs(column) < F.lit(float("inf")))


def typed_acc(dataset, spec):
    frame = spark.read.table(f"{BRONZE}.{dataset}_acc_pilot").withColumn(
        "event_ts", F.expr("try_cast(datetime_raw AS TIMESTAMP_NTZ)")
    )
    for axis in ("x", "y", "z"):
        frame = frame.withColumn(f"acc_{axis}_g", F.expr(
            f"try_cast(acc_{axis}_raw AS DOUBLE)"
        ) * F.lit(spec["acc_scale_to_g"]))
    axes = [F.col(f"acc_{axis}_g") for axis in ("x", "y", "z")]
    valid = reduce(lambda a, b: a & b, [finite(axis) for axis in axes])
    return (frame.withColumn("valid_numeric", valid)
            .withColumn("vector_g", F.when(valid, F.sqrt(sum(axis * axis for axis in axes))))
            .withColumn("enmo_g", F.when(valid, F.greatest(F.col("vector_g") - 1.0, F.lit(0.0)))))


def typed_temperature(dataset):
    return (spark.read.table(f"{BRONZE}.{dataset}_temperature_pilot")
            .withColumn("event_ts", F.expr("try_cast(datetime_raw AS TIMESTAMP_NTZ)"))
            .withColumn("temperature_c", F.expr("try_cast(temperature_raw AS DOUBLE)"))
            .withColumn("valid_numeric", finite(F.col("temperature_c"))))


def source_minutes(dataset, spec):
    keys = ["source_dataset", "subject_id", "participant_key", "minute_ts"]
    acc = (typed_acc(dataset, spec).where(F.col("event_ts").isNotNull())
           .withColumn("minute_ts", minute_key(F.col("event_ts")))
           .groupBy(*keys).agg(
               F.count("*").alias("acc_rows"),
               F.count("enmo_g").alias("acc_samples"),
               F.avg("vector_g").alias("vector_mean_g"),
               F.avg("enmo_g").alias("enmo_mean_g"),
               F.stddev_samp("enmo_g").alias("enmo_std_g"),
               F.expr("percentile_approx(enmo_g, 0.95, 1000)").alias("enmo_p95_g"),
           ))
    temperature = (typed_temperature(dataset).where(F.col("event_ts").isNotNull())
                   .withColumn("minute_ts", minute_key(F.col("event_ts")))
                   .groupBy(*keys).agg(
                       F.count("*").alias("temperature_rows"),
                       F.count(F.when(F.col("valid_numeric"), 1)).alias("temperature_samples"),
                       F.avg(F.when(F.col("valid_numeric"), F.col("temperature_c")))
                       .alias("temperature_mean_c"),
                   ))
    # Outer join preserves temperature-only minutes. No forward filling and no
    # resampling of 1/min temperature into fake 4 Hz readings.
    result = acc.join(temperature, keys, "full")
    for column in ("acc_rows", "acc_samples", "temperature_rows", "temperature_samples"):
        result = result.withColumn(column, F.coalesce(F.col(column), F.lit(0)))
    return (result
            .withColumn("acc_invalid_rows", F.col("acc_rows") - F.col("acc_samples"))
            .withColumn("temperature_invalid_rows", F.col("temperature_rows") - F.col("temperature_samples"))
            .withColumn("expected_acc_samples", F.lit(spec["acc_hz"] * 60))
            .withColumn("acc_sample_ratio", F.col("acc_samples") / F.col("expected_acc_samples"))
            .withColumn("acc_coverage_fraction", F.least(F.col("acc_sample_ratio"), F.lit(1.0)))
            .withColumn("acc_overfull", F.col("acc_sample_ratio") > 1)
            .withColumn("expected_temperature_samples", F.lit(spec["temperature_hz"] * 60))
            .withColumn("temperature_sample_ratio", F.col("temperature_samples") / F.col("expected_temperature_samples"))
            .withColumn("acc_unit", F.lit("g"))
            .withColumn("temperature_unit", F.lit("degC"))
            .withColumn("unit_status", F.lit(spec["unit_status"]))
            .withColumn("unit_policy_version", F.lit(UNIT_POLICY_VERSION))
            .withColumn("cross_device_validated", F.lit(False))
            .withColumn("hr_mean_bpm", F.lit(None).cast("double")))


@dp.materialized_view(
    name=f"{SILVER}.shared_sensor_minute_pilot",
    table_properties=NTZ_PROPERTIES,
    comment="Common units only, not calibrated device equivalence. IMU50 g/Celsius inferred.",
)
@dp.expect("valid_enmo", "enmo_mean_g IS NULL OR enmo_mean_g >= 0")
@dp.expect("valid_coverage", "acc_coverage_fraction BETWEEN 0 AND 1")
@dp.expect("expected_acc_count", "NOT acc_overfull")
def shared_sensor_minute_pilot():
    frames = [source_minutes(dataset, spec) for dataset, spec in SOURCES.items()]
    return frames[0].unionByName(frames[1])


@dp.materialized_view(name=f"{SILVER}.sensor_parse_audit_pilot")
def sensor_parse_audit_pilot():
    summaries = []
    for dataset, spec in SOURCES.items():
        for kind, frame in (("acc", typed_acc(dataset, spec)),
                            ("temperature", typed_temperature(dataset))):
            summaries.append(frame.groupBy("source_dataset", "participant_key").agg(
                F.count("*").alias("raw_rows"),
                F.sum(F.when(F.col("event_ts").isNull(), 1).otherwise(0)).alias("invalid_timestamp_rows"),
                F.sum(F.when(~F.col("valid_numeric"), 1).otherwise(0)).alias("invalid_numeric_rows"),
            ).withColumn("signal", F.lit(kind)))
    return reduce(lambda left, right: left.unionByName(right), summaries)
