#!/usr/bin/env python3
"""Authenticated HTTP ingestion API for live sensor events."""

from __future__ import annotations

import hmac
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, status
from psycopg_pool import ConnectionPool
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator


DATABASE_URL = os.environ.get("TIGER_DATABASE_URL", "")
INGEST_API_KEY = os.environ.get("SENSOR_INGEST_API_KEY", "")
POOL_SIZE = int(os.environ.get("TIGER_POOL_SIZE", "5"))

pool = ConnectionPool(
    conninfo=DATABASE_URL,
    min_size=1,
    max_size=POOL_SIZE,
    open=False,
)


class SensorEvent(BaseModel):
    """Versioned raw event contract shared by mock and real sensors."""

    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    sensor_id: str = Field(min_length=1, max_length=200)
    observed_at: datetime
    sequence_number: int | None = Field(default=None, ge=0)
    schema_version: int = Field(default=1, ge=1)
    measurements: dict[str, Any] = Field(min_length=1)

    @field_validator("observed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must include a timezone, preferably UTC")
        return value


class SensorEventBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[SensorEvent] = Field(min_length=1, max_length=1000)


class IngestResult(BaseModel):
    accepted: int
    inserted: int
    duplicates: int


def require_api_key(
    x_api_key: Annotated[str | None, Header()] = None,
) -> None:
    if not x_api_key or not hmac.compare_digest(x_api_key, INGEST_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid API key",
        )


def insert_events(events: list[SensorEvent]) -> IngestResult:
    statement = """
        INSERT INTO raw.sensor_events (
            observed_at,
            sensor_id,
            event_id,
            sequence_number,
            schema_version,
            raw_payload
        )
        SELECT (event->>'observed_at')::timestamptz,
               event->>'sensor_id',
               (event->>'event_id')::uuid,
               (event->>'sequence_number')::bigint,
               (event->>'schema_version')::integer,
               event
        FROM jsonb_array_elements(%s::jsonb) AS event
        ON CONFLICT (sensor_id, observed_at, event_id) DO NOTHING
        RETURNING event_id
    """
    payload = [event.model_dump(mode="json") for event in events]
    with pool.connection() as connection:
        inserted = len(connection.execute(statement, (Jsonb(payload),)).fetchall())
    return IngestResult(
        accepted=len(events),
        inserted=inserted,
        duplicates=len(events) - inserted,
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not DATABASE_URL:
        raise RuntimeError("TIGER_DATABASE_URL is required")
    if not INGEST_API_KEY:
        raise RuntimeError("SENSOR_INGEST_API_KEY is required")
    pool.open()
    pool.wait()
    try:
        yield
    finally:
        pool.close()


app = FastAPI(title="WolfHacks Sensor Ingestion", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    with pool.connection() as connection:
        connection.execute("SELECT 1")
    return {"status": "ok"}


@app.post(
    "/v1/events",
    response_model=IngestResult,
    dependencies=[Depends(require_api_key)],
)
def ingest_event(event: SensorEvent) -> IngestResult:
    return insert_events([event])


@app.post(
    "/v1/events/batch",
    response_model=IngestResult,
    dependencies=[Depends(require_api_key)],
)
def ingest_batch(batch: SensorEventBatch) -> IngestResult:
    return insert_events(batch.events)
