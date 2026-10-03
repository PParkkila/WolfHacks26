# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
"""Download one BIG IDEAs subject directly into a Unity Catalog Volume."""

# COMMAND ----------

import os
import re
import time
from pathlib import Path
from urllib.request import Request, urlopen


dbutils.widgets.text("subject_id", "001")
dbutils.widgets.text(
    "volume_root",
    "/Volumes/workspace/wolfhacks_raw/source_files/big_ideas",
)
dbutils.widgets.dropdown("include_large_files", "false", ["false", "true"])

subject_id = dbutils.widgets.get("subject_id").strip()
volume_root = Path(dbutils.widgets.get("volume_root").strip())
include_large_files = dbutils.widgets.get("include_large_files") == "true"

if not re.fullmatch(r"0(?:0[1-9]|1[0-6])", subject_id):
    raise ValueError("subject_id must be 001 through 016")

small_files = [
    f"Dexcom_{subject_id}.csv",
    f"Food_Log_{subject_id}.csv",
    f"HR_{subject_id}.csv",
    f"IBI_{subject_id}.csv",
    f"TEMP_{subject_id}.csv",
    f"EDA_{subject_id}.csv",
]
large_files = [f"ACC_{subject_id}.csv", f"BVP_{subject_id}.csv"]
files = small_files + (large_files if include_large_files else [])

base_url = "https://physionet.org/files/big-ideas-glycemic-wearable/1.1.3"


def copy_with_progress(
    source,
    output,
    total_bytes: int,
    label: str,
    initial_bytes: int = 0,
) -> None:
    transferred = initial_bytes
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


def download(url: str, destination: Path) -> None:
    # Unity Catalog owns the catalog/schema/volume directories. Use the
    # Databricks filesystem API to create only folders inside the Volume.
    dbutils.fs.mkdirs(str(destination.parent))
    temporary = destination.with_suffix(destination.suffix + ".part")
    resume_from = temporary.stat().st_size if temporary.exists() else 0
    headers = {"User-Agent": "WolfHacks26-databricks-ingest/1.0"}
    if resume_from:
        headers["Range"] = f"bytes={resume_from}-"
    request = Request(url, headers=headers)
    with urlopen(request, timeout=600) as response:
        content_range = response.headers.get("Content-Range")
        partial_response = response.status == 206 and content_range is not None
        if partial_response:
            total_bytes = int(content_range.rsplit("/", 1)[1])
            write_mode = "ab"
        else:
            total_bytes = int(response.headers.get("Content-Length") or 0)
            resume_from = 0
            write_mode = "wb"
        if destination.exists() and total_bytes:
            if destination.stat().st_size == total_bytes:
                print(f"skip existing: {destination}")
                return
        if partial_response:
            print(f"resuming {destination.name} at {resume_from / 1_000_000:,.0f} MB")
        with temporary.open(write_mode) as output:
            copy_with_progress(
                response,
                output,
                total_bytes,
                destination.name,
                initial_bytes=resume_from,
            )
        if total_bytes and temporary.stat().st_size != total_bytes:
            raise IOError(f"incomplete download: {destination}")
        os.replace(temporary, destination)
        print(f"downloaded: {destination}")


# COMMAND ----------

download(f"{base_url}/Demographics.csv", volume_root / "Demographics.csv")

for filename in files:
    download(
        f"{base_url}/{subject_id}/{filename}",
        volume_root / subject_id / filename,
    )

<<<<<<< Updated upstream
if not include_large_files:
    print("Skipped ACC and BVP for this pilot. Set include_large_files=true to add them.")

print(f"BIG IDEAs subject {subject_id} is staged in {volume_root / subject_id}")
=======
print(f"BIG IDEAs subject {subject_id} is staged in {volume_root / subject_id}")
>>>>>>> Stashed changes