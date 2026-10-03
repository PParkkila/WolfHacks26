"""Download BIG IDEAs subjects and IMU50 00 onto a local computer.

Run from the repository root after installing remotezip==0.12.6.
The output folders can be uploaded directly into a Unity Catalog Volume.
"""

import argparse
import os
import shutil
import time
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen
from zipfile import ZipFile

BIG_CURRENT_URL = "https://physionet.org/files/big-ideas-glycemic-wearable/1.1.3"
BIG_S3_URL = (
    "https://physionet-open.s3.amazonaws.com/"
    "big-ideas-glycemic-wearable/1.1.2"
)
# The published 1.1.2 and 1.1.3 SHA-256 lists differ only for these food logs.
BIG_UPDATED_FOOD_LOGS = frozenset(("007", "013", "015", "016"))
IMU_URL = "https://zenodo.org/records/21468410/files/IMU50.zip?download=1"
BIG_SMALL = ("Dexcom", "Food_Log", "HR", "IBI", "TEMP", "EDA")
BIG_LARGE = ("ACC", "BVP")
IMU_MEMBER = "IMU50/DATA/00.zip"
IMU_METADATA = "IMU50/DATA/subjects_info.csv"


def copy_with_progress(source, destination, total_bytes: int, initial_bytes: int = 0):
    session_bytes = 0
    started = time.monotonic()
    last_update = started
    while True:
        chunk = source.read(4 * 1024 * 1024)
        if not chunk:
            break
        destination.write(chunk)
        session_bytes += len(chunk)
        now = time.monotonic()
        if now - last_update < 2 and initial_bytes + session_bytes < total_bytes:
            continue
        elapsed = max(now - started, 0.001)
        rate = session_bytes / elapsed
        done = initial_bytes + session_bytes
        if total_bytes:
            percent = min(100 * done / total_bytes, 100)
            eta = (total_bytes - done) / rate / 60 if rate else 0
            progress = f"{percent:5.1f}% {done / 1e6:,.0f}/{total_bytes / 1e6:,.0f} MB"
            progress += f" ETA {eta:,.1f} min"
        else:
            progress = f"{done / 1e6:,.0f} MB"
        print(f"\r  {progress}  {rate / 1e6:,.1f} MB/s", end="", flush=True)
        last_update = now
    print()


def download_http(url: str, destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        print(f"Skipping existing {destination}")
        return

    partial = destination.with_name(destination.name + ".part")
    resume_at = partial.stat().st_size if partial.exists() else 0
    headers = {"User-Agent": "WolfHacks26-pilot-download/1.0"}
    if resume_at:
        headers["Range"] = f"bytes={resume_at}-"

    print(f"Downloading {destination.name}")
    with urlopen(Request(url, headers=headers), timeout=600) as response:
        content_range = response.headers.get("Content-Range", "")
        if resume_at and response.status == 206:
            expected_prefix = f"bytes {resume_at}-"
            if not content_range.startswith(expected_prefix):
                raise IOError(f"Unexpected resume range: {content_range}")
            total_bytes = int(content_range.rsplit("/", 1)[1])
            mode = "ab"
            print(f"  Resuming at {resume_at / 1e6:,.0f} MB")
        else:
            resume_at = 0
            total_bytes = int(response.headers.get("Content-Length") or 0)
            mode = "wb"

        with partial.open(mode) as output:
            copy_with_progress(response, output, total_bytes, resume_at)

    if total_bytes and partial.stat().st_size != total_bytes:
        raise IOError(f"Incomplete download; rerun to resume: {partial}")
    os.replace(partial, destination)


def download_big_ideas(output_root: Path, quick: bool, all_subjects: bool):
    root = output_root / "big_ideas"
    download_http(f"{BIG_S3_URL}/Demographics.csv", root / "Demographics.csv")
    kinds = BIG_SMALL if quick else BIG_SMALL + BIG_LARGE
    subjects = (f"{number:03d}" for number in range(1, 17)) if all_subjects else ("001",)
    for subject in subjects:
        for kind in kinds:
            filename = f"{kind}_{subject}.csv"
            if kind == "Food_Log" and subject in BIG_UPDATED_FOOD_LOGS:
                source = BIG_CURRENT_URL
            else:
                source = BIG_S3_URL
            download_http(f"{source}/{subject}/{filename}", root / subject / filename)
    if quick:
        print("BIG IDEAs: skipped ACC and BVP. Rerun without --quick to add them.")


def copy_remote_member(archive, name: str, destination: Path):
    info = archive.getinfo(name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size == info.file_size:
        print(f"Skipping existing {destination}")
        return

    partial = destination.with_name(destination.name + ".part")
    print(f"Downloading {name}")
    with archive.open(info) as source, partial.open("wb") as output:
        copy_with_progress(source, output, info.file_size)
    if partial.stat().st_size != info.file_size:
        raise IOError(f"Incomplete nested ZIP download: {partial}")
    os.replace(partial, destination)


def download_imu50(output_root: Path, zip_only: bool):
    try:
        from remotezip import RemoteZip
    except ImportError as exc:
        raise SystemExit(
            "Install the IMU50 dependency with: python -m pip install remotezip==0.12.6"
        ) from exc

    root = output_root / "imu50"
    subject_zip = root / "archives" / "00.zip"
    metadata = root / "subjects_info.csv"

    # Preserve a completed download made by an earlier version of this script.
    legacy_zip = output_root / ".downloads" / "00.zip"
    legacy_metadata = output_root / ".downloads" / "subjects_info.csv"
    for legacy, current in ((legacy_zip, subject_zip), (legacy_metadata, metadata)):
        if legacy.is_file() and not current.exists():
            current.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(legacy, current)

    # HTTP byte ranges read just the nested subject ZIP from the large archive.
    if not (metadata.exists() and subject_zip.exists()):
        with RemoteZip(IMU_URL, support_suffix_range=False) as outer:
            copy_remote_member(outer, IMU_METADATA, metadata)
            copy_remote_member(outer, IMU_MEMBER, subject_zip)

    root.mkdir(parents=True, exist_ok=True)
    if zip_only:
        print(f"Nested subject ZIP ready for upload: {subject_zip}")
        return

    with ZipFile(subject_zip) as inner:
        members = [
            info
            for info in inner.infolist()
            if not info.is_dir()
            and PurePosixPath(info.filename).parent == PurePosixPath("00")
            and PurePosixPath(info.filename).name.endswith(".csv")
        ]
        expected = {f"00_{kind}.csv" for kind in ("imu", "ppg", "temperature", "scoring")}
        found = {PurePosixPath(info.filename).name for info in members}
        if not expected.issubset(found):
            raise ValueError(f"Unexpected IMU50 files. Expected {expected}; found {found}")

        for info in members:
            filename = PurePosixPath(info.filename).name
            destination = root / "00" / filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and destination.stat().st_size == info.file_size:
                print(f"Skipping existing {destination}")
                continue
            partial = destination.with_name(destination.name + ".part")
            print(f"Extracting {filename}")
            with inner.open(info) as source, partial.open("wb") as output:
                copy_with_progress(source, output, info.file_size)
            if partial.stat().st_size != info.file_size:
                raise IOError(f"Incomplete extraction: {partial}")
            os.replace(partial, destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("pilot-data"),
        help="Local output directory (default: ./pilot-data)",
    )
    parser.add_argument("--dataset", choices=("both", "big", "imu"), default="both")
    parser.add_argument(
        "--all-big",
        action="store_true",
        help="Download all 16 BIG IDEAs subjects instead of just subject 001",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Skip BIG IDEAs ACC and BVP; add them later by rerunning without --quick",
    )
    parser.add_argument(
        "--imu-zip-only",
        action="store_true",
        help="Keep IMU50 subject compressed for upload and expand it in Databricks",
    )
    args = parser.parse_args()
    output_root = args.output_dir.expanduser().resolve()

    if args.dataset in ("both", "big"):
        download_big_ideas(output_root, args.quick, args.all_big)
    if args.dataset in ("both", "imu"):
        download_imu50(output_root, args.imu_zip_only)

    print(f"\nReady to upload from: {output_root}")
    print("Upload big_ideas/ and imu50/ to the matching folders in your Volume.")
    if args.imu_zip_only:
        print("Upload imu50/archives/00.zip to the same path in the Volume.")
    else:
        print("The imu50/archives/ directory holds the compressed subject ZIP.")


if __name__ == "__main__":
    main()
