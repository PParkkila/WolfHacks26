# Databricks notebook source
"""Stage all 16 BIG IDEAs subjects directly from verified public S3 objects.

Only ACC/TEMP/HR/CGM needed for this modeling increment are fetched. Sources
are compared to the published v1.1.3 SHA256 manifest before using the faster
v1.1.2 public mirror. Existing raw files are never silently overwritten.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import time
from urllib.request import Request, urlopen

ROOT = Path("/Volumes/workspace/wolfhacks_raw/source_files/big_ideas")
S3 = "https://physionet-open.s3.amazonaws.com/big-ideas-glycemic-wearable/1.1.2"
CURRENT = "https://physionet.org/files/big-ideas-glycemic-wearable/1.1.3"


def manifest(base):
    with urlopen(f"{base}/SHA256SUMS.txt", timeout=60) as response:
        lines = response.read().decode().splitlines()
    return {name.strip().lstrip("*").removeprefix("./"): digest
            for digest, name in (line.split(maxsplit=1) for line in lines if line.strip())}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


current_hashes, mirror_hashes = manifest(CURRENT), manifest(S3)
paths = ["Demographics.csv"] + [
    f"{subject:03d}/{kind}_{subject:03d}.csv"
    for subject in range(1, 17) for kind in ("ACC", "TEMP", "HR", "Dexcom")
]
for name in paths:
    if current_hashes.get(name) is None or current_hashes[name] != mirror_hashes.get(name):
        raise ValueError(f"Mirror content is not verified against v1.1.3: {name}")
for subject in range(1, 17):
    dbutils.fs.mkdirs(str(ROOT / f"{subject:03d}"))


def download(name):
    target = ROOT / name
    if target.exists():
        if sha256(target) != current_hashes[name]:
            raise ValueError(f"Existing file fails checksum; preserved for inspection: {name}")
        return {"path": name, "status": "verified_existing", "bytes": target.stat().st_size}
    partial = target.with_name(target.name + ".model-download.part")
    offset = partial.stat().st_size if partial.exists() else 0
    headers = {"User-Agent": "WolfHacks26-model-cohort/1.0"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    started, last_report = time.monotonic(), time.monotonic()
    with urlopen(Request(f"{S3}/{name}", headers=headers), timeout=120) as response:
        if offset and response.status == 206:
            content_range = response.headers.get("Content-Range", "")
            if not content_range.startswith(f"bytes {offset}-"):
                raise ValueError(f"Unexpected range response for {name}")
            total, mode = int(content_range.rsplit("/", 1)[1]), "ab"
        else:
            offset, total, mode = 0, int(response.headers.get("Content-Length", 0)), "wb"
        done = offset
        with partial.open(mode) as destination:
            while block := response.read(8 * 1024 * 1024):
                destination.write(block)
                done += len(block)
                now = time.monotonic()
                if now - last_report > 30:
                    print(f"{name}: {done / 1e6:.0f}/{total / 1e6:.0f} MB", flush=True)
                    last_report = now
    if total and partial.stat().st_size != total:
        raise ValueError(f"Incomplete file; rerun to resume: {name}")
    if sha256(partial) != current_hashes[name]:
        raise ValueError(f"Checksum mismatch; partial retained: {name}")
    os.replace(partial, target)
    return {"path": name, "status": "downloaded", "bytes": done,
            "seconds": round(time.monotonic() - started, 1)}


results = []
with ThreadPoolExecutor(max_workers=4) as pool:
    futures = [pool.submit(download, name) for name in paths]
    for future in as_completed(futures):
        record = future.result()
        results.append(record)
        print(json.dumps(record), flush=True)
dbutils.notebook.exit(json.dumps({"verified_files": len(results),
                                  "total_bytes": sum(r["bytes"] for r in results)}))
