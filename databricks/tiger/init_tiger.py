#!/usr/bin/env python3
"""Apply the idempotent Tiger schema using TIGER_DATABASE_URL."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg


database_url = os.environ.get("TIGER_DATABASE_URL")
if not database_url:
    raise SystemExit(
        "Set TIGER_DATABASE_URL to the Tiger PostgreSQL connection string "
        "with sslmode=require."
    )

schema_path = Path(__file__).with_name("schema.sql")
with psycopg.connect(database_url) as connection:
    connection.execute(schema_path.read_text(encoding="utf-8"))
    row = connection.execute(
        """
        SELECT count(*),
               pg_size_pretty(hypertable_size('raw.sensor_events'))
        FROM raw.sensor_events
        """
    ).fetchone()

print(f"Tiger schema ready: raw.sensor_events rows={row[0]}, size={row[1]}")
