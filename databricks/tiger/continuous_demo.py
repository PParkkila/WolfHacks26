#!/usr/bin/env python3
"""Persistent event-clock replay: morning preparation, catch-up, noon–3 judging.

No overnight compute: prepare is blocked until 08:00 Eastern Oct 4. The same
session/anchor/cursor is retained across recording and judging. Events cover
every simulated minute; transport is micro-batched, not a production device.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]/"local-data"/"continuous-demo"
REMOTE = "/Workspace/Users/pbparkki@ncsu.edu/WolfHacks26/databricks/tiger/"
SESSION = "continuous-oct4-v1"
ANCHOR = "2026-10-04T07:00:00-04:00"
PREP_AT = datetime.fromisoformat("2026-10-04T08:00:00-04:00").timestamp()
START_AT = datetime.fromisoformat("2026-10-04T12:00:00-04:00").timestamp()
STOP_AT = datetime.fromisoformat("2026-10-04T15:00:00-04:00").timestamp()
CLI = "/opt/homebrew/bin/databricks"


def api(*arguments):
    result = subprocess.run([CLI, *arguments, "--profile", "wolfhacks", "--output", "json"],
                            check=True, capture_output=True, text=True, timeout=90)
    return json.loads(result.stdout or "{}")


def save(state):
    path = ROOT/"state.json"
    temp = ROOT/"state.json.part"
    temp.write_text(json.dumps(state, indent=2))
    os.replace(temp, path)


def tasks_for(state, mode, start=11520, end=11580):
    common = {"session_id": SESSION, "fixture_id": state["fixture_id"], "replay_start": ANCHOR,
              "risk_model_version": "0006be934ae7480d922f248ddd25a17d",
              "start_offset": str(start), "end_offset": str(end)}
    def notebook(key, name, params, parent=None):
        task = {"task_key": key, "notebook_task": {"notebook_path": REMOTE+name, "base_parameters": params}}
        if parent:
            task["depends_on"] = [{"task_key": parent}]
        return task
    if mode == "prepare":
        tasks = []
        if state["fixture_id"] == "overnight-v1":
            tasks.append(notebook("register", "register_overnight", {}))
        tasks.append(notebook("prepare", "demo_smoke_test", {**common, "mode": "prepare"}, "register" if tasks else None))
        return tasks
    return [notebook("emit", "demo_smoke_test", {**common, "mode": "emit"}),
            notebook("bronze", "tiger_to_bronze", {"tiger_host": "hi70ycj0r6.b4t1dqdug8.tsdb.cloud.timescale.com",
                "tiger_port": "31994", "lookback_minutes": "60"}, "emit"),
            notebook("refresh", "demo_smoke_test", {**common, "mode": "refresh"}, "bronze")]


def settle(state, deadline):
    pending = state.get("pending")
    if not pending:
        return
    run_id = pending["run_id"]
    while True:
        if time.time() >= deadline or (ROOT/"STOP").exists():
            api("jobs", "cancel-run", str(run_id))
            state["status"] = "stop_requested"
            save(state)
            raise SystemExit("Stopped; partial batch will be retried idempotently on an authorized resume")
        run = api("jobs", "get-run", str(run_id))
        lifecycle = run["state"]["life_cycle_state"]
        if lifecycle in {"TERMINATED", "SKIPPED", "INTERNAL_ERROR"}:
            if run["state"].get("result_state") != "SUCCESS":
                state["status"] = "needs_attention"
                state["error"] = run["state"]
                save(state)
                raise RuntimeError(f"Databricks run {run_id} did not succeed; cursor not advanced")
            wanted = "prepare" if pending["mode"] == "prepare" else "refresh"
            task = next(t for t in run["tasks"] if t["task_key"] == wanted)
            output = api("jobs", "get-run-output", str(task["run_id"]))
            data = json.loads(output["notebook_output"]["result"])
            (ROOT/"latest_dashboard.json").write_text(json.dumps(data, indent=2))
            if pending["mode"] == "prepare":
                state["ready"] = True
            else:
                state["cursor"] = pending["end"]
            state.update(participants=data["participants"], last_successful_run=run_id, status="ready")
            state.pop("pending", None)
            save(state)
            print(json.dumps({"run_id": run_id, "cursor": state["cursor"], "participants": state["participants"]}), flush=True)
            return
        time.sleep(15)


def submit(state, mode, end, deadline):
    tasks = tasks_for(state, mode, state["cursor"], end)
    run = api("jobs", "submit", "--json", json.dumps({"run_name": f"WolfHacks {SESSION}: {mode} through {end}",
              "timeout_seconds": min(1800, max(60, int(deadline-time.time()))), "tasks": tasks}), "--no-wait")
    state["pending"] = {"run_id": run["run_id"], "mode": mode, "end": end}
    state["status"] = "running"
    save(state)
    settle(state, deadline)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "advance", "judge", "status", "stop", "dry-run"])
    parser.add_argument("--fallback", action="store_true", help="Use the proven 17-person fixture when first preparing")
    parser.add_argument("--background", action="store_true", help="Detach the judging controller with a log and sleep prevention")
    parser.add_argument("--batch-minutes", type=int, default=15)
    args = parser.parse_args()
    ROOT.mkdir(parents=True, exist_ok=True)
    path = ROOT/"state.json"
    state = json.loads(path.read_text()) if path.exists() else {
        "session_id": SESSION, "fixture_id": "nine-day-v1" if args.fallback else "overnight-v1",
        "anchor": ANCHOR, "cursor": 11520, "ready": False, "status": "not_started"}
    if state["session_id"] != SESSION or state["anchor"] != ANCHOR:
        raise ValueError("Stored timeline differs; do not reset it")
    if args.fallback and state["fixture_id"] != "nine-day-v1":
        raise ValueError("Cannot switch an established session to a different roster")
    if args.action == "status":
        print(json.dumps(state, indent=2)); return
    if args.action == "dry-run":
        print(json.dumps(tasks_for(state, "advance", state["cursor"], state["cursor"] + 15), indent=2)); return
    if args.action == "stop":
        (ROOT/"STOP").touch()
        if state.get("pending"):
            api("jobs", "cancel-run", str(state["pending"]["run_id"]))
        print("Stopped new replay batches; dashboard history is preserved"); return
    if args.background:
        if args.action != "judge" or not START_AT <= time.time() < STOP_AT:
            raise ValueError("Background judging can only start noon–3 p.m. Eastern on Oct 4")
        with (ROOT/"controller.log").open("a") as log:
            process = subprocess.Popen([sys.executable, "-u", str(Path(__file__).resolve()), "judge",
                "--batch-minutes", str(args.batch_minutes)], stdout=log, stderr=log, start_new_session=True)
            subprocess.Popen(["/usr/bin/caffeinate", "-i", "-s", "-w", str(process.pid)], stdout=log, stderr=log, start_new_session=True)
        print(json.dumps({"controller_pid": process.pid, "stop_at": "2026-10-04T15:00:00-04:00"})); return
    lock = (ROOT/"controller.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if time.time() < PREP_AT:
        raise ValueError("No Databricks compute before 8 a.m. Eastern")
    if args.action == "judge" and not START_AT <= time.time() < STOP_AT:
        raise ValueError("Judging window is noon–3 p.m. Eastern on Oct 4")
    if not 1 <= args.batch_minutes <= 60:
        raise ValueError("batch-minutes must be 1–60")
    if (ROOT/"STOP").exists():
        raise ValueError("STOP marker is present; request an explicit resume before clearing it")
    save(state)
    deadline = STOP_AT if args.action == "judge" else min(STOP_AT, time.time()+2400)
    if state.get("pending"):
        settle(state, deadline)
    if args.action == "prepare":
        if not state["ready"]:
            submit(state, "prepare", 11580, deadline)
        print(json.dumps(state, indent=2)); return
    if not state["ready"]:
        raise ValueError("Run prepare and verify it before replay")
    fixed_target = min(12960, 11520 + int((time.time()-datetime.fromisoformat(ANCHOR).timestamp()) // 60))
    while time.time() < deadline and not (ROOT/"STOP").exists():
        target = (min(12960, 11520 + int((time.time()-datetime.fromisoformat(ANCHOR).timestamp()) // 60))
                  if args.action == "judge" else fixed_target)
        backlog = target - state["cursor"]
        if backlog > 0 and (args.action == "advance" or backlog >= args.batch_minutes):
            submit(state, "advance", state["cursor"] + min(60, backlog), deadline)
        elif args.action == "advance" or state["cursor"] >= 12960:
            break
        else:
            time.sleep(10)
    state["status"] = "stopped" if args.action == "judge" else "ready"
    save(state)
    print(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
