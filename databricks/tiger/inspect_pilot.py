# Databricks notebook source
"""Inspect the first landed subject from each source without scanning whole files."""

# COMMAND ----------

import csv
from pathlib import Path


dbutils.widgets.text("volume_root", "/Volumes/<catalog>/wolfhacks_raw/source_files")
dbutils.widgets.text("big_subject_id", "001")
dbutils.widgets.text("imu_subject_id", "00")

volume_root = Path(dbutils.widgets.get("volume_root").strip())
big_subject_id = dbutils.widgets.get("big_subject_id").strip()
imu_subject_id = dbutils.widgets.get("imu_subject_id").strip()

if "<catalog>" in str(volume_root):
    raise ValueError("Replace <catalog> in volume_root with your writable catalog")
if not volume_root.is_dir():
    raise FileNotFoundError(f"Volume path is unavailable: {volume_root}")

csv.field_size_limit(10_000_000)

files = [
    volume_root / "big_ideas" / "Demographics.csv",
    *(volume_root / "big_ideas" / big_subject_id / f"{kind}_{big_subject_id}.csv"
      for kind in ("Dexcom", "Food_Log", "HR", "IBI", "TEMP", "EDA", "ACC", "BVP")),
    volume_root / "imu50" / "subjects_info.csv",
    *(volume_root / "imu50" / imu_subject_id / f"{imu_subject_id}_{kind}.csv"
      for kind in ("imu", "ppg", "temperature", "scoring")),
]


def inspect_csv(path: Path, sample_limit: int = 1_000) -> None:
    print(f"\n{path}")
    if not path.is_file():
        print("  MISSING (large files may have been intentionally skipped)")
        return

    print(f"  size: {path.stat().st_size / 1_000_000:,.1f} MB")
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as source:
        reader = csv.reader(source)
        header = next(reader, None)
        if header is None:
            print("  EMPTY FILE")
            return

        print(f"  columns: {header}")
        missing = [0] * len(header)
        sample_count = 0
        first_row = None
        last_row = None

        for row in reader:
            if sample_count == 0:
                first_row = row
            last_row = row
            sample_count += 1
            for index in range(len(header)):
                if index >= len(row) or not row[index].strip():
                    missing[index] += 1
            if sample_count >= sample_limit:
                break

    print(f"  sampled rows: {sample_count:,} (first rows only; not total count)")
    print(f"  first row: {first_row}")
    print(f"  last sampled row: {last_row}")
    if sample_count:
        print(
            "  blank cells in sample: "
            + ", ".join(
                f"{column}={count / sample_count:.1%}"
                for column, count in zip(header, missing)
            )
        )


for file_path in files:
    inspect_csv(file_path)

print("\nThis is a bounded format check, not a complete data-quality audit.")
