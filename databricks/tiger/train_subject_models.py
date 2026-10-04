# Databricks notebook source
"""Nested participant-held-out comparison; 15 eligible labeled participants."""

# COMMAND ----------
# MAGIC %pip install "scikit-learn==1.5.2" "mlflow-skinny>=2.22,<3"

# COMMAND ----------
dbutils.library.restartPython()

# COMMAND ----------
from datetime import datetime, timezone
import json
from pathlib import Path
import warnings

import joblib
import mlflow
import numpy as np
from sklearn.base import clone
from sklearn.compose import TransformedTargetRegressor
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.feature_selection import SelectKBest, f_classif
from sklearn.linear_model import BayesianRidge, LogisticRegression, Ridge
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, average_precision_score, brier_score_loss,
                             confusion_matrix, log_loss, mean_absolute_error,
                             mean_squared_error, precision_score, r2_score,
                             recall_score, roc_auc_score)
from sklearn.model_selection import GroupKFold, LeaveOneGroupOut, StratifiedGroupKFold
from sklearn.neural_network import MLPClassifier, MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

spark.conf.set("spark.sql.session.timeZone", "UTC")
dbutils.widgets.dropdown("feature_set", "v1", ["v1", "v2"])
FEATURE_SET = dbutils.widgets.get("feature_set")
if FEATURE_SET not in {"v1", "v2"}:
    raise ValueError("Unknown feature set")
FEATURES = ["motion_mean_g", "motion_p90_g", "temperature_mean_c", "temperature_std_c"]
if FEATURE_SET == "v2":
    FEATURES += ["motion_median_g", "motion_std_g", "motion_p99_g",
                 "temperature_p10_c", "temperature_p90_c", "motion_temperature_corr",
                 "motion_daily_amplitude_g", "temperature_daily_amplitude_c"]
FEATURE_VERSION = f"motion-temperature-subject-{FEATURE_SET}"
FEATURE_TABLE = "workspace.wolfhacks_features.metabolic_features" + ("_v2" if FEATURE_SET == "v2" else "")
EXPERIMENT = "/Shared/WolfHacks-subject-models"
# User-approved on 2026-10-03, before any model fitting or evaluation.
# Preserve the excluded participant in the source, Silver, and feature tables.
EXCLUSIONS = {"big_ideas:015": "74.47% usable wearable minutes; 23.89% CGM interval coverage"}
EXPECTED_TRAINING_KEYS = {f"big_ideas:{subject:03d}" for subject in range(1, 17)} - set(EXCLUSIONS)
data = spark.sql(f"""
    SELECT f.*, t.cohort_label, t.mean_cgm_mg_dl, t.cgm_samples, t.cgm_interval_coverage
    FROM {FEATURE_TABLE} f
    LEFT JOIN workspace.wolfhacks_silver.subject_targets t USING (participant_key)
""").limit(101).toPandas()
if len(data) > 100 or data.participant_key.duplicated().any():
    raise ValueError("Expected bounded unique participant summaries, not sensor/window rows")
if not data.feature_version.eq(FEATURE_VERSION).all():
    raise ValueError("Unexpected feature version")
train = data[data.source_dataset.eq("big_ideas") & ~data.participant_key.isin(EXCLUSIONS)] \
    .sort_values("participant_key").reset_index(drop=True)
application = data[data.source_dataset.eq("imu50")].sort_values("participant_key").reset_index(drop=True)
if set(train.participant_key) != EXPECTED_TRAINING_KEYS or not train.eligible.all():
    raise ValueError("Need the exact 15 approved eligible BIG IDEAs participants")
if application.empty:
    raise ValueError("No IMU50 application participant features available")
if train[["cohort_label", "mean_cgm_mg_dl"]].isna().any().any():
    raise ValueError("Missing training target; do not invent labels")
if not train.cgm_interval_coverage.between(.5, 1.05).all():
    raise ValueError("CGM coverage outside the declared 50–105% engineering gate; inspect targets")
if train.cohort_label.value_counts().to_dict() != {0.0: 7, 1.0: 8}:
    raise ValueError("Cohort label counts differ from the approved 7/8 study groups")
X = train[FEATURES].to_numpy(dtype=float)
if not np.isfinite(X).all():
    raise ValueError("Non-finite subject features; inspect before training")
groups = train.participant_key.to_numpy()


def pipeline(estimator):
    return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), estimator)


models = {
    "classification": {
        "dummy_prior": pipeline(DummyClassifier(strategy="prior")),
        "logistic": pipeline(LogisticRegression(C=1.0, max_iter=1000, random_state=42)),
        "small_forest": pipeline(RandomForestClassifier(
            n_estimators=64, max_depth=2, min_samples_leaf=3, random_state=42, n_jobs=1)),
        "tiny_mlp": pipeline(MLPClassifier(
            hidden_layer_sizes=(4,), alpha=10.0, solver="lbfgs", max_iter=1000,
            early_stopping=False, random_state=42)),
    },
    "regression": {
        "dummy_mean": pipeline(DummyRegressor(strategy="mean")),
        "ridge": pipeline(Ridge(alpha=10.0)),
        "bayesian_ridge": pipeline(BayesianRidge()),
        "small_forest": pipeline(RandomForestRegressor(
            n_estimators=64, max_depth=2, min_samples_leaf=3, random_state=42, n_jobs=1)),
        "tiny_mlp": TransformedTargetRegressor(
            regressor=pipeline(MLPRegressor(hidden_layer_sizes=(4,), alpha=10.0,
                solver="lbfgs", max_iter=1000, early_stopping=False, random_state=42)),
            transformer=StandardScaler()),
    },
}
if FEATURE_SET == "v2":
    # Fixed bounded development comparison, specified before the v2 results.
    # Supervised feature selection is fitted anew inside every training fold.
    models["classification"] = {
        "dummy_prior": pipeline(DummyClassifier(strategy="prior")),
        "logistic_strong": pipeline(LogisticRegression(C=.1, max_iter=2000, random_state=42)),
        "logistic_select3": make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
            SelectKBest(f_classif, k=3), LogisticRegression(C=1, max_iter=2000, random_state=42)),
        "shrinkage_lda": pipeline(LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")),
        "small_forest": pipeline(RandomForestClassifier(
            n_estimators=64, max_depth=2, min_samples_leaf=3, random_state=42, n_jobs=1)),
        "tiny_mlp": pipeline(MLPClassifier(hidden_layer_sizes=(4,), alpha=.1,
            solver="lbfgs", max_iter=2000, early_stopping=False, random_state=42)),
    }
    models["regression"]["tiny_mlp"] = TransformedTargetRegressor(
        regressor=pipeline(MLPRegressor(hidden_layer_sizes=(4,), alpha=1,
            solver="lbfgs", max_iter=2000, early_stopping=False, random_state=42)),
        transformer=StandardScaler())
targets = {"classification": train.cohort_label.to_numpy(dtype=int),
           "regression": train.mean_cgm_mg_dl.to_numpy(dtype=float)}
convergence_warnings = []


def fit(estimator, x, y):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ConvergenceWarning)
        result = clone(estimator).fit(x, y)
    convergence_warnings.extend(str(w.message) for w in caught if issubclass(w.category, ConvergenceWarning))
    return result


def predict(estimator, x, task):
    if task == "classification":
        result = estimator.predict_proba(x)[:, list(estimator.classes_).index(1)]
    else:
        result = estimator.predict(x)
    if not np.isfinite(result).all():
        raise ValueError("Non-finite model predictions; do not publish")
    return result


def loss(y, predicted, task):
    return float(log_loss(y, predicted, labels=[0, 1]) if task == "classification"
                 else mean_absolute_error(y, predicted))


def select_model(x, y, participant_groups, task):
    cv = (StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=42)
          if task == "classification" else GroupKFold(n_splits=3))
    splits = list(cv.split(x, y, participant_groups))
    scores, selection_keys = {}, {}
    for name, estimator in models[task].items():
        pred = np.full(len(y), np.nan)
        for fit_idx, valid_idx in splits:
            assert set(participant_groups[fit_idx]).isdisjoint(participant_groups[valid_idx])
            fitted = fit(estimator, x[fit_idx], y[fit_idx])
            pred[valid_idx] = predict(fitted, x[valid_idx], task)
        scores[name] = loss(y, pred, task)
        if FEATURE_SET == "v2":
            selection_keys[name] = ((-balanced_accuracy_score(y, (pred >= .5).astype(int)),
                                     round(scores[name], 4)) if task == "classification"
                                    else (round(scores[name], 4),))
        else:
            selection_keys[name] = (scores[name],)
    # Fixed insertion order gives a deterministic tie break; no application data.
    return min(selection_keys, key=selection_keys.get), {name: {
        "loss": scores[name], "selection_key": list(selection_keys[name])} for name in scores}


def metrics(y, p, task):
    if task == "classification":
        labels = (p >= .5).astype(int)  # computational decision threshold, not clinical
        return {"log_loss": loss(y, p, task), "brier": float(brier_score_loss(y, p)),
                "roc_auc": float(roc_auc_score(y, p)),
                "pr_auc_average_precision": float(average_precision_score(y, p)),
                "accuracy": float(accuracy_score(y, labels)),
                "balanced_accuracy": float(balanced_accuracy_score(y, labels)),
                "precision": float(precision_score(y, labels, zero_division=0)),
                "recall": float(recall_score(y, labels, zero_division=0)),
                "confusion_matrix": confusion_matrix(y, labels, labels=[0, 1]).tolist()}
    return {"mae": float(mean_absolute_error(y, p)),
            "rmse": float(np.sqrt(mean_squared_error(y, p))), "r2": float(r2_score(y, p))}


mlflow.set_tracking_uri("databricks")
mlflow.set_experiment(EXPERIMENT)
report, outputs, artifacts, metric_records = {}, {}, {}, []
with mlflow.start_run(run_name=f"nested-LOSO-motion-temperature-{FEATURE_SET}") as run:
    version = run.info.run_id
    inference_time = datetime.now(timezone.utc).replace(tzinfo=None)
    mlflow.log_params({"feature_version": FEATURE_VERSION, "features": ",".join(FEATURES),
                       "training_subjects": len(train), "excluded_participant": "big_ideas:015",
                       "outer_cv": "LeaveOneGroupOut",
                       "inner_cv": "3 subject-grouped folds", "seed": 42})
    mlflow.log_param("classification_selection", "balanced_accuracy_then_logloss" if FEATURE_SET == "v2" else "logloss")
    mlflow.set_tags({"interpretation": "research cohort resemblance; not diagnosis",
                     "imu50_units": "inferred g/Celsius; cross-device unvalidated",
                     "prediction_granularity": "completed observation interval"})
    for task, y in targets.items():
        candidate_oof = {name: np.full(len(y), np.nan) for name in models[task]}
        selected_oof = np.full(len(y), np.nan)
        selected_names, fold_records, selected_std = [None] * len(y), [], [None] * len(y)
        for fold, (fit_idx, held_idx) in enumerate(LeaveOneGroupOut().split(X, y, groups)):
            assert set(groups[fit_idx]).isdisjoint(groups[held_idx])
            chosen, scores = select_model(X[fit_idx], y[fit_idx], groups[fit_idx], task)
            held = int(held_idx[0])
            for name, estimator in models[task].items():
                fitted = fit(estimator, X[fit_idx], y[fit_idx])
                pred = predict(fitted, X[held_idx], task)
                candidate_oof[name][held_idx] = pred
                if name == chosen:
                    selected_oof[held_idx] = pred
                    if name == "bayesian_ridge":
                        selected_std[held] = float(fitted.predict(X[held_idx], return_std=True)[1][0])
            selected_names[held] = chosen
            fold_records.append({"held_out": groups[held], "selected": chosen, "inner_scores": scores})
            print(f"{task}: held out {groups[held]}, selected {chosen}", flush=True)
        chosen_final, final_scores = select_model(X, y, groups, task)
        fitted_final = fit(models[task][chosen_final], X, y)
        artifacts[task] = fitted_final
        main_metrics = metrics(y, selected_oof, task)
        # Paired subject resampling of fixed OOF errors is descriptive only.
        errors = ((selected_oof - y) ** 2 if task == "classification" else abs(selected_oof - y))
        rng = np.random.default_rng(42)
        bootstrap = np.mean(errors[rng.integers(0, len(y), size=(1000, len(y)))], axis=1)
        main_metrics["descriptive_error_bootstrap_95"] = np.quantile(bootstrap, [.025, .975]).tolist()
        report[task] = {"nested_selected_metrics": main_metrics, "selected_final": chosen_final,
                        "final_inner_scores": final_scores, "folds": fold_records,
                        "fixed_candidate_loo_metrics": {name: metrics(y, p, task) for name, p in candidate_oof.items()}}
        outputs[task] = {"predictions": selected_oof, "names": selected_names, "std": selected_std,
                         "final_name": chosen_final}
        for name, p in {**candidate_oof, "nested_selection": selected_oof}.items():
            value = metrics(y, p, task)
            metric_records.append((version, task, name, json.dumps(value), inference_time))
            for key, number in value.items():
                if isinstance(number, (float, int)):
                    mlflow.log_metric(f"{task}.{name}.{key}", number)
    # Model selection and fitting are complete BEFORE examining IMU50 predictions.
    report["limitations"] = [
        "15 independent training subjects; no clinical validation or probability calibration claim",
        "Bootstrap describes fixed OOF error uncertainty, not full model-selection uncertainty",
        "LOSO class-prior baseline probabilities depend on the omitted class; its AUC can be misleading",
        "IMU50 has inferred units and unvalidated device/population transfer",
        "Shared ACC/temperature features only; HR and PPG amplitudes are not shared inputs",
        "Regression estimates mean CGM in a completed interval, not current glucose or a forecast",
    ]
    if FEATURE_SET == "v2":
        report["limitations"].append("Development iteration after reviewing v1 on the same cohort; not fresh independent validation")
    report["classification_selection"] = "balanced_accuracy_then_logloss" if FEATURE_SET == "v2" else "logloss"
    report["candidate_models"] = {task: list(candidates) for task, candidates in models.items()}
    report["convergence_warning_count"] = len(convergence_warnings)
    report["features"] = FEATURES
    report["feature_version"] = FEATURE_VERSION
    report["training_cohort"] = groups.tolist()
    report["excluded_participants"] = EXCLUSIONS
    report["exclusion_approved_at"] = "2026-10-03; before model fitting/evaluation"
    report["model_version"] = version
    mlflow.log_dict(report, "evaluation.json")
    # Persist only our own fitted objects. Never load untrusted pickle artifacts.
    spark.sql("CREATE SCHEMA IF NOT EXISTS workspace.wolfhacks_models")
    spark.sql("CREATE VOLUME IF NOT EXISTS workspace.wolfhacks_models.artifacts")
    artifact_root = Path(f"/Volumes/workspace/wolfhacks_models/artifacts/{version}")
    artifact_root.mkdir(parents=True, exist_ok=False)
    for task, fitted in artifacts.items():
        joblib.dump(fitted, artifact_root / f"{task}.joblib")
    (artifact_root / "metadata.json").write_text(json.dumps(report, indent=2))
    mlflow.log_artifacts(str(artifact_root), artifact_path="fitted_models")

# COMMAND ----------

def common(row, model_name, evaluation, outside_range):
    return (str(row.source_dataset), str(row.subject_id), str(row.participant_key),
            row.observation_start.to_pydatetime(), row.observation_end.to_pydatetime(),
            model_name, version, FEATURE_VERSION, inference_time, evaluation,
            str(row.unit_status), bool(outside_range), "exploratory_not_clinically_validated")


class_rows, reg_rows = [], []
for index, row in train.iterrows():
    class_prediction = float(outputs["classification"]["predictions"][index])
    reg_prediction = float(outputs["regression"]["predictions"][index])
    others = np.delete(X, index, axis=0)
    outside = np.any((X[index] < others.min(axis=0)) | (X[index] > others.max(axis=0)))
    class_rows.append(common(row, outputs["classification"]["names"][index], "nested_loso", outside) +
                      (class_prediction, int(class_prediction >= .5), int(row.cohort_label)))
    reg_rows.append(common(row, outputs["regression"]["names"][index], "nested_loso", outside) +
                    (reg_prediction, float(row.mean_cgm_mg_dl),
                     abs(reg_prediction - float(row.mean_cgm_mg_dl)), outputs["regression"]["std"][index]))

for _, row in application.iterrows():
    if not row.eligible:
        raise ValueError("Application participant fails quality gate; do not publish an imputed score")
    values = np.asarray([[row[name] for name in FEATURES]], dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Non-finite application features")
    outside = np.any((values < X.min(axis=0)) | (values > X.max(axis=0)))
    cp = float(predict(artifacts["classification"], values, "classification")[0])
    rp = float(predict(artifacts["regression"], values, "regression")[0])
    std = None
    if outputs["regression"]["final_name"] == "bayesian_ridge":
        std = float(artifacts["regression"].predict(values, return_std=True)[1][0])
    class_rows.append(common(row, outputs["classification"]["final_name"], "application_unvalidated", outside) +
                      (cp, int(cp >= .5), None))
    reg_rows.append(common(row, outputs["regression"]["final_name"], "application_unvalidated", outside) +
                    (rp, None, None, std))

common_schema = """
source_dataset STRING, subject_id STRING, participant_key STRING,
observation_start TIMESTAMP_NTZ, observation_end TIMESTAMP_NTZ,
model_name STRING, model_version STRING, feature_version STRING,
inference_timestamp TIMESTAMP, evaluation STRING, unit_status STRING,
outside_training_feature_range BOOLEAN, interpretation STRING
"""
spark.sql("CREATE SCHEMA IF NOT EXISTS workspace.wolfhacks_gold")
for name, rows, suffix in (
    ("metabolic_risk_predictions", class_rows,
     "risk_probability DOUBLE, risk_class INT, actual_label INT"),
    ("glucose_proxy_predictions", reg_rows,
     "predicted_glucose_metric DOUBLE, actual_glucose_metric DOUBLE, absolute_error DOUBLE, predictive_std DOUBLE"),
):
    schema = common_schema + "," + suffix
    table = f"workspace.wolfhacks_gold.{name}"
    spark.sql(f"CREATE TABLE IF NOT EXISTS {table} ({schema}) USING DELTA "
              "TBLPROPERTIES ('delta.feature.timestampNtz'='supported')")
    spark.createDataFrame(rows, schema).write.mode("append").saveAsTable(table)
spark.createDataFrame(metric_records, "model_version STRING, task STRING, model_name STRING, metrics_json STRING, evaluated_at TIMESTAMP") \
    .write.mode("append").saveAsTable("workspace.wolfhacks_gold.model_comparison")
dbutils.jobs.taskValues.set(key="model_version", value=version)
dbutils.notebook.exit(json.dumps({"model_version": version, "report": str(artifact_root / "metadata.json"),
    "classification": report["classification"]["nested_selected_metrics"],
    "regression": report["regression"]["nested_selected_metrics"],
    "selected_classification": outputs["classification"]["final_name"],
    "selected_regression": outputs["regression"]["final_name"],
    "gold_rows_per_task": len(class_rows)}))
