# Databricks notebook source
"""Range-download one nested IMU50 subject ZIP and expand it into a Volume."""

# COMMAND ----------

# MAGIC %pip install remotezip==0.12.6

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import os
import re
import shutil
import time
from pathlib import Path
from zipfile import ZipFile

from remotezip import RemoteZip


dbutils.widgets.text("subject_id", "00")
dbutils.widgets.text(
    "volume_root",
    "/Volumes/main/wolfhacks_raw/source_files/imu50",
)

subject_id = dbutils.widgets.get("subject_id").strip()
volume_root = Path(dbutils.widgets.get("volume_root").strip())

if not re.fullmatch(r"(?:[0-4][0-9])", subject_id):
    raise ValueError("subject_id must be 00 through 49")

url = "https://zenodo.org/records/21468410/files/IMU50.zip?download=1"
stage_root = Path("/local_disk0/wolfhacks/imu50") / subject_id
member = f"IMU50/DATA/{subject_id}.zip"
metadata_member = "IMU50/DATA/subjects_info.csv"
inner_zip = stage_root / member
metadata_source = stage_root / metadata_member

stage_root.mkdir(parents=True, exist_ok=True)


def copy_with_progress(source, output, total_bytes: int, label: str) -> None:
    transferred = 0
    started = time.monotonic()
    last_update = started
    bar_width = 30
    while True:
        chunk = source.read(16 * 1024 * 1024)
        if not chunk:
            break
        output.write(chunk)
        transferred += len(chunk)
        now = time.monotonic()
        if now - last_update < 2 and transferred < total_bytes:
            continue
        elapsed = max(now - started, 0.001)
        rate = transferred / elapsed
        ratio = min(transferred / total_bytes, 1) if total_bytes else 0
        filled = int(ratio * bar_width)
        bar = "#" * filled + "-" * (bar_width - filled)
        eta = (total_bytes - transferred) / rate if total_bytes and rate else 0
        print(
            f"\r{label} [{bar}] {ratio:6.1%} "
            f"{transferred / 1_000_000:,.0f}/{total_bytes / 1_000_000:,.0f} MB "
            f"{rate / 1_000_000:,.1f} MB/s ETA {eta / 60:,.1f} min",
            end="",
            flush=True,
        )
        last_update = now
    print()


def copy_member_to_volume(archive: ZipFile, member_name: str, destination: Path) -> None:
    info = archive.getinfo(member_name)
    # Unity Catalog owns the catalog/schema/volume directories. Use the
    # Databricks filesystem API to create only folders inside the Volume.
    dbutils.fs.mkdirs(str(destination.parent))
    if destination.exists() and destination.stat().st_size == info.file_size:
        print(f"skip existing: {destination}")
        return
    temporary = destination.with_suffix(destination.suffix + ".part")
    with archive.open(info) as source, temporary.open("wb") as output:
        copy_with_progress(source, output, info.file_size, f"expand {destination.name}")
    if temporary.stat().st_size != info.file_size:
        raise IOError(f"incomplete expansion: {destination}")
    os.replace(temporary, destination)
    print(f"expanded: {destination}")


def copy_file_to_volume(source: Path, destination: Path) -> None:
    dbutils.fs.mkdirs(str(destination.parent))
    if destination.exists() and destination.stat().st_size == source.stat().st_size:
        print(f"skip existing: {destination}")
        return
    temporary = destination.with_suffix(destination.suffix + ".part")
    with source.open("rb") as input_file, temporary.open("wb") as output:
        copy_with_progress(
            input_file,
            output,
            source.stat().st_size,
            f"copy {destination.name}",
        )
    os.replace(temporary, destination)
    print(f"copied: {destination}")


# COMMAND ----------

try:
    # Zenodo supports HTTP byte ranges, so this retrieves only the requested
    # approximately 0.7-1.0 GB nested subject ZIP, not the 46.7 GB outer ZIP.
    with RemoteZip(url, support_suffix_range=False) as remote_archive:
        for remote_member, destination in (
            (metadata_member, metadata_source),
            (member, inner_zip),
        ):
            info = remote_archive.getinfo(remote_member)
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(destination.suffix + ".part")
            with remote_archive.open(info) as source, temporary.open("wb") as output:
                copy_with_progress(
                    source,
                    output,
                    info.file_size,
                    f"download {destination.name}",
                )
            if temporary.stat().st_size != info.file_size:
                raise IOError(f"incomplete download: {remote_member}")
            os.replace(temporary, destination)

    copy_file_to_volume(metadata_source, volume_root / "subjects_info.csv")

    with ZipFile(inner_zip) as subject_archive:
        expected_prefix = f"{subject_id}/"
        csv_members = [
            item.filename
            for item in subject_archive.infolist()
            if not item.is_dir()
            and item.filename.startswith(expected_prefix)
            and item.filename.lower().endswith(".csv")
        ]
        if not csv_members:
            raise ValueError(f"No CSV members found in {inner_zip}")
        for csv_member in csv_members:
            destination = volume_root / csv_member
            copy_member_to_volume(subject_archive, csv_member, destination)

    print(f"IMU50 subject {subject_id} is staged in {volume_root / subject_id}")
finally:
    shutil.rmtree(stage_root, ignore_errors=True)
