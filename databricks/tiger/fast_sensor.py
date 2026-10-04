#!/usr/bin/env python3
"""One-second latest-sensor simulation in Tiger; canonical minute history only.

Credentials are read into memory from the existing Databricks secret scope.
Interpolated snapshots are explicitly synthetic, never measured 1 Hz samples.
"""
import argparse
import base64
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import signal
import ssl
import subprocess
import sys
import time

import pg8000.native
from demo_replay_payload import event_for_minute
from continuous_demo import ANCHOR, CLI, ROOT, SESSION, STOP_AT

BANK = ROOT / "live_bank.jsonl"
STATE = ROOT / "sensor_state.json"
stop_requested = False


def connect():
    def secret(key):
        result = subprocess.run([CLI, "secrets", "get-secret", "wolfhacks", key,
                                 "--profile", "wolfhacks", "--output", "json"],
                                check=True, capture_output=True, text=True, timeout=30)
        return base64.b64decode(json.loads(result.stdout)["value"]).decode()
    return pg8000.native.Connection(host="hi70ycj0r6.b4t1dqdug8.tsdb.cloud.timescale.com",
        port=31994, database="tsdb", user=secret("tiger-user"), password=secret("tiger-password"),
        ssl_context=ssl.create_default_context(), timeout=15)


def bootstrap(connection):
    connection.run("""CREATE TABLE IF NOT EXISTS gold.sensor_latest (
        session_id text NOT NULL, participant_key text NOT NULL,
        observed_at timestamptz NOT NULL, payload jsonb NOT NULL,
        published_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY(session_id, participant_key))""")
    connection.run("""CREATE OR REPLACE VIEW gold.dashboard_live AS
        SELECT d.session_id, d.participant_key, d.window_end,
               d.published_at AS analytics_published_at, s.published_at AS sensor_published_at,
               d.payload || coalesce(s.payload, '{}'::jsonb) AS payload
        FROM gold.dashboard_latest d LEFT JOIN gold.sensor_latest s
          ON s.session_id=d.session_id AND s.participant_key=d.participant_key""")
    # Preserve the established access boundary: only existing dashboard readers.
    roles = connection.run("""SELECT DISTINCT grantee FROM information_schema.table_privileges
        WHERE table_schema='gold' AND table_name='dashboard_latest'
          AND privilege_type='SELECT' AND grantee<>current_user AND grantee<>'PUBLIC'""")
    for (role,) in roles:
        quoted = '"' + role.replace('"', '""') + '"'
        connection.run(f"GRANT SELECT ON gold.sensor_latest, gold.dashboard_live TO {quoted}")
    return [r[0] for r in roles]


def sensor_payload(previous, current, fraction, timestamp):
    def interpolate(column):
        a, b = previous.get(column), current.get(column)
        return None if a is None or b is None else float(a) + (float(b)-float(a))*fraction
    return {"latest_sensor_time": timestamp.isoformat(),
        "latest_motion_g": interpolate("enmo_mean_g"),
        "latest_skin_temperature_c": interpolate("temperature_mean_c"),
        "latest_hr_bpm": interpolate("hr_mean_bpm"),
        "latest_sensor_is_synthetic": True,
        "latest_sensor_generation_policy": "linear_interpolation_of_demo_minute_summaries",
        "latest_sensor_source_resolution_seconds": 60,
        "latest_sensor_update_interval_seconds": 1}


def write_state(value):
    temporary = STATE.with_suffix(".json.part")
    temporary.write_text(json.dumps(value, indent=2))
    os.replace(temporary, STATE)


def run():
    global stop_requested
    lock = (ROOT/"sensor.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    def stop(*_):
        global stop_requested
        stop_requested = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    session = json.loads((ROOT/"state.json").read_text())
    if not session["ready"] or session["session_id"] != SESSION or session["anchor"] != ANCHOR:
        raise ValueError("Require the existing prepared continuous session")
    bank = {}
    with BANK.open() as source:
        for line in source:
            row = json.loads(line)
            bank.setdefault(row["source_participant_key"], {})[row["minute_offset"]] = row
    if len(bank) != 66 or any(set(rows) != set(range(11519, 12960)) for rows in bank.values()):
        raise ValueError("Incomplete frozen sensor bank")
    anchor = datetime.fromisoformat(ANCHOR)
    previous_state = json.loads(STATE.read_text()) if STATE.exists() else {}
    last_minute = previous_state.get("last_minute", 11520 + int((time.time()-anchor.timestamp())//60)-2)
    connection = None
    ticks = previous_state.get("ticks", 0)
    errors = 0
    try:
        while time.time() < STOP_AT and not stop_requested and not (ROOT/"STOP").exists():
            started = time.monotonic()
            try:
                if connection is None:
                    connection = connect()
                    print(json.dumps({"started": True, "read_only_roles": bootstrap(connection)}), flush=True)
                now = datetime.now(timezone.utc).replace(microsecond=0)
                elapsed = now.timestamp() - anchor.timestamp()
                offset = 11520 + int(elapsed//60)
                if not 11520 <= offset < 12960:
                    raise ValueError("Outside reserved replay day")
                snapshots = []
                events = []
                for key, rows in bank.items():
                    snapshots.append({"session_id": SESSION, "participant_key": f"demo:{key}",
                        "observed_at": now.isoformat(),
                        "payload": sensor_payload(rows[offset-1], rows[offset], (elapsed % 60)/60, now)})
                    for minute in range(max(11520, last_minute+1), offset):
                        events.append(event_for_minute(rows[minute], SESSION, anchor))
                connection.run("START TRANSACTION")
                connection.run("""INSERT INTO gold.sensor_latest(session_id, participant_key, observed_at, payload)
                    SELECT x->>'session_id', x->>'participant_key', (x->>'observed_at')::timestamptz, x->'payload'
                    FROM jsonb_array_elements(CAST(:data AS jsonb)) x
                    ON CONFLICT(session_id, participant_key) DO UPDATE SET observed_at=EXCLUDED.observed_at,
                        payload=EXCLUDED.payload, published_at=now()
                    WHERE gold.sensor_latest.observed_at < EXCLUDED.observed_at""", data=json.dumps(snapshots, allow_nan=False))
                if events:
                    connection.run("""INSERT INTO raw.sensor_events
                        (observed_at,sensor_id,event_id,sequence_number,schema_version,raw_payload)
                        SELECT (x->>'observed_at')::timestamptz,x->>'sensor_id',(x->>'event_id')::uuid,
                            (x->>'sequence_number')::bigint,(x->>'schema_version')::integer,x
                        FROM jsonb_array_elements(CAST(:data AS jsonb)) x
                        ON CONFLICT(sensor_id,observed_at,event_id) DO NOTHING""", data=json.dumps(events, allow_nan=False))
                connection.run("COMMIT")
                last_minute = offset-1
                ticks += 1
                errors = 0
                write_state({"pid": os.getpid(), "session_id": SESSION, "participants": 66,
                    "status": "running", "ticks": ticks, "last_minute": last_minute,
                    "latest_sensor_time": now.isoformat(), "last_write_seconds": time.monotonic()-started})
                if ticks % 60 == 0:
                    print(json.dumps({"ticks": ticks, "sensor_time": now.isoformat()}), flush=True)
            except Exception as error:
                errors += 1
                print(json.dumps({"error_type": type(error).__name__, "consecutive_errors": errors}), flush=True)
                if connection:
                    try:
                        connection.close()
                    except Exception:
                        pass
                connection = None
                if errors >= 5:
                    write_state({"status": "needs_attention", "pid": os.getpid(), "ticks": ticks,
                        "last_minute": last_minute, "error_type": type(error).__name__})
                    return
            time.sleep(max(0.01, (min(15, 2**errors) if errors else 1) - (time.monotonic()-started)))
    finally:
        if connection:
            connection.close()
    write_state({"status": "stopped", "pid": os.getpid(), "ticks": ticks, "last_minute": last_minute})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--background", action="store_true")
    args = parser.parse_args()
    if args.background:
        if not time.time() < STOP_AT or not BANK.exists() or (ROOT/"STOP").exists():
            raise SystemExit("Require downloaded bank, active demo window, and no STOP marker")
        with (ROOT/"sensor.lock").open("a") as probe:
            try:
                fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise SystemExit("Sensor sender already running")
        with (ROOT/"sensor.log").open("a") as log:
            process = subprocess.Popen([sys.executable, "-u", str(Path(__file__).resolve())],
                stdout=log, stderr=log, start_new_session=True)
            subprocess.Popen(["/usr/bin/caffeinate", "-i", "-s", "-w", str(process.pid)],
                stdout=log, stderr=log, start_new_session=True)
        print(json.dumps({"sensor_pid": process.pid}))
    else:
        run()
