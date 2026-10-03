-- Run in a Databricks SQL editor. Change `main` if your writable catalog has
-- another name.
CREATE SCHEMA IF NOT EXISTS main.wolfhacks_raw;
CREATE SCHEMA IF NOT EXISTS main.wolfhacks_bronze;

-- Historical ZIP/CSV sources belong here, backed by cloud object storage.
CREATE VOLUME IF NOT EXISTS main.wolfhacks_raw.source_files;

-- Incremental copies of Tiger's live events land here before Silver parsing.
CREATE TABLE IF NOT EXISTS main.wolfhacks_bronze.sensor_events (
    observed_at TIMESTAMP,
    received_at TIMESTAMP,
    sensor_id STRING,
    event_id STRING,
    sequence_number BIGINT,
    schema_version INT,
    raw_payload STRING,
    bronze_ingested_at TIMESTAMP
) USING DELTA;
