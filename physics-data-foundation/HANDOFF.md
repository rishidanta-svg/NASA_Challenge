# POLTERGEIST unified Duck dataset handoff

This release contains the numerical dataset, including all 28 aligned acquisitions, on the `data/duck-unified-v1` branch of `rishidanta-svg/NASA_Challenge`. Collaborators need read access to the private repository.

## Checkout and verify

Run from a fresh checkout with Python 3.12. Installing dependencies requires internet access. Verification and loading use the checked-in files.

```sh
git clone --single-branch --branch data/duck-unified-v1 https://github.com/rishidanta-svg/NASA_Challenge.git
cd NASA_Challenge
python3.12 -m venv .venv
.venv/bin/python -m pip install -r physics-data-foundation/requirements.txt
.venv/bin/python physics-data-foundation/validate_collection.py --processed-only --output data/processed/verified/unified
```

On Windows, use `py -3.12 -m venv .venv` and replace `.venv/bin/python` with `.venv\Scripts\python.exe`.

The verifier checks the 45 file hashes against `SHA256SUMS`, acquisition IDs and UTC timestamps, grid and units, TIFF and NetCDF value agreement, valid-data masks, and environmental joins. It should print `"status": "passed"`, `"observations": 28`, `"pixel_rows": 40600`, `"change_cells": 168`, and `"verified_files": 45`. The SHA-256 of `SHA256SUMS` is `600e1eecbc114a14d7a80558f1e2e68fed43fdc5ef12df929496ed87e48defe5`. The SHA-256 of `duck_observations.nc` is `8ae6a0732ddfe113746a754fc4201d4516a15ddc1f6fc6918cdaf9a110ec4df9`.

## Load the dataset

```text
data/processed/verified/
  comparison/ and lidar/           Existing geospatial handoff used by the map
  unified/
    duck_observations.nc           28 aligned acquisitions, with source UTC and masks
    duck_pixels.parquet            40,600 acquisition/pixel rows
    cross_date.nc, cross_date.tif   June–October comparisons and overlap masks
    cross_date_pixels.parquet      Tabular comparison values
    cross_date_pairs.json          Sensor pairs and matching details
    june/, october/, additional/  One aligned GeoTIFF per acquisition
    environment/                   Observation and feature Parquets, plus environmental QA
    acquisition_manifest.json      UTC, source IDs, per-acquisition bands and provenance
    variable_dictionary.json      Variable definitions and units
    observation_groups.json        Acquisition indices by event group
    geospatial_qa.json              Spatial checks and overlap counts
    verification.json               Original full-source verification results
    SHA256SUMS                      Expected checksums for the 45 release files
```

From the repository root, point your loader at `data/processed/verified/unified`. You can use `POLTERGEIST_UNIFIED_DATA_DIR` to override this path in integration code. The example below uses it. The existing map backend's `POLTERGEIST_DATA_DIR` still points to the parent directory with `comparison/` and `lidar/`. Loading the unified collection into the backend and exposing it in the map require integration work.

```python
import json
import os
from pathlib import Path

import pandas as pd
import xarray as xr

root = Path(os.environ.get("POLTERGEIST_UNIFIED_DATA_DIR", "data/processed/verified/unified"))
groups = json.loads((root / "observation_groups.json").read_text(encoding="utf-8"))
with xr.open_dataset(root / "duck_observations.nc") as observations:
    june = observations.isel(observation=groups["june"]).load()
with xr.open_dataset(root / "cross_date.nc") as comparisons:
    overlap = comparisons["all_sensor_valid_overlap"].load()
conditions = pd.read_parquet(root / "environment" / "nearest.parquet")
june_conditions = conditions[conditions["id"].isin(june["id"].values)]
```

See the [dataset schema](SCHEMA.md) and [quality report](QA.md). Join environmental features by acquisition `id` and retain source timestamps and offsets. Respect validity masks and NaN values. June and October group labels contain acquisitions with distinct timestamps. The 10 m grid contains 1,450 study-area cells and 168 cells with valid overlap across the four sensor comparisons. Harmonizing the grid does not increase the native resolution of the sensors.

## Source archive and rebuild

This branch distributes 45 processed files verbatim from `POLTERGEIST_Duck_Data_Foundation.zip` together with a release-specific checksum manifest. Equivalent environmental CSV exports and the original cache are available in the source archive. The archive is 11,116,386 bytes and its SHA-256 is `3977bc71efec95fcd02552ad6e67c4a7f2345dedfa612b89baa35b23990ce983`. The [full rebuild](README.md#reproduce-the-outputs) runs from the extracted source archive. Before publication a full offline replay matched the original acquisition and comparison NetCDFs and both the nearest and antecedent environmental Parquets byte for byte.
