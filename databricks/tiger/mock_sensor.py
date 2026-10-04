#!/usr/bin/env python3
"""Send mock events through the same HTTP contract as a future real sensor."""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4


def send_event(url: str, api_key: str, payload: dict[str, object]) -> dict[str, object]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        },
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default=os.environ.get("SENSOR_API_URL", "http://127.0.0.1:8000/v1/events"),
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("SENSOR_INGEST_API_KEY"),
    )
    parser.add_argument("--sensor-id", default="mock-sensor-001")
    parser.add_argument("--measurement-name", default="demo_signal")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument(
        "--count",
        type=int,
        default=20,
        help="Events to send; 0 runs until interrupted (default: 20)",
    )
    parser.add_argument(
        "--anomaly-every",
        type=int,
        default=0,
        help="Add a controlled spike every N events; 0 disables it",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not args.api_key:
        raise SystemExit("Set SENSOR_INGEST_API_KEY or pass --api-key")
    if args.interval <= 0:
        raise SystemExit("--interval must be greater than zero")
    if args.count < 0 or args.anomaly_every < 0:
        raise SystemExit("--count and --anomaly-every cannot be negative")

    sequence = 0
    try:
        while args.count == 0 or sequence < args.count:
            sequence += 1
            value = 50 + 8 * math.sin(sequence / 5) + random.uniform(-1, 1)
            if args.anomaly_every and sequence % args.anomaly_every == 0:
                value += 30
            event = {
                "event_id": str(uuid4()),
                "sensor_id": args.sensor_id,
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "sequence_number": sequence,
                "schema_version": 1,
                "measurements": {args.measurement_name: round(value, 3)},
            }
            result = send_event(args.url, args.api_key, event)
            print(f"sequence={sequence} result={result}")
            if args.count == 0 or sequence < args.count:
                time.sleep(args.interval)
    except (HTTPError, URLError) as error:
        raise SystemExit(f"sensor request failed: {error}") from error
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    main()
