CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE SCHEMA IF NOT EXISTS raw;

-- Live sensor events arrive through the ingestion API. Keep the original
-- event envelope in JSONB until the actual production sensor contract is
-- known; observed_at is timezone-aware because live devices should send UTC.
CREATE TABLE IF NOT EXISTS raw.sensor_events (
    observed_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sensor_id TEXT NOT NULL,
    event_id UUID NOT NULL,
    sequence_number BIGINT,
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    raw_payload JSONB NOT NULL CHECK (jsonb_typeof(raw_payload) = 'object'),
    UNIQUE (sensor_id, observed_at, event_id)
);

SELECT create_hypertable(
    'raw.sensor_events',
    by_range('observed_at', INTERVAL '1 day'),
    if_not_exists => TRUE
);

-- Databricks incremental pulls use received_at with a lookback window. The
-- unique event key makes replayed device requests idempotent.
CREATE INDEX IF NOT EXISTS sensor_events_received_at_idx
    ON raw.sensor_events (received_at DESC);

CREATE INDEX IF NOT EXISTS sensor_events_sensor_time_idx
    ON raw.sensor_events (sensor_id, observed_at DESC);
