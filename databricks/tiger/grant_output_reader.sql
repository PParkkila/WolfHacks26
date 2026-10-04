-- Run as the output-object owner (currently tsdbadmin), not the reader.
-- Applies only to published outputs in gold; no raw-data or write grants.
GRANT CONNECT ON DATABASE tsdb TO dashboard_reader;
GRANT USAGE ON SCHEMA gold TO dashboard_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA gold TO dashboard_reader;

-- Includes future tables and views created by this executing owner in gold.
-- If another role starts creating outputs, apply this default as that role too.
ALTER DEFAULT PRIVILEGES IN SCHEMA gold
    GRANT SELECT ON TABLES TO dashboard_reader;
