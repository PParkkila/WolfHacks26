"""Bounded, read-only evidence for provisional sensor units (no model tuning).

Run from the repo root. Reads the first N acceleration rows, all IMU50
temperature rows, and the first N BIG IDEAs temperature rows. ZIPs stay zipped.
"""

import argparse
import csv
import io
import itertools
import json
import math
from pathlib import Path
from zipfile import ZipFile


def summary(values):
    values = sorted(values)
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        **{name: values[round((len(values) - 1) * p)]
           for name, p in (("min", 0), ("p01", .01), ("p50", .5),
                           ("p99", .99), ("max", 1))},
    }


def inspect(source, limit, acceleration=False, scale=1.0):
    reader = csv.reader(source)
    header = next(reader)
    values, gyro, timestamps = [], [], []
    invalid = 0
    for row in itertools.islice(reader, limit):
        try:
            nums = [float(value) for value in row[1:]]
            if not all(math.isfinite(value) for value in nums):
                raise ValueError("non-finite value")
            if acceleration:
                values.append(math.sqrt(sum(value ** 2 for value in nums[:3])) / scale)
                if len(nums) == 6:
                    gyro.append(max(abs(value) for value in nums[3:]))
            else:
                values.append(nums[0])
            timestamps.append(row[0])
        except (ValueError, IndexError):
            invalid += 1
    result = {
        "header": header, "invalid_rows": invalid,
        "first_time": timestamps[0] if timestamps else None,
        "last_time": timestamps[-1] if timestamps else None,
        "values": summary(values),
    }
    if gyro:
        result["gyro_max_abs_axis_raw"] = summary(gyro)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("pilot-data"))
    parser.add_argument("--sample-rows", type=int, default=250_000)
    args = parser.parse_args()
    if args.sample_rows < 1:
        parser.error("--sample-rows must be positive")
    result = {"scope": "first-subject bounded sample; not a population calibration"}
    for kind, acceleration, scale in (("ACC", True, 64.0), ("TEMP", False, 1.0)):
        with (args.root / "big_ideas" / "001" / f"{kind}_001.csv").open(
            encoding="utf-8-sig", newline=""
        ) as source:
            result[f"big_ideas_{kind}"] = inspect(
                source, args.sample_rows, acceleration, scale
            )
    with ZipFile(args.root / "imu50" / "archives" / "00.zip") as archive:
        for kind in ("imu", "temperature"):
            with archive.open(f"00/00_{kind}.csv") as source:
                result[f"imu50_{kind}"] = inspect(
                    io.TextIOWrapper(source, encoding="utf-8-sig", newline=""),
                    args.sample_rows if kind == "imu" else None,
                    acceleration=kind == "imu",
                )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
