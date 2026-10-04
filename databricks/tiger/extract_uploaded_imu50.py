# Databricks notebook source
"""Expand an uploaded IMU50 subject ZIP into a Unity Catalog Volume."""

# COMMAND ----------

import os
import re
import time
from pathlib import Path, PurePosixPath
from zipfile import ZipFile


dbutils.widgets.text("subject_id", "00")
dbutils.widgets.text(
    "volume_root", "/Volumes/<catalog>/wolfhacks_raw/source_files/imu50"
)
dbutils.widgets.text("uploaded_zip_path", "")

subject_id = dbutils.widgets.get("subject_id").strip()
volume_root = Path(dbutils.widgets.get("volume_root").strip())
uploaded_zip_path = dbutils.widgets.get("uploaded_zip_path").strip()

if not re.fullmatch(r"[0-4][0-9]", subject_id):
    raise ValueError("subject_id must be 00 through 49")
if "<catalog>" in str(volume_root):
    raise ValueError("Replace <catalog> in volume_root with your writable catalog")

source_zip = (
    Path(uploaded_zip_path)
    if uploaded_zip_path
    else volume_root / "archives" / f"{subject_id}.zip"
)
if not source_zip.is_file():
    raise FileNotFoundError(f"Upload the nested subject ZIP first: {source_zip}")


def expand_member(archive: ZipFile, info, destination: Path) -> None:
    dbutils.fs.mkdirs(str(destination.parent))
    if destination.exists() and destination.stat().st_size == info.file_size:
        print(f"Skipping existing {destination}")
        return

    partial = destination.with_name(destination.name + ".part")
    transferred = 0
    started = time.monotonic()
    last_update = started
    print(f"Expanding {destination.name}")
    with archive.open(info) as source, partial.open("wb") as output:
        while chunk := source.read(4 * 1024 * 1024):
            output.write(chunk)
            transferred += len(chunk)
            now = time.monotonic()
            if now - last_update >= 2 or transferred == info.file_size:
                elapsed = max(now - started, 0.001)
                rate = transferred / elapsed
                percent = 100 * transferred / info.file_size if info.file_size else 100
                print(
                    f"\r  {percent:5.1f}% "
                    f"{transferred / 1e6:,.0f}/{info.file_size / 1e6:,.0f} MB "
                    f"{rate / 1e6:,.1f} MB/s",
                    end="",
                    flush=True,
                )
                last_update = now
    print()
    if partial.stat().st_size != info.file_size:
        raise IOError(f"Incomplete expansion: {partial}")
    os.replace(partial, destination)


with ZipFile(source_zip) as archive:
    expected_names = {
        f"{subject_id}_{kind}.csv"
        for kind in ("imu", "ppg", "temperature", "scoring")
    }
    members = [
        info
        for info in archive.infolist()
        if not info.is_dir()
        and PurePosixPath(info.filename).parent == PurePosixPath(subject_id)
        and PurePosixPath(info.filename).name in expected_names
    ]
    found_names = {PurePosixPath(info.filename).name for info in members}
    if found_names != expected_names:
        raise ValueError(f"Expected {expected_names}; found {found_names}")

    for info in members:
        destination = volume_root / subject_id / PurePosixPath(info.filename).name
        expand_member(archive, info, destination)

print(f"IMU50 subject {subject_id} is ready at {volume_root / subject_id}")
if not (volume_root / "subjects_info.csv").is_file():
    print(f"Upload subjects_info.csv to {volume_root} for the metadata audit.")
