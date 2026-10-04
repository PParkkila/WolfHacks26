"""Shared past-only 24-hour features for real-data training and demo inference."""

import numpy as np

FEATURE_VERSION = "wearable-24h-v1"
FEATURES = ["motion_mean_g", "motion_p90_g", "temperature_mean_c", "temperature_std_c",
            "motion_median_g", "motion_std_g", "motion_p99_g", "temperature_p10_c",
            "temperature_p90_c", "motion_temperature_corr", "motion_daily_amplitude_g",
            "temperature_daily_amplitude_c"]


def window_features(times, motion, temperature, end):
    """Integer minute coordinates; [end-1440, end). Missing minutes stay missing.

    Engineering coverage gate: >=80% of elapsed minutes and >=30 valid minutes
    in each of the 24 relative hour bins. No interpolation or future values.
    """
    left, right = np.searchsorted(times, [end - 1440, end])
    t, a, c = times[left:right], motion[left:right], temperature[left:right]
    if len(t) < 1152 or not np.isfinite(a).all() or not np.isfinite(c).all():
        return None
    hours = ((t - (end - 1440)) // 60).astype(int)
    counts = np.bincount(hours, minlength=24)
    if (counts < 30).any():
        return None
    angle = 2 * np.pi * np.arange(24) / 24

    def amplitude(values):
        means = np.bincount(hours, weights=values, minlength=24) / counts
        return float(2 * np.hypot(np.mean(means * np.cos(angle)), np.mean(means * np.sin(angle))))

    corr = float(np.corrcoef(a, c)[0, 1]) if np.std(a) > 1e-12 and np.std(c) > 1e-12 else 0.0
    values = [np.mean(a), np.quantile(a, .9), np.mean(c), np.std(c, ddof=1),
              np.median(a), np.std(a, ddof=1), np.quantile(a, .99), np.quantile(c, .1),
              np.quantile(c, .9), corr, amplitude(a), amplitude(c)]
    return dict(zip(FEATURES, map(float, values)))


def arrays(frame, time_column):
    frame = frame.sort_values(time_column)
    times = frame[time_column].to_numpy(dtype=np.int64)
    if len(times) > 1 and (np.diff(times) <= 0).any():
        raise ValueError("Minute keys must be unique and increasing")
    return times, frame.enmo_mean_g.to_numpy(float), frame.temperature_mean_c.to_numpy(float)


def score_records(records, minutes, bundle):
    """Score only published historical/live windows from this session's minutes.

    Known training participants use their nested-LOSO fold model, never a model
    trained on their own source observations. Synthetic replay is application
    only, and its score behavior is not an evaluation result.
    """
    if bundle["feature_version"] != FEATURE_VERSION or bundle["features"] != FEATURES:
        raise ValueError("Model/feature contract mismatch")
    grouped = {key: arrays(part, "minute_offset") for key, part in minutes.groupby("source_participant_key")}
    for row in records:
        key = row["source_participant_key"]
        features = window_features(*grouped[key], row["window_end_offset_minutes"])
        if features is None:
            raise ValueError(f"Cannot score incomplete 24-hour demo window: {key}")
        item = bundle["held_out"].get(key, bundle["final"])
        vector = np.array([[features[name] for name in FEATURES]])
        model = item["model"]
        score = float(model.predict_proba(vector)[0, list(model.classes_).index(1)]) * 100
        if not np.isfinite(score) or not 0 <= score <= 100:
            raise ValueError("Invalid risk score")
        row.update({
            "wearable_risk_indicator": score,
            "risk_status": "experimental_demo_cohort_similarity",
            "risk_model_version": bundle["model_version"],
            "risk_feature_version": FEATURE_VERSION,
            "risk_model_name": item["name"],
            "risk_evaluation": ("held_out_participant_demo" if key in bundle["held_out"]
                                else "application_unvalidated"),
            "risk_outside_training_range": bool(((vector[0] < item["minimum"]) |
                                                 (vector[0] > item["maximum"])).any()),
            "risk_cross_device_validated": False,
            "risk_score_unit": "index_0_100_not_clinical_probability",
        })
    by_key = {(r["participant_key"], r["window_end_offset_minutes"]): r for r in records}
    for row in records:
        previous = by_key.get((row["participant_key"], row["window_end_offset_minutes"] - 1440))
        row["risk_change_24h_points"] = (row["wearable_risk_indicator"] - previous["wearable_risk_indicator"]
                                         if previous else None)
    return records
