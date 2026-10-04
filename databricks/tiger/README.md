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
/Volumes/main/wolfhacks_raw/source_files/
main.wolfhacks_bronze.sensor_events
```

If you cannot write to the `main` catalog, replace `main` in the SQL and in the
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
volume_root = /Volumes/main/wolfhacks_raw/source_files/big_ideas
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
volume_root = /Volumes/main/wolfhacks_raw/source_files/imu50
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
display(dbutils.fs.ls("/Volumes/main/wolfhacks_raw/source_files/big_ideas/001"))
display(dbutils.fs.ls("/Volumes/main/wolfhacks_raw/source_files/imu50/00"))
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

## 7. Store Tiger credentials in Databricks Secrets

Create a secret scope called `wolfhacks`, then add:

```text
tiger-user
tiger-password
```

Do this in the Databricks secret UI or CLI. Do not put the password in notebook
widgets, cluster environment variables visible to other users, or Git.

Allow network traffic from the Databricks compute plane to the Tiger service.
Depending on the workspace, this means permitting the workspace egress IP or
configuring private networking.

## 8. Configure the Tiger-to-Bronze job

`tiger_to_bronze.py` is compatible with serverless compute. Its first cell
installs the Python PostgreSQL client, so no cluster or Maven JDBC library is
required. Run that first cell and allow the Python restart before continuing.

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

Run it once manually. It reads Tiger events using `received_at`, deliberately
rereads a short lookback window, and uses Delta `MERGE` so retries do not create
duplicates. Then schedule it every one to five minutes for the prototype.

Validate in Databricks SQL:

```sql
SELECT sensor_id,
       count(*) AS events,
       min(observed_at) AS first_event,
       max(observed_at) AS latest_event
FROM main.wolfhacks_bronze.sensor_events
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

## 10. What comes next

After both landing paths work, the next development increment is:

1. inspect the actual historical and real-device fields;
2. create typed Bronze parsing for each source;
3. normalize them into a shared Silver sensor schema;
4. create subject/window features without glucose inputs;
5. implement subject-level model validation.

Do not start full IMU50 parsing or Tiger replication until the one-subject
pilot has verified file sizes, schemas, timestamps, and expected cost.
