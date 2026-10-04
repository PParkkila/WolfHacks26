# Databricks + Tiger live sensor setup

This directory implements the hackathon architecture:

```text
Historical datasets -> Databricks Unity Catalog Volume -> Bronze Delta

Mock or real sensor -> HTTPS ingestion API -> Tiger raw.sensor_events
                                             |
                                             v
                                  Databricks Bronze Delta
```

Historical high-frequency files do not go into Tiger. They live in inexpensive
cloud object storage behind a Databricks Volume. Tiger is the operational
time-series database for live events. Both sources meet in Databricks Bronze.

## Files

- `schema.sql`: Tiger hypertable and indexes for live sensor events.
- `init_tiger.py`: applies the Tiger schema.
- `api.py`: authenticated FastAPI ingestion service.
- `mock_sensor.py`: development producer using the production HTTP contract.
- `Dockerfile`: deployable ingestion API container.
- `setup_databricks.sql`: creates the Volume and Bronze Delta table.
- `stage_big_ideas_subject.py`: downloads one BIG IDEAs subject to the Volume.
- `stage_imu50_subject.py`: retrieves one nested IMU50 subject ZIP and expands
  only that subject into the Volume.
- `tiger_to_bronze.py`: incremental Tiger-to-Delta Databricks job.
- `check_tiger.py`: read-only serverless connection, schema, and library check;
  reads credentials from Databricks Secrets without printing them.
- `tiger_to_bronze.job.json`: this workspace's unscheduled serverless ingestion
  job configuration; contains connection metadata and secret key names only.
- `inspect_pilot.py`: bounded header and sample inspection after the first two
  subjects land; it does not scan the whole dataset.
- `download_first_subjects.py`: local Windows/macOS/Linux download of BIG IDEAs
  subject `001` and IMU50 subject `00`, ready for a manual Volume upload.
- `extract_uploaded_imu50.py`: expands an uploaded nested IMU50 subject ZIP on
  serverless, so the home upload sends about 0.8 GB instead of 4 GB of CSVs.
- `activity_minute_pilot.py`: read-only, one-subject acceleration/HR minute
  summary to inspect motion features and coverage before building Silver.
- `lakeflow_activity_minute_pilot.py`: the reviewed one-subject transform as a
  Lakeflow materialized view; still a pilot, not the full cohort pipeline.
- `audit_sensor_units.py`: reproducible, bounded local unit-evidence audit.
- `lakeflow_shared_units_pilot.py`: Bronze CSV fields and shared minute motion/
  temperature features for all 16 BIG IDEAs participants and IMU50 00, with
  provisional-unit tags. Existing table names retain the `_pilot` suffix.
- `stage_model_cohort.py`: checksum-verified S3 staging for all 16 participants'
  ACC, temperature, HR, and Dexcom files plus demographics.
- `lakeflow_model_tables.py`: wearable-only participant features and separate
  cohort/CGM targets; no glucose or HbA1c enters feature construction.
- `train_subject_models.py`: nested participant-held-out candidate comparison,
  MLflow artifacts, and versioned Gold predictions; quality gates run first.
- `gold_to_tiger.py`: bounded, transactional, idempotent export of one completed
  model version to Tiger; credentials come from Databricks Secrets.
- `subject_models.job.json`: unscheduled feature refresh → training → Tiger
  publication workflow; passes the exact model version between tasks.
- `prepare_demo_history.py`: isolated nine-day demo fixtures with explicit
  synthetic gap/extension flags and seven days of trailing sensor metrics.
- `demo_replay_payload.py`: pure, non-sending adapter from a fixture minute to
  an idempotent API event with separate source and demo timestamps.
- `pilot.pipeline.json`: deployed Lakeflow source configuration, preserving the
  original BIG IDEAs motion/HR table alongside the shared-unit tables.

## 1. Create the Tiger service

Create a Tiger Cloud PostgreSQL service and copy its connection string. It must
include TLS:

```text
postgresql://USER:PASSWORD@HOST:PORT/DATABASE?sslmode=require
```

Keep this value out of Git.

## 2. Install the local API dependencies

From the monorepo root:

```sh
python3 -m venv databricks/.venv
source databricks/.venv/bin/activate
python -m pip install -r databricks/tiger/requirements.txt
```

## 3. Initialize Tiger

Set the connection only in the current shell and apply the idempotent schema:

```sh
export TIGER_DATABASE_URL='postgresql://USER:PASSWORD@HOST:PORT/DATABASE?sslmode=require'
python databricks/tiger/init_tiger.py
```

This creates `raw.sensor_events` as a Timescale hypertable. Live timestamps are
stored as `TIMESTAMPTZ`; the complete versioned event is retained as JSONB.

For a deployed environment, create separate database roles:

- API role: `USAGE` on `raw`, `INSERT` on `raw.sensor_events`, and column-level
  `SELECT (event_id)` for the insert response.
- Databricks role: `USAGE` on `raw` and `SELECT` on `raw.sensor_events`.
- Keep the Tiger administrative account out of deployed services.

## 4. Start the ingestion API locally

Choose a long random API key and start the service:

```sh
export SENSOR_INGEST_API_KEY='replace-with-a-long-random-secret'
uvicorn api:app --app-dir databricks/tiger --reload
```

In a second terminal, activate the same environment and use the same key:

```sh
source databricks/.venv/bin/activate
export SENSOR_INGEST_API_KEY='replace-with-the-same-secret'
python databricks/tiger/mock_sensor.py --count 20 --interval 1
```

The mock sends `demo_signal` values rather than pretending to know the eventual
hardware schema. A real sensor will replace this sender and keep the same event
envelope:

```json
{
  "event_id": "80d03798-0274-43f7-b60f-6ac09bc27897",
  "sensor_id": "device-001",
  "observed_at": "2026-10-03T15:30:00Z",
  "sequence_number": 1,
  "schema_version": 1,
  "measurements": {
    "actual_sensor_field": 12.3
  }
}
```

`event_id` makes exact retries idempotent. `observed_at` must include a timezone.

Validate in the Tiger SQL editor:

```sql
SELECT sensor_id,
       count(*) AS events,
       min(observed_at) AS first_event,
       max(observed_at) AS latest_event
FROM raw.sensor_events
GROUP BY sensor_id;
```

## 5. Create Databricks storage

Add this repository to a Databricks Git folder using the
`databricks/metabolic-risk-pipeline` branch. Open `setup_databricks.sql` in a
Databricks SQL editor and run it.

It creates:

```text
/Volumes/workspace/wolfhacks_raw/source_files/
workspace.wolfhacks_bronze.sensor_events
```

This workspace uses the `workspace` catalog, not `main`. For another workspace,
replace `workspace` in the SQL and in the
notebook defaults with a catalog where you have `USE CATALOG`, `CREATE SCHEMA`,
`CREATE VOLUME`, and `CREATE TABLE` permissions.

## 6. Stage the historical datasets into the Volume

Run these as Databricks notebooks or one-time jobs. Do one subject first and
inspect the result before running all subjects.

If downloading on your own computer is faster, run this instead from the
monorepo root (on Windows, use `py` in place of `python3`):

```sh
python3 -m pip install remotezip==0.12.6
python3 databricks/tiger/download_first_subjects.py --output-dir pilot-data
```

This downloads all eight BIG IDEAs `001` CSVs and the four IMU50 `00` CSVs.
For BIG IDEAs, it uses PhysioNet's public AWS S3 mirror for files whose
published SHA-256 checksums match version 1.1.3. Only four corrected food logs
(`007`, `013`, `015`, and `016`) come from the current PhysioNet HTTP source.
The public S3 mirror currently exposes version 1.1.2; the version 1.1.3 public
S3 object path returns 404. Use `--dataset big --all-big` to download all 16
subjects with the current corrected content. The script needs no AWS CLI or
AWS credentials for this public mirror.

For the small glucose-target audit without downloading every large wearable
file, use `--dataset big --all-big --big-kinds Dexcom`. Completed local files
are skipped.

It reads only the nested IMU50 subject ZIP from Zenodo. Add `--quick` to skip
BIG IDEAs ACC and BVP for a smaller initial pilot; rerun without it later to
fill those in. Existing completed files are skipped, and interrupted BIG IDEAs
downloads resume when the source accepts HTTP ranges.

In Databricks Catalog Explorer, upload `pilot-data/big_ideas/Demographics.csv`
to the Volume's `big_ideas/` directory, the files in `pilot-data/big_ideas/001/`
to `big_ideas/001/`, and `pilot-data/imu50/subjects_info.csv` to `imu50/`.
For IMU50, upload only `pilot-data/imu50/archives/00.zip` to the Volume's
`imu50/archives/00.zip` path, then run `extract_uploaded_imu50.py` on serverless
with the correct `volume_root`. This avoids uploading the roughly 4 GB of
expanded `pilot-data/imu50/00/` CSVs. Keep the directories exactly as shown so
the pilot inspection notebook finds the files.

To download only the compressed IMU50 subject for that route, run:

```sh
python3 databricks/tiger/download_first_subjects.py --dataset imu --imu-zip-only --output-dir pilot-data
```

### BIG IDEAs

Run `stage_big_ideas_subject.py` with:

```text
subject_id = 001
volume_root = /Volumes/workspace/wolfhacks_raw/source_files/big_ideas
include_large_files = false
```

Then repeat for `002` through `016`. The notebook downloads each public CSV
directly from PhysioNet and also stages `Demographics.csv`. The pilot setting
downloads Dexcom, food log, HR, IBI, temperature, and EDA first. Set
`include_large_files=true` in a background job to add the much larger ACC and
BVP files. Interrupted `.part` downloads resume when PhysioNet supports HTTP
Range requests.

### IMU50

Run `stage_imu50_subject.py` with:

```text
subject_id = 00
volume_root = /Volumes/workspace/wolfhacks_raw/source_files/imu50
```

Then repeat for `01` through `49`. The notebook uses Zenodo HTTP byte ranges to
retrieve only `IMU50/DATA/XX.zip`, expands its four CSV members into the Volume,
stages `subjects_info.csv`, and deletes the temporary ZIP. It never downloads
the complete 46.7 GB outer archive.

For subject `00`, expect roughly 834 MB of temporary ZIP data and about 4 GB of
expanded CSV data. The notebook uses the compute session's temporary directory,
so it works on serverless and classic compute without assuming `/local_disk0`
exists. The expanded CSV is written directly to the Volume.

Both staging notebooks display byte progress, current MB/s, and ETA. Typical
healthy-workspace estimates are 5-20 minutes for one BIG IDEAs subject and
5-20 minutes for one IMU50 subject. The public source, workspace region, and
Volume write throughput can make runs slower. Expect the complete BIG IDEAs
landing to take roughly 1-4 hours and all 50 IMU50 subjects to take roughly
4-12+ hours; run them as jobs rather than keeping an interactive browser tab
open.

Verify the landing paths:

```python
display(dbutils.fs.ls("/Volumes/workspace/wolfhacks_raw/source_files/big_ideas/001"))
display(dbutils.fs.ls("/Volumes/workspace/wolfhacks_raw/source_files/imu50/00"))
```

Then run `inspect_pilot.py` on serverless with `volume_root` set to
`/Volumes/<your-catalog>/wolfhacks_raw/source_files`. It prints file sizes,
actual CSV headers, first and last sampled rows, and blank-cell percentages
from at most 1,000 rows per file. The ACC and BVP files may show as missing if
you ran the BIG IDEAs pilot with `include_large_files=false`. This is a quick
format check; it does not claim exact full-file counts or missingness.

Do not interpret IMU50 units, timezone, or coded subject metadata until its
source documentation supports that interpretation. Its 128 Hz IMU and 25 Hz
PPG rows repeat whole-second timestamps, so future Bronze parsing must preserve
the source row/sample ordinal.

### One-subject motion + heart-rate pilot

After BIG IDEAs `ACC_001.csv` and `HR_001.csv` are uploaded, import
`activity_minute_pilot.py` as a Databricks notebook and run it on serverless
with these widgets:

```text
volume_root = /Volumes/workspace/wolfhacks_raw/source_files
subject_id = 001
```

The notebook converts Empatica E4 accelerometer counts to g using 64 counts
per g, calculates one-minute ENMO movement summaries, and averages the HR
readings sharing a minute timestamp. The output shows minute coverage and
sample rows. It only creates a temporary view, `activity_minute_pilot`; it
does not write a Silver table or label exercise intensity. Review timestamps,
coverage, and HR overlap before promoting this logic to Lakeflow.

BIG IDEAs and IMU50 contain different people. Every feature row keeps
`source_dataset`, `subject_id`, and a dataset-qualified `participant_key`;
never join the two datasets on a numeric subject ID. BIG IDEAs supplies the
glucose outcomes for training, while IMU50 is an unlabeled, out-of-cohort
application dataset whose sensor compatibility must be checked separately.

To persist the reviewed one-subject result, create a **New → ETL pipeline**
using serverless, set its default catalog to `workspace` and schema to
`wolfhacks_silver`, and add `lakeflow_activity_minute_pilot.py` as source code.
Run one triggered update. It publishes
`workspace.wolfhacks_silver.activity_minute_pilot`. The materialized-view
function only returns a Spark DataFrame; it has no manual writes or collects.
It still reads raw Volume files directly as a limited pilot. Add Bronze Delta
source tables before expanding this to a production medallion pipeline.

Historical minute keys use `TIMESTAMP_NTZ`: the source dates were shifted and
the timezone is undocumented. `make_timestamp_ntz` preserves that source clock
when constructing a minute key. The materialized view explicitly enables
`delta.feature.timestampNtz = supported`; otherwise changing an existing Delta
table from `TIMESTAMP` can fail during refresh. Live device events remain
timezone-aware UTC instants, separate from historical source-clock values.

## 7. Store Tiger credentials in Databricks Secrets

Create a secret scope called `wolfhacks`, then add:

```text
tiger-user
tiger-password
```

Do this in the Databricks secret UI or CLI. Do not put the password in notebook
widgets, cluster environment variables visible to other users, or Git.

For the configured `wolfhacks` CLI profile, enter values at the interactive
prompts (do not include secrets as command-line arguments):

```sh
databricks secrets put-secret wolfhacks tiger-user --profile wolfhacks
databricks secrets put-secret wolfhacks tiger-password --profile wolfhacks
```

Allow network traffic from the Databricks compute plane to the Tiger service.
Depending on the workspace, this means permitting the workspace egress IP or
configuring private networking.

## 8. Configure the Tiger-to-Bronze job

`tiger_to_bronze.py` is compatible with serverless compute. Its first cell
installs the pure-Python `pg8000` PostgreSQL client, so no cluster or Maven JDBC library is
required. Run that first cell and allow the Python restart before continuing.
The native `psycopg-binary` import crashed on this workspace's ingestion run;
the API's local psycopg dependency is unchanged. The Databricks loader uses
certificate-verified TLS and a server-side cursor with bounded fetches.

Create a Databricks job for `tiger_to_bronze.py` with these parameters:

```text
tiger_host          = your Tiger hostname
tiger_port          = 5432 or the port from Tiger
tiger_database      = database name from the connection string
secret_scope        = wolfhacks
user_secret_key     = tiger-user
password_secret_key = tiger-password
target_table        = <your-catalog>.wolfhacks_bronze.sensor_events
lookback_minutes    = 10
```

Configured service for this workspace:

```text
tiger_host     = hi70ycj0r6.b4t1dqdug8.tsdb.cloud.timescale.com
tiger_port     = 31994
tiger_database = tsdb
job_id         = 940874481780578
```

Run the existing job from your local terminal (do not create a duplicate):

```sh
databricks jobs run-now 940874481780578 --no-wait --profile wolfhacks
```

No recurring schedule is enabled yet.

Verified in this workspace: Tiger's `raw.sensor_events` is a Timescale
hypertable. Two successful loader runs each processed the same 20 candidate
events; the Bronze table remained at 20 rows and 20 unique event keys. These
events contain only `demo_signal`, so this verifies transport and replay
idempotency, not physiological feature extraction or model inference.

Run it once manually. It reads Tiger events using `received_at`, deliberately
rereads a short lookback window, and uses Delta `MERGE` so retries do not create
duplicates. Then schedule it every one to five minutes for the prototype.

Validate in Databricks SQL:

```sql
SELECT sensor_id,
       count(*) AS events,
       min(observed_at) AS first_event,
       max(observed_at) AS latest_event
FROM workspace.wolfhacks_bronze.sensor_events
GROUP BY sensor_id;
```

## 9. Deploy the API and connect the real sensor

Build the API container:

```sh
docker build -t wolfhacks-sensor-api databricks/tiger
```

Deploy it to a managed HTTPS container service such as Cloud Run, ECS/Fargate,
or Azure Container Apps. Store these as managed secrets:

```text
TIGER_DATABASE_URL
SENSOR_INGEST_API_KEY
TIGER_POOL_SIZE=5
```

Production requirements:

- expose only HTTPS;
- never put Tiger credentials on the physical sensor;
- rotate the API key and database password;
- configure health checks against `/health`;
- set API request limits at the gateway;
- have the device retain and retry the same `event_id` after a timeout;
- batch up to 1,000 events with `POST /v1/events/batch` when appropriate.

The real device posts to the same endpoint as `mock_sensor.py`. Only the
contents of `measurements` and its documented `schema_version` change.

## 10. Full-cohort modeling status

On October 3, 2026, staging run `828548818964265` completed: 65 files,
14,554,572,736 bytes, all selected files verified against published checksums.
There is no need to download these files again from a home connection.

Lakeflow pipeline `54ffc96e-afc7-493e-8025-3e7aafd26c1a`, update
`86713cde-4594-4bc8-99c3-f9b6a69e9c48`, completed successfully. It publishes
17 feature rows (16 BIG IDEAs, one IMU50) and 16 separate labeled target rows:

- `workspace.wolfhacks_features.metabolic_features`
- `workspace.wolfhacks_silver.subject_targets`
- `workspace.wolfhacks_silver.cgm_targets`

The four model inputs are mean and 90th-percentile minute ENMO, mean skin
temperature, and standard deviation of minute skin temperature. HR remains
in the separate BIG IDEAs pilot; raw IMU50 PPG is not substituted for HR.

### Exclusion decision: BIG IDEAs participant 015

**Decision:** exclude `big_ideas:015` from both models' training, model
selection, and held-out evaluation for this prototype. The user approved this
on October 3, 2026, before any model fitting or evaluation. This is a
recording-quality exclusion, not a clinical judgment or a decision based on
the participant's label, glucose level, or prediction error.

Participant `big_ideas:015` has only 4,324 usable minutes out of 5,806 observed
minutes (74.47%; the declared gate requires 80%). Its wearable date range
includes a gap between July 7 and July 19, 2020, and some later ACC minutes
have twice the expected sample count. CGM coverage across the usable-minute
start/end interval is 23.89%, below the declared 50% minimum. All other 15
BIG IDEAs participants pass these checks, with CGM coverage of 81.27–99.47%.
IMU50 00 passes the wearable gate and has no ground truth by design.

| Quality check | Participant 015 | Required by the prototype | Result |
| --- | ---: | ---: | --- |
| Usable wearable minutes | 4,324 | At least 1,440 | Pass |
| Usable / observed wearable minutes | 74.47% | At least 80% | Fail |
| CGM coverage across the observation interval | 23.89% | 50–105% | Fail |

A usable minute requires both ACC and temperature sample counts to be
80–100% of their expected counts, with non-null motion and temperature
summaries. The wearable fraction uses **observed minute bins**, not every
minute of elapsed calendar time. CGM coverage is `cgm_samples × 300 seconds`
divided by the elapsed observation interval, from the first usable minute
through one minute after the last usable minute. For 015, that interval is
July 5, 2020 at 15:12 through July 25 at 11:05, in the source's undocumented
local clock (`TIMESTAMP_NTZ`). Long gaps therefore reduce CGM coverage even
when the samples present can be parsed successfully.

**Why exclude it:** the current regression target summarizes CGM over that
completed interval, while the wearable inputs summarize usable recorded
minutes. Sparse, disconnected coverage makes that pairing less representative
of the interval. Overfull ACC minutes also fail the expected-sampling check;
they are not assumed to be safe-to-delete duplicates. Participant 015 fails
the wearable gate independently of its CGM coverage, so the same exclusion
is applied to both models using the shared feature pipeline. These gates are
engineering choices, not clinical thresholds.

The selected source files passed published SHA-256 checksums, and the sensor
parser audit reported zero invalid timestamp/numeric rows. The observed
problem is coverage and sample counts, not a demonstrated download corruption
or numeric-parsing failure; the cause of the source gaps/overfull minutes has
not been established. No thresholds were relaxed, values imputed to fill the
recording gaps, timestamps shifted, or source rows deleted to make 015 pass.

**Impact and traceability:** the training cohort changes from 16 (8/8 study
groups) to 15 (seven lower-HbA1c-group, eight higher-group). The training
notebook requires those exact 15 participants and records `excluded_participants`
and `exclusion_approved_at` in the model report. All 16 participants' source
files and Bronze/Silver/feature/target rows remain preserved. Participant 015
has no prediction row in the published model version
`cf6c0b85df794678b8aa3db8c96c2a6c`. This exclusion further limits the small
cohort's representativeness; it does not establish that the remaining data or
models are clinically valid.

The evidence was inspected after Lakeflow update
`86713cde-4594-4bc8-99c3-f9b6a69e9c48`. To reproduce the coverage check in
Databricks SQL:

```sql
SELECT f.participant_key, f.observation_start, f.observation_end,
       f.observed_minutes, f.usable_minutes, f.usable_fraction_of_observed,
       f.eligible, t.cgm_samples, t.cgm_interval_coverage
FROM workspace.wolfhacks_features.metabolic_features f
LEFT JOIN workspace.wolfhacks_silver.subject_targets t USING (participant_key)
WHERE f.participant_key = 'big_ideas:015';
```

Reconsider inclusion only after investigating the source gaps/overlapping
sampling and explicitly revising the interval/quality policy if justified.
Any revised analysis needs a new model version and a fresh grouped evaluation;
do not reinterpret this completed run as having included all 16 participants.

### Running the model workflow

Unscheduled workflow job `637291493113074` refreshes the Lakeflow features,
runs the nested model comparison, then exports the resulting model version
to Tiger. Training failures prevent the publication task from running.

```sh
databricks jobs run-now 637291493113074 --no-wait --profile wolfhacks
```

Do not create duplicate jobs. A new successful training run produces a new
model version and preserves earlier outputs. For publication-only retries,
run `gold_to_tiger` with the completed run's `model_version`; Tiger inserts
are idempotent on `(model_version, participant_key, evaluation)`.

Workflow run `928063154293123` completed successfully: feature refresh,
training, and Tiger publication all succeeded. Model version:
`cf6c0b85df794678b8aa3db8c96c2a6c`. Each Gold/Tiger prediction table contains
16 rows for this version: 15 held-out BIG IDEAs predictions and one unlabeled
IMU50 application prediction. The publisher verified both Tiger counts before
committing. No predictions are published for the excluded participant 015.

[Open the completed workflow](https://dbc-5eba5e12-fdc8.cloud.databricks.com/?o=7474646785929472#job/637291493113074/run/928063154293123).

### First executed results — no demonstrated predictive benefit

| Held-out metric | Nested model selection | Simple held-out baseline |
| --- | ---: | ---: |
| Classification log loss (lower is better) | 0.8604 | 0.7651 (class prior) |
| Classification Brier score (lower is better) | 0.3244 | 0.2857 (class prior) |
| Classification accuracy | 40.0% | 53.3% (class prior) |
| Regression MAE, mg/dL | 10.3490 | 9.4217 (training mean) |
| Regression RMSE, mg/dL | 12.1482 | 11.0064 (training mean) |

Nested-selection classification ROC AUC is 0.3214; regression R² is -0.3985.
The fixed-candidate metrics and every fold's selection are retained in MLflow.
There were zero reported convergence warnings. Final inner validation chose
`tiny_mlp` for both tasks, but its advantages over the corresponding dummy
baselines were only about 0.00000054 log-loss units and 0.0000223 mg/dL MAE:
effectively a numerical tie, not evidence of useful neural-network learning.
Outer validation was worse than the simple baselines. Do not promote this
run as an accurate metabolic-risk or glucose predictor, or change model choice
after inspecting held-out results and then reuse those results as fresh validation.

The historical source → features → models → Gold → Tiger path is verified.
This does not complete live physiological inference: the live path still
verifies transport only (`demo_signal`). The frontend's existing synthetic
fixtures have not been replaced by these outputs.

### V2 development experiment

The user requested improved classification after reviewing v1. V2 retains the
same 15 approved participants, target definitions, source units, quality gates,
seed 42, participant-held-out outer folds, and three grouped inner folds. V1
features and model artifacts are preserved. This is a development comparison
on a previously inspected cohort, not a fresh independent validation dataset.

The fixed v2 plan, written before inspecting its model results:

- Add median, standard deviation, and p99 of minute ENMO; p10/p90 temperature;
  motion–temperature correlation; and daily first-harmonic amplitudes for motion
  and temperature. Together with v1, these are 12 wearable-only features.
- Daily amplitudes use equally weighted hourly means, requiring all 24 hours
  with at least 30 usable minutes each across the observation interval. They
  describe source-clock patterns, not sleep diagnoses or exercise categories.
- Compare a class-prior baseline, strongly regularized logistic regression,
  logistic regression using three selected features, shrinkage LDA, a shallow
  forest, and a four-unit neural network with less aggressive regularization.
- Fit supervised feature selection, scaling, and imputation only within each
  training fold. Select classification candidates by inner balanced accuracy,
  breaking ties by log loss rounded to four decimal places, then fixed model
  order. This avoids choosing a neural net for a negligible numerical advantage
  over a baseline. Regression retains MAE selection, rounded to four decimals.
- Report outer accuracy, balanced accuracy, log loss, and baseline comparisons;
  do not change labels, exclude more people, search random seeds, or report
  training accuracy to reach the requested percentage. Predicting the majority
  group already yields 53.3%; beating 50% alone is not useful evidence.

The v2 table is `workspace.wolfhacks_features.metabolic_features_v2`.
After refreshing it, run the bounded development comparison with:

```sh
databricks jobs submit --json @databricks/tiger/model_development.run.json --no-wait --profile wolfhacks
```

This writes separately versioned Gold/artifact outputs but does not automatically
publish the experiment to Tiger. The saved full workflow still defaults to v1.
Nested validation reduces within-run selection leakage, but cannot undo reuse
of the same cohort across development iterations. See scikit-learn's
[nested-validation explanation](https://scikit-learn.org/stable/auto_examples/model_selection/plot_nested_cross_validation_iris.html)
and [pipeline leakage guidance](https://scikit-learn.org/stable/common_pitfalls.html).

V2 run `1084751433753721` succeeded, model version
`2020da0a20a84dd183db105c9623117b`. The nested held-out development evaluation
classified 13/15 participants correctly (86.67% accuracy; 86.61% balanced
accuracy; ROC AUC 0.9464; log loss 0.2595). Its confusion matrix is
`[[6, 1], [1, 7]]`, ordered lower/higher HbA1c group. The majority baseline
was 8/15 (53.33%). A direct Gold-to-target-table audit verified all 15 labels,
13 correct predictions, no prediction for 015, and a null actual label for
IMU50. No convergence warnings were reported. Final inner selection chose
the tiny MLP; outer folds selected it 12 times, shrinkage LDA twice, and
three-feature logistic regression once. These are development results on the
same 15 people, not an independently confirmed population accuracy.

Regression did not improve: nested MAE was 10.7810 mg/dL versus 9.4217 for the
mean baseline; final regression selection chose that baseline. Feature set,
regularization, and selection criterion changed together, so this experiment
does not isolate which change caused the classification improvement.

V2 outputs are in Databricks Gold, but publication to Tiger and changing the
saved workflow default were paused after the user's clarification below.
V1 Tiger outputs and saved artifacts remain intact.

### Product clarification: recent-pattern cohort resemblance

The user clarified that the intended output is similarity of recent wearable
data to reference people in the lower/higher-HbA1c study groups, not a diagnosis
or a claim to recover that person's glucose level. Group membership does not
define a unique sensor profile or CGM trace. Do not manufacture a third
"diabetic" reference group, extrapolate unseen glucose levels, or hard-code
assumptions that lower HbA1c implies less movement or less variability in every
wearable signal. Such relationships must be measured, not assumed.

The existing v2 classifier is a **completed-observation-interval** classifier.
Its model probability is not a measured percentage of physiological similarity.
A recent-window resemblance implementation should compare equal-duration,
quality-qualified wearable summaries, expose supporting reference participants
and feature differences, and allow "unlike either group"/insufficient-data
results. The user confirmed a trailing 24-hour window updated hourly, with a
seven-day trend; this requires a separately evaluated windowed implementation.
Retraining and evaluation must still hold out whole participants; all windows
from one participant stay in the same fold. The reported 86.67% does not measure
the recent-window task or transfer accuracy on IMU50. The separate 24-hour
implementation and its own development results are documented below.

### Agreed dashboard framing: risk indicator and rolling trends

The user approved presenting cohort resemblance as a **wearable risk indicator**
alongside health-related sensor metrics and rolling trends. In this prototype,
"risk" means resemblance to the higher-HbA1c reference group's wearable patterns,
not a calibrated chance of diabetes, a diagnosis, or a predicted disease event.
Do not describe an output of 80 as "80% diabetes risk" or low resemblance as
proof that someone is healthy. Show the reference cohort, observation window,
data coverage, model version, and inferred-unit/cross-device limitations.

Confirmed score window: the previous 24 hours, updated hourly, with a seven-day
history. Rebuild the reference features and evaluation
at the same duration as the application window; do not apply the multi-day
v2 result directly to a few minutes of incoming data. Preserve participant-level
splits when there are multiple rolling windows per person. Overlapping windows
must not be counted as additional independent participants in reported accuracy.

The planned metric panel separates measurements from interpretations:

| Panel | Defensible quantity | Guardrail |
| --- | --- | --- |
| Wearable risk indicator | Relative resemblance to the two study groups, with supporting feature differences | Not a disease probability; support insufficient-data/unlike-reference results |
| Movement | Minute ENMO, movement variability, recent versus personal-baseline changes | Do not invent METs, calories, or clinical exercise zones |
| Heart rate | Observed HR and changes alongside movement, where a valid HR series exists | BIG IDEAs has HR; IMU50 raw PPG needs a validated extraction/quality step first |
| Skin temperature | Measured skin temperature and rolling baseline deviations | Not core temperature, fever, or a diagnosis |
| Daily pattern | Variation across recorded hours and its change over time | Not a sleep/stress score without supporting validation |
| Data quality | Coverage, missing intervals, overfull samples, and source/unit status | Missing or unreliable data should be visible, not silently turned into a normal score |

Use recent movement and HR together as context, not proof that movement caused
a physiological change. Variability in these signals is not automatically
harmful. The current regression outputs remain experimental: neither v1 nor v2
beat the mean-glucose baseline, and the selected v2 regressor is the training
mean. Do not present it as a measured or responsive live glucose signal.

These panels and rolling-window inference describe the agreed next increment;
they have not yet been connected to the frontend or live physiological stream.

### Replay history requirement and source-duration audit

The user requested a ready-to-start mock stream with seven days precomputed
for each demo individual and at least another day available for replay.
Do not start an ongoing stream or enable a schedule until the user decides to
turn it on. Preserve source timestamps separately from the demo's replay clock.
Replayed recordings are not new independent training participants.

Seven days of raw historical input plus one replay day requires eight days.
Seven **full days of hourly 24-hour scores** also needs a preceding 24-hour
warm-up: eight preloaded days plus one replay day, or nine days total. Missing
data can still make some windows unscorable; elapsed time alone is insufficient.

The source audit on October 3, 2026 found:

| Participant | Elapsed span, days | Usable minute equivalents, days |
| --- | ---: | ---: |
| BIG IDEAs 001 | 9.10 | 7.34 |
| BIG IDEAs 005 | 9.04 | 8.43 |
| BIG IDEAs 006 | 9.99 | 5.78 |
| BIG IDEAs 011 | 10.08 | 7.65 |
| IMU50 00 | 5.13 | 4.70 |

The four listed BIG IDEAs participants are the non-excluded **duration
candidates** for a nine-day demo, not proof of continuously adequate rolling
coverage. Among all 15 eligible BIG IDEAs participants, ten span at least eight
days and only these four span at least nine. Other participants have shorter
recordings. Participant 015 remains excluded regardless of its long calendar
span, because of the documented quality failures.

The staged data cannot provide eight/nine days of real history for everyone.
On October 3, 2026, the user explicitly approved synthetic extensions **for this
demo purpose only**. IMU50 00 and shorter/incomplete recordings therefore receive
labeled demo-only extensions; their original observations remain unchanged.

### Synthetic demo preparation (stream remains disabled)

Run `prepare_demo_history` as a serverless notebook with `fixture_id=nine-day-v1`.
It prepares all 17 staged participants, including 015 as a **demo-only** sensor
persona. Participant 015 remains excluded from model training/evaluation; being
included in a fabricated replay is not a reversal of that exclusion.

Each demo persona has 12,960 consecutive minute summaries (nine days):

1. Offsets 0–1,439: 24-hour warm-up.
2. Offsets 1,440–11,519: seven days of history.
3. Offsets 11,520–12,959: one reserved replay day, not exposed to historical metrics.

The generator retains valid observed ACC/temperature minute tuples when present.
For missing/invalid minutes or dates beyond the recording, it uses that same
participant's valid tuple at the same clock minute, preferring their most
complete recorded day. If no same-clock-minute donor exists, it uses the previous
available template minute, or the next at the start of the day. The actual donor
timestamp is retained. Movement, temperature, and available HR travel together;
no cross-person mixing, invented glucose, added outcome labels, or random clinical
anomalies are used. Repeated templates are artificial and may make demo trends
look more regular; they do not simulate physiological progression. Donors may
come from later parts of the source recording, so synthetic history is also
unsuitable for forecasting/backtesting or accuracy claims.

Every row carries `demo_only=true`, `training_eligible=false`, a `demo:` identity,
`is_synthetic`, `provenance` (`observed_replay`, `synthetic_gap_fill`, or
`synthetic_extension`), original intended/donor source-clock strings, unit status,
and the generation policy. Even an unmodified observed tuple is a **replay**,
not a newly observed live sensor measurement. Existing model notebooks only
read the historical feature tables, never this isolated demo schema.

Tables under `workspace.wolfhacks_demo`:

- `minute_bank`: all nine days, including the reserved future replay bank.
- `history_minutes`: eight preloaded days only, including warm-up.
- `history_metrics_24h`: 168 hourly trailing windows per persona, each using only
  the preceding 1,440 minutes; movement, skin temperature, measured HR where
  available, motion–HR correlation, HR coverage, and synthetic-data fraction.
- `manifest`: per-person counts and `stream_enabled=false`.

HR comes from BIG IDEAs' supplied HR series where sufficiently covered; IMU50
HR remains NULL. A copied HR value is tagged synthetic with its donor tuple.
In the base `history_metrics_24h` fixture, `wearable_risk_indicator` remains NULL:
these are precomputed **sensor metrics**, not model outputs. The dashboard
publisher separately scores them using the trained 24-hour release described
below. No model is trained on synthetic history, and fixture preparation does
not activate a stream.

Verified preparation run `969421652848660` completed successfully for fixture
`nine-day-v1`: 17 personas, 220,320 total minute records, of which 63,334 are
explicitly synthetic. Each persona has exactly 1,440 reserved replay minutes
and 168 precomputed hourly history summaries (2,856 summaries total). IMU50 00
has 6,188 synthetic minutes out of its 12,960-minute demo fixture. These numbers
describe fabricated demo completeness, not observed recording coverage.

The HR parser supports both observed export formats: ISO date/second strings
and month/day/year minute strings. It truncates to minute bins and rejects
unrecognized timestamps. All prior model artifacts remain unchanged.

When a sender is enabled later, `event_for_minute` in `demo_replay_payload.py`
maps offset 11,520 to the chosen UTC `replay_start`; prior offsets map to the
preceding eight days. Persist the same session ID and start time for retries.
Deterministic event UUIDs support idempotent ingestion. The event carries a
`demo_minute_summary_v1` measurement contract, not fabricated raw 32/128 Hz
samples. The adapter itself performs no network calls; the physiological replay
consumer and 24-hour model still need integration before this is an end-to-end
live-risk demonstration.

### Reading the outputs

After successful publication, Tiger tables are `gold.metabolic_risk_predictions`
and `gold.glucose_proxy_predictions`; Databricks mirrors are in
`workspace.wolfhacks_gold`. Always select a single `model_version`.
BIG IDEAs rows have `evaluation = 'nested_loso'`: each is an honest held-out
prediction, so its model name can differ between folds. IMU50 rows have
`evaluation = 'application_unvalidated'` and use the final model fitted on all
15 eligible training participants. Their actual outcomes and errors are NULL.

Example Tiger query (replace the version with the training task's output):

```sql
SELECT c.participant_key, c.risk_probability, c.model_name AS classification_model,
       r.predicted_glucose_metric AS estimated_interval_mean_mg_dl,
       r.model_name AS regression_model, c.unit_status,
       c.outside_training_feature_range, c.observation_start, c.observation_end
FROM gold.metabolic_risk_predictions c
JOIN gold.glucose_proxy_predictions r
  USING (model_version, participant_key, evaluation)
WHERE c.model_version = 'REPLACE_WITH_MODEL_VERSION'
  AND c.evaluation = 'application_unvalidated';
```

`risk_probability` is the legacy field name for a study-group resemblance
score, not a validated disease probability. Do not present the regression
estimate as a current glucose measurement. An out-of-training-range flag is
a simple feature-range warning, not a complete device-shift detector.
Metrics are saved in `workspace.wolfhacks_gold.model_comparison`, the MLflow
experiment `/Shared/WolfHacks-subject-models`, and the model version's metadata
under `/Volumes/workspace/wolfhacks_models/artifacts/`.

### Approved modeling direction

See the workflow status above for executed results.

The user approved the recommended subject-level pair on October 3, 2026.
The [original study](https://www.nature.com/articles/s41746-021-00465-w)
provides the recruitment groups used for classification:

- Participant cohort: HbA1c 5.7–6.4 versus 5.2–5.6, the study's recruitment
  groups. The local demographics file contains eight participants in each
  group. Laboratory HbA1c is approved as the target instead of deriving a label
  from CGM; HbA1c must never enter the features. This estimates resemblance to
  study groups, not a diagnosis or a calibrated probability of disease.
- CGM excursions: the paper's `PersHigh` means glucose above the prior 24-hour
  mean plus one standard deviation. A binary `PersHigh` versus all other
  eligible observations would be an explicit adaptation of the paper's
  three-class task, not a diagnosis or a participant-level metabolic-risk label.
  This alternative is not selected for the prototype.

For a participant-level regression, mean observed CGM glucose over the same
observation interval as the wearable features is the selected target. It
requires coverage reporting and is not an instantaneous glucose estimate.
The [companion study](https://pmc.ncbi.nlm.nih.gov/articles/PMC8208014/)
also investigates participant-level glucose-summary targets. Predictions are
retrospective summaries available only after the observation interval closes;
they must not be presented as forecasts using future wearable information.

Implemented validation: leave one complete BIG IDEAs participant out at a time;
all their windows stay in the held-out fold. Imputation/scaling and any model
selection happen only within training participants (three inner grouped folds
inside each outer held-out-participant fold). Report subject-level errors and pooled out-of-fold
metrics where defined, rather than treating sensor rows as independent people.
IMU50 is application-only: no target imputation, cohort matching, or tuning on
its predictions. Its units and cross-device feature comparability still need
verification for validated applications. The user has explicitly authorized
provisional unit inference and cross-device compatibility as hackathon working
assumptions; this is no longer a blocker for exploratory development.

Implemented candidate comparison: regularized logistic regression for classification,
Ridge and Bayesian Ridge for regression, and small/shallow random forests as
nonlinear comparators. A tiny regularized MLP is included as an exploratory
candidate, not presumed better because the recordings contain millions of
rows. There are only 15 eligible independent labeled participants. Include dummy
class-prior/mean baselines. Bayesian Ridge's predictive standard deviation is
conditional on its model assumptions, not a calibrated cross-device or clinical
confidence interval. Logistic output is a study-group score, not disease risk.
If model choice uses validation scores, evaluate that choice inside nested
subject-grouped folds; do not report the winning score from a broad search as
an unbiased final estimate. No neural-network early-stopping split may mix
windows from the same participant across train/validation.

The IMU50 archive's `README.md`, `utils.py`, and `example_usage.ipynb` were
inspected directly. They document IMU 128 Hz, PPG 25 Hz, and temperature once
per minute, but do not explicitly define the exported accelerometer or
temperature units. Manufacturer sensor ranges are not proof of the scaling in
these processed CSVs. IMU50 has raw PPG, not the ready-made HR series used by
the BIG IDEAs pilot. The prototype will retain these distinctions rather than
claiming the devices or their raw PPG amplitudes are interchangeable.

### Provisional unit policy: sensor-units-v1-provisional

The user's explicit instruction to infer plausible units supersedes the earlier
requirement to wait for an export data dictionary. Preserve raw inputs and tag
all IMU50-derived outputs as inferred; do not describe the assumption as a
verified dataset fact or validated cross-device calibration.

| Signal | BIG IDEAs | IMU50 working assumption | Common representation |
| --- | --- | --- | --- |
| Acceleration | E4 counts; divide by 64 | Already g; multiply by 1 | g |
| Skin temperature | Documented Celsius | Already Celsius; no conversion | °C |
| Gyroscope | Absent | Likely degrees/second; retained raw, excluded from shared model | Not shared |
| Raw BVP/PPG amplitude | Device-specific BVP | Device-specific optical channels | Not directly comparable |

Evidence: `python3 databricks/tiger/audit_sensor_units.py` reads the first
250,000 ACC rows per dataset, the first 250,000 BIG IDEAs TEMP rows, and all
6,777 IMU50 00 temperature rows. It does not use labels, predictions, or fit a
scaling factor to force the two distributions to match.

- BIG IDEAs vector median after documented ÷64: 0.997678 g.
- IMU50 vector median without scaling: 0.990415. A gravity component near one
  supports g; dividing by 9.80665 would give about 0.101 g instead.
- IMU50 temperature range: 26.98–36.20, median 33.03. This supports Celsius
  for wrist temperature, alongside the manufacturer's Celsius specification.
- IMU50 sampled maximum absolute gyro axis: 749.7561, consistent with a
  degrees/second interpretation and the device's ±2000 dps specification.
  This is weaker evidence than acceleration's gravity reference.

References: [Empatica E4 units](https://www.empatica.com/blog/decoding-wearable-sensor-signals-what-to-expect-from-your-e4-data/),
[LEAP device specifications](https://ametris.com/actigraph-leap), and
[IMU50 source sampling rates](https://zenodo.org/records/21468410).

The shared pilot uses one-minute bins: 1,920 expected ACC samples for E4 and
7,680 for IMU50. It computes each sample's ENMO before averaging, retains
missingness/overfull-minute flags, and does not fabricate higher-frequency
temperature measurements. This standardizes units and time bins, not bandwidth,
calibration, wearing position, or PPG quality. No exercise categories, clinical
thresholds, distribution matching, or glucose-derived input features are added.
Missing timestamps/numeric values are counted in `sensor_parse_audit_pilot`.
Repeated whole-second IMU50 rows are retained, not deduplicated.

New tables (under the `workspace` catalog):

- `wolfhacks_bronze.big_ideas_acc_pilot`
- `wolfhacks_bronze.big_ideas_temperature_pilot`
- `wolfhacks_bronze.imu50_acc_pilot`
- `wolfhacks_bronze.imu50_temperature_pilot`
- `wolfhacks_silver.shared_sensor_minute_pilot`
- `wolfhacks_silver.sensor_parse_audit_pilot`

Silver carries `unit_status`, `unit_policy_version`, and
`cross_device_validated=false`. These and participant IDs are provenance, not
model inputs. The existing `activity_minute_pilot` retains BIG IDEAs HR analysis;
the shared ACC/temperature pilot does not invent IMU50 heart rate from raw PPG.

Verified deployed update `bef1fc57-f182-4d48-8363-2e530af30758` completed:

| Participant | ACC rows | Temperature rows | Shared minutes |
| --- | ---: | ---: | ---: |
| big_ideas:001 | 20,296,428 | 2,537,040 | 10,580 |
| imu50:00 | 52,024,832 | 6,777 | 6,777 |

Both have zero invalid timestamp/ACC/temperature numeric rows in the parser
audit and zero overfull ACC minutes. This confirms parsing and aggregation,
not physiological validity, identical device behavior, or model performance.
The minute key is confirmed `TIMESTAMP_NTZ` in the published shared table.

### October 4 submission: finite replay and dashboard handoff

The submission deadline is **11 a.m. Eastern on October 4, 2026**. Prioritize a
recordable finite test before then; the proposed noon–3 p.m. judging replay is
separate and is not scheduled by this test.

`demo_smoke_test.run.json` runs seven sequential, bounded tasks: preload history,
emit one simulated hour, ingest Tiger into Bronze, publish a new 24-hour window,
then repeat the emit/ingest/publish sequence once. It exits automatically; there
is no continuous stream or schedule. Default session: `submission-smoke-v1`.
Default simulated replay anchor: `2026-10-04T04:00:00Z`. Event timestamps are
simulated time, not the wall-clock time at which this accelerated test executes.

This tests **direct Tiger writes → existing Bronze ingestion → demo rolling
aggregation → Tiger dashboard publication**. It does not exercise HTTP API
authentication, a production live sensor, or a Lakeflow continuous update.
History is preloaded from prepared archive-derived minute summaries, not sent
through the live event path. Each of the two replay batches contains 1,020
minute-summary events (17 people × 60 minutes), not raw 32/128 Hz samples.
Each producer immediately retries the batch and requires zero duplicate inserts.
All outputs remain demo-only and excluded from model training.

Backend/frontend handoff:

- Tiger **`gold.dashboard_latest`**: one row per session/person; return its
  `payload` JSON object to the frontend, with `published_at` as a separate
  wall-clock freshness field if useful.
- Tiger **`gold.dashboard_windows`**: all hourly 24-hour metric windows. Filter
  by session AND participant; do not combine independently replayed sessions.
- `dashboard_queries.sql`: parameterized latest/trend queries.
- `dashboard_contract.ts`: payload types and nullable-field meanings.
- `dashboard_sample.json`: exported snapshots plus a full seven-day example
  trend; usable offline without Databricks or database credentials.
- The final smoke-test notebook output contains `latest` for all 17 people and
  `example_trend` for BIG IDEAs 001, suitable as an offline frontend fixture.
- Use a backend-only read-only database role. Never put the Tiger admin password
  in a frontend bundle or commit secrets. A read-only role is not provisioned by
  this smoke test.

Display motion in **g**, wrist skin temperature in **°C**, and heart rate in
**bpm**. Show a visible “Simulated replay” label, `synthetic_fraction`, and
missing HR as “Unavailable” (IMU50 has no derived HR yet). Do not label motion
as validated exercise intensity or skin temperature as fever/body temperature.
The original smoke test left `wearable_risk_indicator` **null**. The rolling-risk
integration below replaces that pending value with a separately trained 24-hour
score; it does not substitute the whole-recording classifier.
Participant 015 is a demo persona only, still excluded from model evaluation.

To repeat the same test (idempotent, no new timeline):

```bash
databricks jobs submit --profile wolfhacks \
  --json @databricks/tiger/demo_smoke_test.run.json --no-wait
```

Reusing the session preserves its event IDs and simulated clock. For a fresh
recording with visible progression, choose a NEW session ID and pass that same
`session_id` and `replay_start` to every `demo_smoke_test` task in the run JSON;
Bronze tasks need no session parameter. Run prepare first to show historical
charts, then the first emit/ingest/refresh sequence, then the second sequence.
Do not delete/reset the existing session to make it look live. A session refuses
to change its fixture or anchor after creation. Source archives and model tables
are untouched. A complete run should publish 2,890 windows (17 × 170) and
2,040 unique live-path events, with all rolling windows containing 1,440 minutes.

This 17-person test is not evidence that all 66 participants are loaded or that
the pending 24-hour risk model has been validated. The archive pipeline and
these small replay summaries are distinct scales of processing.

For a recording, run these from the repository root, **waiting for each run to
succeed before proceeding**. Use the same new session ID for all three phases:

```bash
python3 databricks/tiger/run_demo_test.py --session recording-01 --phase prepare
# Point the backend at session recording-01 and show the preloaded charts.
python3 databricks/tiger/run_demo_test.py --session recording-01 --phase hour1
# Show the new window and updated metrics after this run succeeds.
python3 databricks/tiger/run_demo_test.py --session recording-01 --phase hour2
```

The helper prints each Databricks run ID; inspect it in Jobs & Pipelines or use
`databricks jobs get-run RUN_ID --profile wolfhacks`. Recording phases are
accelerated micro-batches, not minute-by-minute real-time playback. Keep the
simulated-time badge visible. The helper does not record your screen or deploy
the frontend, and no further events are produced after each phase exits.

Verified smoke test: Databricks run **779148180348142**, all seven tasks
**SUCCESS**. Baseline: 2,856 windows. First refresh: 2,873 windows and 1,020
Bronze replay events. Second refresh: **2,890 windows and 2,040 unique Bronze
replay events**, 17 participants, each window covering 1,440 demo minutes.
Both producer retries inserted **zero** duplicates. All 17 participants changed
in motion mean and/or temperature mean between baseline and final output.
`dashboard_sample.json` contains the final Tiger-read snapshots and 168 hourly
trend points for BIG IDEAs 001. The finite run terminated; no replay schedule
was created. These checks do not imply that the frontend, HTTP ingestion API,
pending rolling risk model, or full 66-person cohort has passed an end-to-end test.

### 24-hour rolling risk integration

`train_rolling_risk.py` constructs real-data, trailing 24-hour windows with
hourly ends from Silver ACC/temperature minutes. It uses the 15 previously
approved labeled BIG IDEAs participants and preserves the 015 exclusion.
Synthetic demo data is never read by training or used for evaluation.

The 12 inputs are motion mean/p90/median/std/p99, skin-temperature mean/std/p10/p90,
motion–temperature correlation, and motion/temperature first daily-harmonic
amplitudes. `rolling_risk.py` implements the same features for both training and
inference. Each window requires at least 1,152 real usable minutes (80% of the
elapsed 24 hours), with at least 30 in each relative hourly bin. This is an
engineering quality gate, not a health threshold; gaps are not interpolated.

Outer evaluation leaves one participant out; inner selection uses three folds
of the participant roster. Equal total participant weights are used in fitting,
scaling, and window-level metrics. Candidates are a prior baseline, logistic
regression at C=0.1/1, and a 64-tree depth-3 forest. Selection uses weighted
balanced accuracy, then log loss. Equal 0.5 predictions deterministically map to
class 1 for evaluation only; the UI has no validated binary risk threshold.

`wearable_risk_indicator` is **100 × the model's higher-study-group score**:
an experimental **0–100 cohort-resemblance index**, NOT a calibrated diabetes
probability, measured glucose, or future clinical-event risk. Report the new
24-hour evaluation separately from the earlier 86.67% whole-recording result.
Source-data development remains limited to 15 independent labeled people.

Saved releases: `workspace.wolfhacks_models.rolling_risk_releases`; artifacts:
`/Volumes/workspace/wolfhacks_models/artifacts/<model_version>/rolling_risk.joblib`.
Real held-out window predictions are stored in
`workspace.wolfhacks_features.rolling_risk_training_windows` with their version.

The dashboard publisher now pins a release per session in
`workspace.wolfhacks_demo.replay_risk_models`. For the 15 training participants,
demo inference uses their held-out-person model. Other participants use the
final fitted model and `risk_evaluation=application_unvalidated`. Full-model
application is not reported as held-out accuracy. Synthetic fraction and
cross-device limitations remain visible.

Scores are backfilled into the existing seven-day history and recomputed on
each published hourly window. `risk_change_24h_points` is current score minus
the score ending 24 hours earlier, or null without that prior window. The
version, feature contract, model name, held-out/application mode, and training
range flag are included in the Tiger payload. There are no inferred high/medium/
low clinical bands. The backend reads the same two dashboard objects as before.

Run training once, then publish and verify one further replay hour:

```bash
databricks jobs submit --profile wolfhacks --json @databricks/tiger/train_rolling_risk.run.json --no-wait
# Wait for successful completion before submitting publication.
databricks jobs submit --profile wolfhacks --json @databricks/tiger/rolling_risk_publish.run.json --no-wait
```

The publisher's `score_existing` mode backfills without emitting any sensor
events. `prepare` and `refresh` also score before publishing. Tiger upserts only
changed payloads, preserving grants and avoiding duplicate windows. Existing
sessions retain their pinned version; use a new session for a different model.
The local recording helper continues to work and now includes predictions.

Completed corrected training run **930895403689436**, model release
**`0006be934ae7480d922f248ddd25a17d`**: 660 qualifying real windows from all
15 approved participants. Final application estimator: `forest_depth3`.

| Real 24-hour development metric | Nested participant-held-out model | Held-out prior baseline |
| --- | ---: | ---: |
| Participant-weighted window accuracy | 60.42% | 53.33% |
| Participant-weighted window balanced accuracy | 60.03% | 50.00% |
| Participant-weighted window log loss (lower is better) | 0.8244 | 0.7651 |
| Participant-weighted window Brier loss (lower is better) | 0.2788 | 0.2857 |

Window ROC AUC is 0.5953. Averaging held-out window scores within each person
classifies 11/15 people correctly (73.33%), but that is a different aggregation
and must not be presented as 24-hour window accuracy. Neither statistic is
external validation. Log loss is worse than the prior baseline; do not claim
well-calibrated probabilities. The held-out prior's AUC is misleading because
its probability changes with the omitted person's class; use the documented
accuracy/loss comparisons instead.

The initial development artifact `7cc76a0dff4949e8b849f0fbaa57406c` is retained
for provenance but superseded: equal-prior baseline folds were sensitive to
floating-point ties around 0.5. The corrected run fixes tie handling before
publication. The selected model's reported window metrics are unchanged.
See `rolling_risk_evaluation.json` for the corrected complete report, including
per-person window counts and fold-specific selected models.

Verified publication/replay run **31022209749215** completed all four tasks in
about three minutes and stopped. The backfill scored all 2,890 existing windows;
one further replay hour added 17 windows, producing **2,907 scored windows** for
17 participants. The session now contains 3,060 unique replay events. The new
1,020-event batch's retry inserted zero duplicates. Twelve participants' scores
changed in that hour; unchanged scores are retained rather than artificially
perturbed. BIG IDEAs 001 changed from 15.73 to 16.83 index points.

`dashboard_sample.json` now contains actual scored Tiger snapshots and the last
168 hourly points for BIG IDEAs 001. The backend uses the unchanged session
`submission-smoke-v1` and unchanged `gold.dashboard_latest` /
`gold.dashboard_windows` objects. No database credentials or access grants were
created/changed by the risk integration, and no ongoing stream was scheduled.

### October 4 overnight preparation and continuous judging session

The user authorized local preparation on the connected M1 Mac until **8 a.m.
Eastern October 4**, then recording and a **noon–3 p.m.** judging replay (official
judging 12:30–2:30). No Databricks compute is started by overnight preparation.
The morning compact-data registration/test and event-time replay do use compute.

`prepare_overnight.py` downloads IMU50 subjects 01–49, smallest ZIPs first, one at
a time. It reads CSVs in 250,000-row chunks directly from the nested ZIP; it does
not expand multi-GB CSVs onto the SSD. It computes real minute summaries, then
the same clearly labeled nine-day demo fixture and 168 precomputed hourly
scores. The existing 15-person model is reused, not retrained. This processes
ACC/temperature across additional participants, not every sensor modality.

Completed compact files are uploaded through the Databricks file API to:

```text
/Volumes/workspace/wolfhacks_raw/source_files/prepared_replay/overnight-v1/imu50/<id>/
  real_minutes.parquet
  minute_bank.parquet
  history_metrics.json
  manifest.json
```

The manifest is uploaded last and contains row counts, provenance, file sizes,
and SHA-256 digests. Local processing is explicitly labeled `local_mac` rather
than claimed as Databricks raw processing. The worker only removes its own
temporary subject ZIP/partial file; those can be downloaded again from the
public source. Existing `pilot-data` files are never deleted. Task storage stops
at 9 GiB or when free disk falls below 5 GiB. An absolute alarm stops the worker
at 8 a.m. Completed outputs survive interruption and can be reused on restart.

Local controls (from the repository root):

```bash
databricks/.overnight-venv/bin/python databricks/tiger/overnight_control.py status
databricks/.overnight-venv/bin/python databricks/tiger/overnight_control.py stop
```

The initial local check on subject 00 matched 52,024,832 ACC rows, 6,777
temperature rows and 6,188 synthetic fixture minutes. It produced under 1 MB of
compact outputs and uploaded them successfully without starting compute.

At/after 8 a.m., `register_overnight.py` combines complete, integrity-checked new
subjects with the existing 17-person fixture and freezes its roster as
`overnight-v1`. Subject 00 is not counted twice. Never claim all 66 until the
actual ready roster confirms 66. The original `nine-day-v1` fixture and
`submission-smoke-v1` dashboard remain intact as the working fallback.

#### A continuous user history, not a fresh session each time

Use **`continuous-oct4-v1`** for both recording and judging after its morning
preparation succeeds. Its fixed simulated event clock starts at **7 a.m.
Eastern October 4**, with eight input days before that anchor. Each person keeps
their identity and history. The local controller persists the last successfully
processed minute and any pending job in `databricks/local-data/continuous-demo/`.

```bash
# Blocked before 8 a.m.; registers compact files, seeds history and pins a model.
databricks/.overnight-venv/bin/python databricks/tiger/continuous_demo.py prepare

# Catch up every missing minute through the current clock; no reset or duplicates.
databricks/.overnight-venv/bin/python databricks/tiger/continuous_demo.py advance

# Scheduled for noon; accepts starts only between noon and 3 p.m. on October 4.
databricks/.overnight-venv/bin/python databricks/tiger/continuous_demo.py judge --background

databricks/.overnight-venv/bin/python databricks/tiger/continuous_demo.py status
databricks/.overnight-venv/bin/python databricks/tiger/continuous_demo.py stop
```

The default judging transport uses **15-minute micro-batches**. Every simulated
minute is represented; the backend should not imply second-by-second transport.
Gaps between recording and judging are caught up in batches of at most 60 minutes.
Risk windows update hourly. Previously calculated scores are reused under the
session's pinned model, avoiding repeated seven-day inference on every batch.
Only successful complete runs advance the cursor. A retry uses stable event IDs.
At 3 p.m. no new batches are launched and the controller cancels its own pending
run, if needed. A partial cancelled batch must be reported, not called complete.

Latest payloads also expose `latest_sensor_time`, `latest_motion_g`,
`latest_skin_temperature_c`, `latest_hr_bpm`, and `latest_sensor_is_synthetic`.
Use those for current sensor cards; use `window_end` for the last completed
hourly risk window and `published_at` for actual processing freshness. Show the
simulated-data badge and indicate a paused/stale pipeline honestly even though
the underlying simulated timeline is continuous.

Local schedules check preparation every 30 minutes, launch judging at noon, and
verify stopping at 3 p.m. They need this Mac on, lid open, connected to power,
and the Codex app running. A temporary sleep-prevention process covers the demo
window; it does not change persistent power settings. Public-source speed and
Databricks Free Edition quotas still limit what can be completed. The expanded
roster's remote registration and replay are verified in the morning, not by the
storage-only overnight upload.

#### Morning verification — October 4, 2026

The expanded session **`continuous-oct4-v1` is verified for all 66 participants**
(16 BIG IDEAs + 50 IMU50; separate identities, not matched subjects).
All 49 additional uploaded manifests were checked, and registration verified
file hashes before freezing the roster. Preparation run `220148463930322`
succeeded and published 11,088 scored history windows to Tiger.

Catch-up runs `303830614582900` and `1059862920828150` then succeeded through
offset 11600 (exclusive): 5,280 unique replay minutes, 80 per participant,
covering 7:00–8:19 a.m. Eastern with no missing/duplicate Bronze minute keys.
The first batch's duplicate retry inserted zero rows. Tiger now has 11,154
scored windows, 66 latest participant payloads, sensor time 8:19 a.m. and last
completed risk window 8:00 a.m. The bounded morning run is stopped, not live;
the noon controller resumes this same cursor and catches up intervening minutes.

Backend: query `gold.dashboard_latest` and `gold.dashboard_windows` with
`session_id = 'continuous-oct4-v1'` using the read-only role. The original
`submission-smoke-v1` session remains separate. A saved 66-person response and
168-point example trend are in
`databricks/local-data/continuous-demo/latest_dashboard.json` (local, ignored).
See `dashboard_queries.sql` for parameterized queries. These are experimental
cohort-similarity scores, not validated diabetes probabilities; synthetic demo
extensions remain labeled and excluded from training.

The local IMU50 preparation (including the subject-00 validation) read
3,031,935,104 acceleration samples and 394,867 temperature rows. This was local
raw preprocessing, not a claim that Databricks processed those raw rows overnight.
Compact local outputs occupy about 48 MB; existing pilot files were preserved.
