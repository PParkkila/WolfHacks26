"""Small subject-level model features and isolated labels; no manual writes.

Predictions summarize the completed wearable observation interval. They are
not instantaneous CGM replacements or forecasts. QC cutoffs below are declared
engineering choices, not exercise or clinical thresholds.
"""

from pyspark import pipelines as dp
from pyspark.sql import functions as F

ROOT = "/Volumes/workspace/wolfhacks_raw/source_files/big_ideas"
NTZ = {"delta.feature.timestampNtz": "supported"}
FEATURE_VERSION = "motion-temperature-subject-v1"


@dp.materialized_view(name="workspace.wolfhacks_bronze.cgm_target_source")
def cgm_target_source():
    # Do not expose Patient Info, Device Info, or other export metadata.
    frame = spark.read.option("header", True).option("inferSchema", False).csv(
        f"{ROOT}/[0-9][0-9][0-9]/Dexcom_*.csv"
    )
    return (frame.select(
        F.col("Timestamp (YYYY-MM-DDThh:mm:ss)").alias("datetime_raw"),
        F.col("Event Type").alias("event_type"),
        F.col("Glucose Value (mg/dL)").alias("glucose_raw"),
        F.col("_metadata.file_path").alias("source_file"),
    ).withColumn("subject_id", F.regexp_extract("source_file", r"/([0-9]{3})/[^/]+$", 1))
      .withColumn("participant_key", F.concat(F.lit("big_ideas:"), F.col("subject_id"))))


@dp.materialized_view(name="workspace.wolfhacks_bronze.cohort_label_source")
def cohort_label_source():
    return (spark.read.option("header", True).option("inferSchema", False)
            .csv(f"{ROOT}/Demographics.csv").toDF("id_raw", "gender_raw", "hba1c_raw")
            .withColumn("subject_id", F.lpad(F.col("id_raw"), 3, "0"))
            .withColumn("participant_key", F.concat(F.lit("big_ideas:"), F.col("subject_id"))))


@dp.materialized_view(name="workspace.wolfhacks_silver.cgm_targets", table_properties=NTZ)
@dp.expect_or_fail("consistent_cgm_duplicates", "distinct_glucose_values = 1")
def cgm_targets():
    values = (spark.read.table("workspace.wolfhacks_bronze.cgm_target_source")
              .where(F.col("event_type") == "EGV")
              .withColumn("event_ts", F.expr("try_cast(datetime_raw AS TIMESTAMP_NTZ)"))
              .withColumn("glucose_mg_dl", F.expr("try_cast(glucose_raw AS DOUBLE)"))
              .where(F.col("event_ts").isNotNull() & (F.col("glucose_mg_dl") > 0)
                     & (F.col("glucose_mg_dl") < F.lit(float("inf")))
                     & ~F.isnan("glucose_mg_dl")))
    return values.groupBy("participant_key", "event_ts").agg(
        F.avg("glucose_mg_dl").alias("glucose_mg_dl"),
        F.countDistinct("glucose_mg_dl").alias("distinct_glucose_values"),
        F.count("*").alias("source_rows"),
    )


@dp.materialized_view(name="workspace.wolfhacks_features.metabolic_features", table_properties=NTZ)
def metabolic_features():
    minute = spark.read.table("workspace.wolfhacks_silver.shared_sensor_minute_pilot")
    usable = ((F.col("acc_sample_ratio") >= .8) & (F.col("acc_sample_ratio") <= 1)
              & (F.col("temperature_sample_ratio") >= .8)
              & (F.col("temperature_sample_ratio") <= 1)
              & F.col("enmo_mean_g").isNotNull() & F.col("temperature_mean_c").isNotNull())
    frame = minute.withColumn("usable", usable).withColumn("usable_minute", F.when(usable, F.col("minute_ts")))
    return (frame.groupBy("source_dataset", "subject_id", "participant_key").agg(
        F.min("usable_minute").alias("observation_start"),
        F.max("usable_minute").alias("observation_last_minute"),
        F.count("*").alias("observed_minutes"),
        F.count("usable_minute").alias("usable_minutes"),
        F.avg(F.when(usable, F.col("enmo_mean_g"))).alias("motion_mean_g"),
        F.percentile_approx(F.when(usable, F.col("enmo_mean_g")), .9, 10000).alias("motion_p90_g"),
        F.avg(F.when(usable, F.col("temperature_mean_c"))).alias("temperature_mean_c"),
        F.stddev_samp(F.when(usable, F.col("temperature_mean_c"))).alias("temperature_std_c"),
        F.first("unit_status").alias("unit_status"),
    ).withColumn("observation_end", F.col("observation_last_minute") + F.expr("INTERVAL 1 MINUTE"))
      .withColumn("usable_fraction_of_observed", F.col("usable_minutes") / F.col("observed_minutes"))
      .withColumn("feature_version", F.lit(FEATURE_VERSION))
      .withColumn("eligible", (F.col("usable_minutes") >= 1440)
                  & (F.col("usable_fraction_of_observed") >= .8))
      .withColumn("eligibility_policy", F.lit("v1: >=1440 usable minutes; >=80% of observed minutes")))


@dp.materialized_view(name="workspace.wolfhacks_silver.subject_targets", table_properties=NTZ)
def subject_targets():
    features = (spark.read.table("workspace.wolfhacks_features.metabolic_features")
                .where(F.col("source_dataset") == "big_ideas")
                .select("participant_key", "observation_start", "observation_end"))
    cgm = spark.read.table("workspace.wolfhacks_silver.cgm_targets")
    # The range depends only on wearable availability; glucose never determines
    # feature construction or eligibility. No joining between different cohorts.
    aligned = (features.join(cgm, "participant_key", "left")
               .where((F.col("event_ts") >= F.col("observation_start"))
                      & (F.col("event_ts") < F.col("observation_end"))))
    glucose = aligned.groupBy("participant_key").agg(
        F.avg("glucose_mg_dl").alias("mean_cgm_mg_dl"),
        F.count("glucose_mg_dl").alias("cgm_samples"),
        F.min("event_ts").alias("first_cgm"), F.max("event_ts").alias("last_cgm"),
    )
    labels = (spark.read.table("workspace.wolfhacks_bronze.cohort_label_source")
              .withColumn("hba1c", F.expr("try_cast(hba1c_raw AS DOUBLE)"))
              .select("participant_key", "hba1c",
                      F.when(F.col("hba1c").between(5.2, 5.6), 0)
                       .when(F.col("hba1c").between(5.7, 6.4), 1).alias("cohort_label")))
    return (features.join(glucose, "participant_key", "left").join(labels, "participant_key", "left")
            .withColumn("cgm_interval_coverage", F.col("cgm_samples") * 300 /
                        F.expr("timestampdiff(SECOND, observation_start, observation_end)"))
            .withColumn("classification_target_version", F.lit("study-hba1c-groups-v1"))
            .withColumn("regression_target_version", F.lit("observed-interval-mean-cgm-v1")))


@dp.materialized_view(name="workspace.wolfhacks_features.metabolic_features_v2", table_properties=NTZ)
def metabolic_features_v2():
    """Wearable distribution/coupling features, independent of all outcomes.

    First-harmonic amplitudes describe the source-clock daily pattern, not
    diagnosed sleep or exercise. Equal weighting of all 24 hourly means avoids
    weighting heavily recorded hours more; require >=30 usable minutes/hour.
    """
    base = spark.read.table("workspace.wolfhacks_features.metabolic_features")
    minute = (spark.read.table("workspace.wolfhacks_silver.shared_sensor_minute_pilot")
              .where(F.col("acc_sample_ratio").between(.8, 1)
                     & F.col("temperature_sample_ratio").between(.8, 1)
                     & F.col("enmo_mean_g").isNotNull()
                     & F.col("temperature_mean_c").isNotNull()))
    extra = minute.groupBy("participant_key").agg(
        F.percentile_approx("enmo_mean_g", .5, 10000).alias("motion_median_g"),
        F.stddev_samp("enmo_mean_g").alias("motion_std_g"),
        F.percentile_approx("enmo_mean_g", .99, 10000).alias("motion_p99_g"),
        F.percentile_approx("temperature_mean_c", .1, 10000).alias("temperature_p10_c"),
        F.percentile_approx("temperature_mean_c", .9, 10000).alias("temperature_p90_c"),
        F.corr("enmo_mean_g", "temperature_mean_c").alias("motion_temperature_corr"),
    )
    hourly = (minute.withColumn("hour", F.hour("minute_ts"))
              .groupBy("participant_key", "hour").agg(
                  F.count("*").alias("minutes"),
                  F.avg("enmo_mean_g").alias("motion"),
                  F.avg("temperature_mean_c").alias("temperature"))
              .where(F.col("minutes") >= 30)
              .withColumn("angle", F.col("hour") * F.lit(2 * 3.141592653589793 / 24)))
    cycles = hourly.groupBy("participant_key").agg(
        F.count("*").alias("clock_hours_covered"),
        *[expression for signal in ("motion", "temperature") for expression in (
            F.avg(F.col(signal) * F.sin("angle")).alias(f"{signal}_sine"),
            F.avg(F.col(signal) * F.cos("angle")).alias(f"{signal}_cosine"),
        )],
    )
    for signal, unit in (("motion", "g"), ("temperature", "c")):
        cycles = cycles.withColumn(f"{signal}_daily_amplitude_{unit}",
            F.when(F.col("clock_hours_covered") == 24,
                   2 * F.sqrt(F.col(f"{signal}_sine") ** 2 + F.col(f"{signal}_cosine") ** 2)))
    return (base.join(extra, "participant_key", "left")
            .join(cycles.select("participant_key", "clock_hours_covered",
                                "motion_daily_amplitude_g", "temperature_daily_amplitude_c"),
                  "participant_key", "left")
            .withColumn("feature_version", F.lit("motion-temperature-subject-v2")))
