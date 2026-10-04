#!/usr/bin/env python3
"""Low-disk local IMU50 preparation. Storage uploads only; never starts compute.

Own scratch ZIPs are removed after compact outputs are committed (or on failure).
Existing pilot-data archives are read-only and never removed. SIGALRM enforces
the absolute cutoff even during parsing/network retries; partial results are
never marked ready. One worker and 250k-row CSV chunks bound RAM/disk use.
"""
import argparse
from datetime import datetime, timezone, timedelta
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
from zipfile import ZipFile

import joblib
import numpy as np
import pandas as pd
from remotezip import RemoteZip

from rolling_risk import score_records, window_features

URL = "https://zenodo.org/records/21468410/files/IMU50.zip?download=1"
FIXTURE = "overnight-v1"
MODEL = "0006be934ae7480d922f248ddd25a17d"
DEST = "dbfs:/Volumes/workspace/wolfhacks_raw/source_files/prepared_replay/overnight-v1/imu50"


class Deadline(Exception):
    pass


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False))
    os.replace(temporary, path)


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(4 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def minute_values(series):
    dates = pd.to_datetime(series, format="ISO8601", errors="raise")
    return dates.astype("datetime64[ns]").astype("int64").to_numpy() // 60_000_000_000


def aggregate_archive(path, subject, check):
    count, invalid, parts, carry, previous_last = 0, 0, [], None, None
    started, last_report = time.monotonic(), time.monotonic()
    with ZipFile(path) as archive:
        needed = {f"{subject}/{subject}_{kind}.csv" for kind in ("imu", "temperature", "ppg", "scoring")}
        if not needed.issubset(archive.namelist()):
            raise ValueError("Unexpected subject archive contents")
        with archive.open(f"{subject}/{subject}_imu.csv") as stream:
            reader = pd.read_csv(stream, usecols=["Timestamp", "Accelerometer X", "Accelerometer Y", "Accelerometer Z"], chunksize=250000)
            for chunk in reader:
                check()
                count += len(chunk)
                ticks = minute_values(chunk.Timestamp)
                if (np.diff(ticks) < 0).any() or (previous_last is not None and ticks[0] < previous_last):
                    raise ValueError("IMU timestamps not ordered; refusing incorrect chunk aggregation")
                previous_last = ticks[-1]
                axes = chunk[["Accelerometer X", "Accelerometer Y", "Accelerometer Z"]].to_numpy(float)
                finite = np.isfinite(axes).all(axis=1)
                invalid += int((~finite).sum())
                values = np.maximum(np.sqrt(np.square(axes).sum(axis=1)) - 1, 0)
                values[~finite] = np.nan
                frame = pd.DataFrame({"minute_index": ticks, "enmo": values})
                if carry is not None:
                    frame = pd.concat([carry, frame], ignore_index=True)
                carry = frame[frame.minute_index == ticks[-1]]
                if len(carry) > 20000:
                    raise ValueError("Abnormally large repeated minute; inspect source")
                completed = frame[frame.minute_index != ticks[-1]]
                if len(completed):
                    group = completed.groupby("minute_index").enmo
                    agg = group.agg(acc_rows="size", acc_samples="count", enmo_mean_g="mean", enmo_std_g="std")
                    agg["enmo_p95_g"] = group.quantile(.95)
                    parts.append(agg)
                if time.monotonic() - last_report > 30:
                    print(json.dumps({"subject": subject, "stage": "aggregate", "raw_rows": count,
                                      "rows_per_second": int(count / (time.monotonic() - started))}), flush=True)
                    last_report = time.monotonic()
            if carry is not None:
                group = carry.groupby("minute_index").enmo
                agg = group.agg(acc_rows="size", acc_samples="count", enmo_mean_g="mean", enmo_std_g="std")
                agg["enmo_p95_g"] = group.quantile(.95)
                parts.append(agg)
        with archive.open(f"{subject}/{subject}_temperature.csv") as stream:
            temp = pd.read_csv(stream)
        temp["minute_index"] = minute_values(temp.Timestamp)
        temp["Temperature"] = pd.to_numeric(temp.Temperature, errors="raise")
        if not np.isfinite(temp.Temperature.to_numpy()).all():
            raise ValueError("Invalid temperature values")
        temperatures = temp.groupby("minute_index").Temperature.agg(temperature_samples="count", temperature_mean_c="mean")
    result = pd.concat(parts).join(temperatures, how="outer").reset_index()
    if result.minute_index.duplicated().any() or int(result.acc_rows.sum()) != count:
        raise ValueError("Minute aggregation row-count mismatch")
    result["acc_sample_ratio"] = result.acc_samples.fillna(0) / 7680
    result["temperature_sample_ratio"] = result.temperature_samples.fillna(0)
    result["participant_key"] = f"imu50:{subject}"
    result["source_dataset"] = "imu50"
    result["unit_status"] = "inferred_g_celsius"
    result["source_clock"] = pd.to_datetime(result.minute_index * 60, unit="s").dt.strftime("%Y-%m-%d %H:%M:%S")
    return result, {"acc_rows_read": count, "acc_invalid_rows": invalid,
                    "temperature_rows_read": len(temp), "observed_minutes": len(result)}


def prepare_fixture(minutes, subject):
    valid = minutes[minutes.acc_sample_ratio.between(.8, 1) & minutes.temperature_sample_ratio.between(.8, 1)].copy()
    if len(valid) < 1440:
        raise ValueError("Less than a day of usable real tuples; skip instead of inventing a persona")
    valid["day"] = valid.minute_index // 1440
    valid["clock_minute"] = valid.minute_index % 1440
    valid["day_minutes"] = valid.groupby("day").minute_index.transform("count")
    ranked = valid.sort_values(["day_minutes", "minute_index"], ascending=[False, True])
    template = ranked.drop_duplicates("clock_minute").set_index("clock_minute").reindex(range(1440)).ffill().bfill()
    original = valid.set_index("minute_index")
    start, last = int(valid.minute_index.min()), int(valid.minute_index.max())
    columns = ["enmo_mean_g", "enmo_std_g", "enmo_p95_g", "temperature_mean_c"]
    records = []
    for offset in range(12960):
        intended = start + offset
        real = intended in original.index
        donor = original.loc[intended] if real else template.loc[intended % 1440]
        donor_index = intended if real else int(donor.minute_index)
        records.append({"fixture_id": FIXTURE, "demo_participant_key": f"demo:imu50:{subject}",
            "source_participant_key": f"imu50:{subject}", "source_dataset": "imu50", "subject_id": subject,
            "unit_status": "inferred_g_celsius", "minute_offset": offset, "clock_minute": intended % 1440,
            "intended_source_clock": datetime.fromtimestamp(intended * 60, timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "donor_source_clock": datetime.fromtimestamp(donor_index * 60, timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            **{c: float(donor[c]) for c in columns}, "hr_mean_bpm": None, "is_synthetic": not real,
            "provenance": "observed_replay" if real else ("synthetic_extension" if intended > last else "synthetic_gap_fill"),
            "phase": "warmup" if offset < 1440 else ("history" if offset < 11520 else "replay"),
            "demo_only": True, "training_eligible": False, "generation_policy": "same-person-clock-template-v1"})
    bank = pd.DataFrame(records)
    bank["minute_offset"] = bank.minute_offset.astype("int32")
    bank["clock_minute"] = bank.clock_minute.astype("int32")
    bank["hr_mean_bpm"] = bank.hr_mean_bpm.astype("float64")
    return bank


def history_metrics(bank, bundle):
    records = []
    t = bank.minute_offset.to_numpy()
    a, c = bank.enmo_mean_g.to_numpy(), bank.temperature_mean_c.to_numpy()
    identity = bank.iloc[0]
    for end in range(1500, 11521, 60):
        frame = bank.iloc[end-1440:end]
        f = window_features(t, a, c, end)
        records.append({"fixture_id": FIXTURE, "demo_participant_key": identity.demo_participant_key,
            "participant_key": identity.demo_participant_key, "source_participant_key": identity.source_participant_key,
            "source_dataset": "imu50", "window_start_offset_minutes": end-1440,
            "window_end_offset_minutes": end, "clock_minute": int(frame.iloc[-1].clock_minute),
            "unit_status": "inferred_g_celsius", "window_minutes": 1440,
            "motion_mean_g": f["motion_mean_g"], "motion_std_g": f["motion_std_g"], "motion_p90_g": f["motion_p90_g"],
            "temperature_mean_c_24h": f["temperature_mean_c"], "temperature_std_c_24h": f["temperature_std_c"],
            "hr_mean_bpm_24h": None, "hr_coverage_fraction": 0.0, "motion_hr_correlation": None,
            "synthetic_minutes": int(frame.is_synthetic.sum()), "synthetic_fraction": float(frame.is_synthetic.mean()),
            "wearable_risk_indicator": None, "risk_status": "pending_24h_model",
            "demo_only": True, "training_eligible": False})
    return score_records(records, bank.iloc[:11520], bundle)


def upload(directory, subject, cli, profile):
    target = f"{DEST}/{subject}"
    subprocess.run([cli, "fs", "mkdir", target, "--profile", profile], check=True, timeout=60)
    # A manifest is the commit marker: upload it only after all referenced files.
    for name in ("real_minutes.parquet", "minute_bank.parquet", "history_metrics.json", "manifest.json"):
        subprocess.run([cli, "fs", "cp", str(directory/name), f"{target}/{name}", "--overwrite", "--profile", profile], check=True, timeout=180)
    check = subprocess.run([cli, "fs", "cat", f"{target}/manifest.json", "--profile", profile], check=True,
                           capture_output=True, text=True, timeout=60)
    if json.loads(check.stdout) != json.loads((directory/"manifest.json").read_text()):
        raise ValueError("Uploaded manifest verification failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("databricks/local-data/overnight"))
    parser.add_argument("--deadline", default="2026-10-04T08:00:00-04:00")
    parser.add_argument("--subjects", nargs="+", help="Default: remaining 01–49, smallest first")
    parser.add_argument("--existing-zip", type=Path, help="Read-only existing ZIP; requires one --subjects ID")
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--cli", default="databricks")
    parser.add_argument("--profile", default="wolfhacks")
    args = parser.parse_args()
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    lock = (root/"worker.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    deadline = datetime.fromisoformat(args.deadline)
    remaining = deadline.timestamp() - time.time()
    if remaining <= 0 or deadline.tzinfo is None:
        raise ValueError("Deadline must be an aware future timestamp")
    def stop(*_): raise Deadline("8 a.m. preparation cutoff reached")
    signal.signal(signal.SIGALRM, stop)
    signal.signal(signal.SIGTERM, stop)
    signal.setitimer(signal.ITIMER_REAL, remaining)
    scratch = root/"scratch"
    scratch.mkdir(exist_ok=True)
    def check():
        if time.time() >= deadline.timestamp() or (root/"STOP").exists():
            raise Deadline("Deadline or STOP file reached")
        if shutil.disk_usage(root).free < 5 * 1024**3:
            raise Deadline("Less than 5 GiB free; preserving disk")
        if sum(f.stat().st_size for f in root.rglob("*") if f.is_file()) > 9 * 1024**3:
            raise Deadline("Local task storage budget reached")
    state = {"pid": os.getpid(), "deadline": args.deadline, "stage": "starting", "completed": [], "failed": {}}
    status = root/"status.json"
    atomic_json(status, state)
    bundle = joblib.load(root/"model"/"rolling_risk.joblib")
    if bundle["model_version"] != MODEL:
        raise ValueError("Unexpected model artifact")
    subjects = args.subjects or [f"{i:02d}" for i in range(1, 50)]
    if not all(len(s) == 2 and s.isdigit() and 0 <= int(s) < 50 for s in subjects):
        raise ValueError("Invalid participant IDs")
    if args.existing_zip and len(subjects) != 1:
        raise ValueError("Existing ZIP requires exactly one subject")
    try:
        if not args.subjects:
            with RemoteZip(URL, support_suffix_range=False, timeout=45) as archive:
                subjects.sort(key=lambda s: archive.getinfo(f"IMU50/DATA/{s}.zip").file_size)
        for subject in subjects:
            check()
            directory = root/"prepared"/subject
            directory.mkdir(parents=True, exist_ok=True)
            marker = directory/"manifest.json"
            state.update(subject=subject, stage="preparing", updated_at=datetime.now(timezone.utc).isoformat())
            atomic_json(status, state)
            owned_zip = scratch/f"{subject}.zip"
            partial = scratch/f"{subject}.zip.part"
            try:
                if not marker.exists():
                    path = args.existing_zip.resolve() if args.existing_zip else owned_zip
                    if not args.existing_zip:
                        last_error = None
                        for attempt in range(3):
                            try:
                                state["stage"] = "downloading"
                                atomic_json(status, state)
                                with RemoteZip(URL, support_suffix_range=False, timeout=60) as archive:
                                    info = archive.getinfo(f"IMU50/DATA/{subject}.zip")
                                    if info.file_size > 2 * 1024**3:
                                        raise ValueError("Subject ZIP exceeds 2 GiB task limit")
                                    done, last_report = 0, time.monotonic()
                                    with archive.open(info) as source, partial.open("wb") as output:
                                        while block := source.read(4 * 1024 * 1024):
                                            check()
                                            output.write(block)
                                            done += len(block)
                                            if time.monotonic()-last_report > 30:
                                                state.update(downloaded_bytes=done, download_total_bytes=info.file_size)
                                                atomic_json(status, state)
                                                print(json.dumps(state), flush=True)
                                                last_report = time.monotonic()
                                    if done != info.file_size:
                                        raise IOError("Incomplete nested ZIP")
                                os.replace(partial, owned_zip)
                                last_error = None
                                break
                            except Deadline:
                                raise
                            except Exception as exc:
                                last_error = exc
                                print(f"Download {subject} attempt {attempt+1}: {exc}", flush=True)
                                time.sleep(min(30, 5 * (attempt + 1)))
                        if last_error:
                            raise last_error
                    state["stage"] = "aggregating"
                    atomic_json(status, state)
                    real, audit = aggregate_archive(path, subject, check)
                    real.to_parquet(directory/"real_minutes.parquet", index=False)
                    bank = prepare_fixture(real, subject)
                    bank.to_parquet(directory/"minute_bank.parquet", index=False)
                    scores = history_metrics(bank, bundle)
                    atomic_json(directory/"history_metrics.json", scores)
                    files = {name: {"bytes": (directory/name).stat().st_size, "sha256": sha(directory/name)}
                             for name in ("real_minutes.parquet", "minute_bank.parquet", "history_metrics.json")}
                    atomic_json(marker, {"subject_id": subject, "participant_key": f"imu50:{subject}",
                        "fixture_id": FIXTURE, "source_url": URL, "source_member": f"IMU50/DATA/{subject}.zip",
                        "processing_location": "local_mac", "model_version": MODEL, **audit,
                        "fixture_minutes": len(bank), "synthetic_minutes": int(bank.is_synthetic.sum()),
                        "history_windows": len(scores), "files": files})
                if args.upload:
                    state["stage"] = "uploading"
                    atomic_json(status, state)
                    upload(directory, subject, args.cli, args.profile)
                state["completed"].append(subject)
                state["stage"] = "participant_ready"
                atomic_json(status, state)
                print(json.dumps({"subject": subject, "ready": True, "uploaded": args.upload,
                                  "completed": len(state["completed"])}), flush=True)
            except Deadline:
                raise
            except Exception as exc:
                state["failed"][subject] = str(exc)
                atomic_json(status, state)
                print(json.dumps({"subject": subject, "error": str(exc)}), flush=True)
            finally:
                # Only exact worker-created scratch files; original archives remain untouched.
                for temporary in (owned_zip, partial):
                    if temporary.parent == scratch and temporary.is_file():
                        temporary.unlink()
        state["stage"] = "finished"
    except Deadline as exc:
        state.update(stage="stopped", stop_reason=str(exc))
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        atomic_json(status, state)
        print(json.dumps(state), flush=True)


if __name__ == "__main__":
    main()
