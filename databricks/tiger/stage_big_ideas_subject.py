# Databricks notebook source
"""Download one BIG IDEAs subject directly into a Unity Catalog Volume."""

# COMMAND ----------

import os
import re
import shutil
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


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "WolfHacks26-databricks-ingest/1.0"})
    with urlopen(request, timeout=600) as response:
        expected_size = response.headers.get("Content-Length")
        if destination.exists() and expected_size:
            if destination.stat().st_size == int(expected_size):
                print(f"skip existing: {destination}")
                return
        temporary = destination.with_suffix(destination.suffix + ".part")
        with temporary.open("wb") as output:
            shutil.copyfileobj(response, output, length=16 * 1024 * 1024)
        if expected_size and temporary.stat().st_size != int(expected_size):
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
