# Databricks notebook source
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
    "/Volumes/main/wolfhacks_raw/source_files/big_ideas",
)

subject_id = dbutils.widgets.get("subject_id").strip()
volume_root = Path(dbutils.widgets.get("volume_root").strip())

if not re.fullmatch(r"0(?:0[1-9]|1[0-6])", subject_id):
    raise ValueError("subject_id must be 001 through 016")

files = [
    f"ACC_{subject_id}.csv",
    f"BVP_{subject_id}.csv",
    f"Dexcom_{subject_id}.csv",
    f"EDA_{subject_id}.csv",
    f"Food_Log_{subject_id}.csv",
    f"HR_{subject_id}.csv",
    f"IBI_{subject_id}.csv",
    f"TEMP_{subject_id}.csv",
]

base_url = "https://physionet.org/files/big-ideas-glycemic-wearable/1.1.3"


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


def download(url: str, destination: Path) -> None:
    # Unity Catalog owns the catalog/schema/volume directories. Use the
    # Databricks filesystem API to create only folders inside the Volume.
    dbutils.fs.mkdirs(str(destination.parent))
    request = Request(url, headers={"User-Agent": "WolfHacks26-databricks-ingest/1.0"})
    with urlopen(request, timeout=600) as response:
        expected_size = response.headers.get("Content-Length")
        total_bytes = int(expected_size) if expected_size else 0
        if destination.exists() and expected_size:
            if destination.stat().st_size == total_bytes:
                print(f"skip existing: {destination}")
                return
        temporary = destination.with_suffix(destination.suffix + ".part")
        with temporary.open("wb") as output:
            copy_with_progress(response, output, total_bytes, destination.name)
        if expected_size and temporary.stat().st_size != total_bytes:
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

print(f"BIG IDEAs subject {subject_id} is staged in {volume_root / subject_id}")
