#!/usr/bin/env python3
"""Start/status/stop the single local preparation worker; never starts Databricks compute."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]/"local-data"/"overnight"
WORKER = Path(__file__).with_name("prepare_overnight.py").resolve()


def running(pid):
    result = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True)
    return result.returncode == 0 and str(WORKER) in result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "status", "stop"])
    parser.add_argument("--deadline", default="2026-10-04T08:00:00-04:00")
    args = parser.parse_args()
    ROOT.mkdir(parents=True, exist_ok=True)
    launch = ROOT/"launch.json"
    previous = json.loads(launch.read_text()) if launch.exists() else {}
    active = bool(previous.get("pid") and running(previous["pid"]))
    if args.action == "start":
        if active:
            raise SystemExit("Preparation worker is already running")
        deadline = datetime.fromisoformat(args.deadline)
        if deadline.tzinfo is None or deadline.timestamp() <= datetime.now().timestamp():
            raise SystemExit("Deadline must be a future, timezone-aware timestamp")
        (ROOT/"STOP").unlink(missing_ok=True)
        with (ROOT/"worker.log").open("a") as log:
            process = subprocess.Popen([sys.executable, "-u", str(WORKER), "--root", str(ROOT),
                "--deadline", args.deadline, "--upload"], stdout=log, stderr=log,
                start_new_session=True, cwd=WORKER.parents[2])
            subprocess.Popen(["/usr/bin/caffeinate", "-i", "-s", "-w", str(process.pid)],
                             stdout=log, stderr=log, start_new_session=True)
        launch.write_text(json.dumps({"pid": process.pid, "deadline": args.deadline}, indent=2))
        print(launch.read_text())
    elif args.action == "stop":
        (ROOT/"STOP").touch()
        if active:
            os.kill(previous["pid"], signal.SIGTERM)
        print("Stop requested; completed outputs are preserved")
    else:
        status = ROOT/"status.json"
        print(json.dumps({"process_running": active, "launch": previous,
                          "status": json.loads(status.read_text()) if status.exists() else None}, indent=2))


if __name__ == "__main__":
    main()
