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

### BIG IDEAs

Run `stage_big_ideas_subject.py` with:

```text
subject_id = 001
volume_root = /Volumes/main/wolfhacks_raw/source_files/big_ideas
```

Then repeat for `002` through `016`. The notebook downloads each public CSV
directly from PhysioNet and also stages `Demographics.csv`.

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
expanded CSV data. Ensure the Databricks driver has at least 2 GB of free local
disk for the nested ZIP. The expanded CSV is written directly to the Volume.

Verify the landing paths:

```python
display(dbutils.fs.ls("/Volumes/main/wolfhacks_raw/source_files/big_ideas/001"))
display(dbutils.fs.ls("/Volumes/main/wolfhacks_raw/source_files/imu50/00"))
```

Do not interpret IMU50 units, timezone, or coded subject metadata until its
source documentation supports that interpretation. Its 128 Hz IMU and 25 Hz
PPG rows repeat whole-second timestamps, so future Bronze parsing must preserve
the source row/sample ordinal.

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

Attach the PostgreSQL JDBC driver to the Databricks job compute. If it is not
already present in the runtime, add the Maven library:

```text
org.postgresql:postgresql:42.7.7
```

Create a Databricks job for `tiger_to_bronze.py` with these parameters:

```text
tiger_host          = your Tiger hostname
tiger_port          = 5432 or the port from Tiger
tiger_database      = database name from the connection string
secret_scope        = wolfhacks
user_secret_key     = tiger-user
password_secret_key = tiger-password
target_table        = main.wolfhacks_bronze.sensor_events
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
