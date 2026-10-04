#!/usr/bin/env python3
"""Submit a finite recording phase. Uses existing CLI authentication, never DB secrets."""

import argparse
import json
from pathlib import Path
import re
import subprocess


def build_run(session: str, phase: str) -> dict:
    if not re.fullmatch(r"[a-z0-9-]{1,50}", session):
        raise ValueError("Session must use 1–50 lowercase letters, digits, or hyphens")
    run = json.loads(Path(__file__).with_name("demo_smoke_test.run.json").read_text())
    phases = {
        "prepare": {"prepare_history"},
        "hour1": {"emit_hour_one", "bronze_hour_one", "dashboard_hour_one"},
        "hour2": {"emit_hour_two", "bronze_hour_two", "dashboard_hour_two"},
    }
    if phase != "all":
        run["tasks"] = [task for task in run["tasks"] if task["task_key"] in phases[phase]]
    selected = {task["task_key"] for task in run["tasks"]}
    for task in run["tasks"]:
        dependencies = [d for d in task.get("depends_on", []) if d["task_key"] in selected]
        if dependencies:
            task["depends_on"] = dependencies
        else:
            task.pop("depends_on", None)
        if task["notebook_task"]["notebook_path"].endswith("/demo_smoke_test"):
            task["notebook_task"]["base_parameters"]["session_id"] = session
    run["run_name"] = f"WolfHacks demo {session}: {phase}"
    return run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True, help="Use one new ID for all phases of a recording")
    parser.add_argument("--phase", choices=["prepare", "hour1", "hour2", "all"], default="all")
    parser.add_argument("--profile", default="wolfhacks")
    parser.add_argument("--dry-run", action="store_true", help="Print configuration without submitting")
    args = parser.parse_args()
    run = build_run(args.session, args.phase)
    if args.dry_run:
        print(json.dumps(run, indent=2))
        return
    print("Finite simulated replay; wait for each phase to succeed before starting the next.", flush=True)
    subprocess.run(["databricks", "jobs", "submit", "--profile", args.profile,
                    "--json", json.dumps(run), "--no-wait", "--output", "json"], check=True)


if __name__ == "__main__":
    main()
