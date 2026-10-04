# Databricks notebook source
"""Train/evaluate recent wearable-pattern resemblance on real 24-hour windows."""

# COMMAND ----------
# MAGIC %pip install "scikit-learn==1.5.2" "mlflow-skinny>=2.22,<3"

# COMMAND ----------
dbutils.library.restartPython()

# COMMAND ----------
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import joblib
import mlflow
import numpy as np
import pandas as pd
from pyspark.sql import functions as F
from sklearn.base import clone
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import LeaveOneGroupOut, StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, "/Workspace/Users/pbparkki@ncsu.edu/WolfHacks26/databricks/tiger")
from rolling_risk import FEATURES, FEATURE_VERSION, arrays, window_features

spark.conf.set("spark.sql.session.timeZone", "UTC")
expected = {f"big_ideas:{i:03d}" for i in range(1, 17)} - {"big_ideas:015"}
source = (spark.table("workspace.wolfhacks_silver.shared_sensor_minute_pilot")
          .where(F.col("participant_key").isin(sorted(expected)))
          .where(F.col("acc_sample_ratio").between(.8, 1) & F.col("temperature_sample_ratio").between(.8, 1))
          .select("participant_key", "minute_ts", "enmo_mean_g", "temperature_mean_c")
          .limit(500001).toPandas())
if len(source) > 500000 or set(source.participant_key) != expected:
    raise ValueError("Unexpected real source roster/size")
source["minute_index"] = pd.to_datetime(source.minute_ts).astype("datetime64[ns]").astype("int64") // 60_000_000_000
labels = spark.table("workspace.wolfhacks_silver.subject_targets").select("participant_key", "cohort_label").toPandas()
label_map = labels.set_index("participant_key").cohort_label.to_dict()
windows = []
for key, part in source.groupby("participant_key"):
    t, a, c = arrays(part, "minute_index")
    first_end = int(((t[0] + 1440 + 59) // 60) * 60)
    for end in range(first_end, int(t[-1] + 1) + 1, 60):
        features = window_features(t, a, c, end)
        if features is not None:
            windows.append({"participant_key": key, "window_end_minute": end,
                            "cohort_label": int(label_map[key]), **features})
data = pd.DataFrame(windows).sort_values(["participant_key", "window_end_minute"]).reset_index(drop=True)
if set(data.participant_key) != expected:
    raise ValueError("Some approved participants have no quality-passing 24-hour windows")
X, y, groups = data[FEATURES].to_numpy(float), data.cohort_label.to_numpy(int), data.participant_key.to_numpy()
if not np.isfinite(X).all():
    raise ValueError("Non-finite features")

# Bounded candidate set fixed before seeing this experiment's results.
models = {
    "prior": DummyClassifier(strategy="prior"),
    "logistic_c01": Pipeline([("scale", StandardScaler()), ("model", LogisticRegression(C=.1, max_iter=2000, random_state=42))]),
    "logistic_c1": Pipeline([("scale", StandardScaler()), ("model", LogisticRegression(C=1, max_iter=2000, random_state=42))]),
    "forest_depth3": RandomForestClassifier(n_estimators=64, max_depth=3, min_samples_leaf=20, random_state=42, n_jobs=1),
}


def weights(g):
    counts = pd.Series(g).value_counts()
    # Each participant contributes equal total weight despite differing coverage.
    return np.array([len(g) / (len(counts) * counts[key]) for key in g])


def fit(name, idx):
    model, w = clone(models[name]), weights(groups[idx])
    if isinstance(model, Pipeline):
        model.fit(X[idx], y[idx], scale__sample_weight=w, model__sample_weight=w)
    else:
        model.fit(X[idx], y[idx], sample_weight=w)
    return model


def predict(model, idx):
    # Equal-prior folds must use the declared 0.5 -> class 1 tie rule, not
    # floating-point differences from per-person sample weights.
    return np.round(model.predict_proba(X[idx])[:, list(model.classes_).index(1)], 12)


def select(idx):
    # Stratify the PERSON roster, then map all their windows into that fold.
    people = np.unique(groups[idx])
    person_labels = np.array([label_map[key] for key in people])
    splits = list(StratifiedKFold(3, shuffle=True, random_state=42).split(people, person_labels))
    scores = {}
    for name in models:
        pred = np.full(len(idx), np.nan)
        for train_people, valid_people in splits:
            fit_idx = idx[np.isin(groups[idx], people[train_people])]
            valid_mask = np.isin(groups[idx], people[valid_people])
            valid_idx = idx[valid_mask]
            assert set(groups[fit_idx]).isdisjoint(groups[valid_idx])
            pred[valid_mask] = predict(fit(name, fit_idx), valid_idx)
        w = weights(groups[idx])
        scores[name] = {"balanced_accuracy": float(balanced_accuracy_score(y[idx], pred >= .5, sample_weight=w)),
                        "log_loss": float(log_loss(y[idx], pred, sample_weight=w, labels=[0, 1]))}
    chosen = min(scores, key=lambda name: (-round(scores[name]["balanced_accuracy"], 6), round(scores[name]["log_loss"], 6)))
    return chosen, scores


def pack(name, idx):
    return {"name": name, "model": fit(name, idx), "minimum": X[idx].min(axis=0), "maximum": X[idx].max(axis=0)}


def evaluate(target, prob, w):
    return {"accuracy": float(accuracy_score(target, prob >= .5, sample_weight=w)),
            "balanced_accuracy": float(balanced_accuracy_score(target, prob >= .5, sample_weight=w)),
            "roc_auc": float(roc_auc_score(target, prob, sample_weight=w)),
            "log_loss": float(log_loss(target, prob, sample_weight=w, labels=[0, 1])),
            "brier": float(brier_score_loss(target, prob, sample_weight=w))}


mlflow.set_tracking_uri("databricks")
mlflow.set_experiment("/Shared/WolfHacks-rolling-risk")
with mlflow.start_run(run_name="real-24h-nested-participant-LOSO-v1") as run:
    version = run.info.run_id
    bundle = {"model_version": version, "feature_version": FEATURE_VERSION, "features": FEATURES, "held_out": {}}
    predictions, baseline = np.full(len(y), np.nan), np.full(len(y), np.nan)
    folds = []
    for train_idx, test_idx in LeaveOneGroupOut().split(X, y, groups):
        key = groups[test_idx[0]]
        assert set(groups[train_idx]).isdisjoint(groups[test_idx])
        chosen, scores = select(train_idx)
        item = pack(chosen, train_idx)
        bundle["held_out"][key] = item
        predictions[test_idx] = predict(item["model"], test_idx)
        baseline[test_idx] = predict(fit("prior", train_idx), test_idx)
        folds.append({"held_out": key, "windows": len(test_idx), "selected": chosen, "inner_scores": scores})
        print(f"Held out {key}: {len(test_idx)} real windows, selected {chosen}", flush=True)
    all_idx = np.arange(len(y))
    chosen, scores = select(all_idx)
    bundle["final"] = pack(chosen, all_idx)
    per_person = pd.DataFrame({"person": groups, "label": y, "score": predictions}).groupby("person").agg(label=("label", "first"), score=("score", "mean"))
    report = {
        "model_version": version, "feature_version": FEATURE_VERSION, "features": FEATURES,
        "training_participants": len(expected), "real_training_windows": len(data),
        "windows_per_participant": {k: int(v) for k, v in data.participant_key.value_counts().sort_index().items()},
        "window_metrics_equal_participant_weight": evaluate(y, predictions, weights(groups)),
        "baseline_window_metrics_equal_participant_weight": evaluate(y, baseline, weights(groups)),
        "participant_mean_score_metrics": evaluate(per_person.label.to_numpy(), per_person.score.to_numpy(), np.ones(len(per_person))),
        "selected_final": chosen, "final_inner_scores": scores, "folds": folds,
        "exclusions": {"big_ideas:015": "Previously approved exclusion: wearable/CGM coverage"},
        "quality_policy": ">=1152 real valid minutes per elapsed 24h; >=30 minutes in every relative hour",
        "interpretation": "0-100 higher-HbA1c study-group resemblance, not diabetes probability or glucose",
        "limitations": ["15 independent labeled participants, not independent windows", "Reused development cohort, not external validation",
                        "No synthetic/demo data used in training or evaluation", "IMU50 units inferred; device transfer unvalidated",
                        "No direct HR input: HR is not available across both datasets", "No clinically validated categories or action thresholds"],
    }
    root = Path(f"/Volumes/workspace/wolfhacks_models/artifacts/{version}")
    root.mkdir(parents=True, exist_ok=False)
    joblib.dump(bundle, root / "rolling_risk.joblib")
    (root / "metadata.json").write_text(json.dumps(report, indent=2))
    mlflow.log_params({"feature_version": FEATURE_VERSION, "training_participants": 15, "windows": len(data), "selected_final": chosen})
    mlflow.log_metrics(report["window_metrics_equal_participant_weight"])
    mlflow.log_dict(report, "evaluation.json")
    mlflow.log_artifacts(str(root), artifact_path="fitted_models")
    # Versioned outputs; only artifacts produced by this code are later loaded.
    data["held_out_score"] = predictions * 100
    data["baseline_score"] = baseline * 100
    data["model_version"] = version
    data["feature_version"] = FEATURE_VERSION
    spark.createDataFrame(data).write.format("delta").mode("append").saveAsTable("workspace.wolfhacks_features.rolling_risk_training_windows")
    release = [(version, FEATURE_VERSION, str(root / "rolling_risk.joblib"), json.dumps(report), datetime.now(timezone.utc).replace(tzinfo=None))]
    spark.createDataFrame(release, "model_version string, feature_version string, artifact_path string, report_json string, created_at timestamp").write.format("delta").mode("append").saveAsTable("workspace.wolfhacks_models.rolling_risk_releases")
    dbutils.jobs.taskValues.set(key="model_version", value=version)
dbutils.notebook.exit(json.dumps(report))
