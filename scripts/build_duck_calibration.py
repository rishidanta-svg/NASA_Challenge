"""Export the Duck foreshore slopes from the archived independent calibration scans."""

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import xarray as xr


def utc(value):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc).isoformat()


def build(source):
    with (source / "lidar_calibration_meta.csv").open() as stream:
        metadata = {row["date_key"]: row for row in csv.DictReader(stream)}
    with xr.open_dataset(source / "lidar_calibration.nc") as surveys:
        result = {}
        for date in surveys.date.values.tolist():
            record = metadata[date]
            if float(record["coregQCFlag"]) != 1:
                raise ValueError(f"Unqualified calibration survey for {date}")
            survey = surveys.elevation.sel(date=date)
            slopes = []
            for y in range(700, 1191, 10):
                profile = survey.sel(yFRF=slice(y - 5, y + 4)).median("yFRF").values
                valid = np.isfinite(profile)
                if valid.sum() < 6:
                    continue
                x, z = survey.xFRF.values[valid], profile[valid]
                end = x >= x[-1] - 10
                if end.sum() >= 4:
                    slope = -np.polyfit(x[end], z[end], 1)[0]
                    if slope > 0.005:
                        slopes.append(float(slope))
            low, median, high = np.percentile(slopes, [10, 50, 90])
            result[date] = {
                "source": record["opendap_url"],
                "acquired_at": utc(record["calibration_scan_utc"]),
                "evaluation_scan_utc": utc(record["evaluation_scan_utc"]),
                "units": "m/m",
                "coreg_qc_flag": 1,
                "sample_rows": len(slopes),
                "slope_m_per_m": round(float(median), 8),
                "slope_p10_p90_m_per_m": [round(float(v), 8) for v in (low, high)],
            }
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(build(args.source), indent=2) + "\n")
