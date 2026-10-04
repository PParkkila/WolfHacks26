"""Pure event adapter for prepared demo minutes; importing/running sends nothing.

The future sender must persist one session_id and replay_start for retries.
Minute offsets 0..11519 preload history; 11520..12959 are the reserved live day.
This contract transports minute summaries, not fabricated high-frequency samples.
"""

from datetime import datetime, timedelta, timezone
import math
from uuid import NAMESPACE_URL, uuid5


def event_for_minute(row: dict, session_id: str, replay_start: datetime) -> dict:
    if not session_id or len(session_id) > 60:
        raise ValueError("Use a nonempty demo session ID of at most 60 characters")
    if replay_start.tzinfo is None or replay_start.utcoffset() is None:
        raise ValueError("replay_start must be timezone-aware")
    if row.get("demo_only") is not True or row.get("training_eligible") is not False:
        raise ValueError("Only explicitly isolated demo rows may use this adapter")
    offset = row["minute_offset"]
    if type(offset) is not int or not 0 <= offset < 12960:
        raise ValueError("Expected a minute within the prepared nine-day fixture")
    numeric = {}
    for key in ("enmo_mean_g", "enmo_std_g", "enmo_p95_g", "temperature_mean_c", "hr_mean_bpm"):
        value = row.get(key)
        if value is not None:
            value = float(value)
            if not math.isfinite(value):
                raise ValueError(f"Non-finite {key}")
        numeric[key] = value
    if numeric["enmo_mean_g"] is None or numeric["temperature_mean_c"] is None:
        raise ValueError("Demo minute is missing its required motion/temperature tuple")
    timestamp = replay_start.astimezone(timezone.utc) + timedelta(minutes=offset - 11520)
    identity = f"wolfhacks-demo/{session_id}/{row['fixture_id']}/{row['demo_participant_key']}/{offset}"
    return {
        "event_id": str(uuid5(NAMESPACE_URL, identity)),
        "sensor_id": f"demo:{session_id}:{row['source_participant_key']}",
        "observed_at": timestamp.isoformat(), "sequence_number": offset, "schema_version": 2,
        "measurements": {
            "contract": "demo_minute_summary_v1", **numeric,
            "demo": {
                "demo_only": True, "training_eligible": False,
                "fixture_id": row["fixture_id"], "session_id": session_id,
                "source_participant_key": row["source_participant_key"],
                "is_synthetic": row["is_synthetic"], "provenance": row["provenance"],
                "donor_source_clock": row["donor_source_clock"],
                "intended_source_clock": row["intended_source_clock"],
                "unit_status": row["unit_status"], "generation_policy": row["generation_policy"],
            },
        },
    }
