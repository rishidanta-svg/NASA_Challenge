# Reproduction, Spatial Support, and Deployment Audit

This document records the authoritative reproduction checks, spatial support distinctions, datum conventions, and archived historical provenance for POLTERGEIST.

## 1. Active Runtime Reproduction

Create an isolated Python 3.11 environment (required for compatibility with pinned `numpy==1.26.4`, `pyarrow==21.0.0`, and `rasterio==1.4.3`) and verify both backend and frontend:

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python physics-data-foundation/validate_collection.py --processed-only --output data/processed/verified/unified

npm --prefix frontend ci
npm --prefix frontend run typecheck
POLTERGEIST_PYTHON="$(pwd)/.venv/bin/python" npm --prefix frontend test
npm --prefix frontend run build
```

Run FastAPI standalone or with the Vite dev server:

```sh
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
npm --prefix frontend run dev
```

For production deployment with separate hosts, set `VITE_API_BASE_URL` at frontend build time to an HTTPS API origin and allow that origin via `POLTERGEIST_CORS_ORIGINS`.

## 2. Runtime File & Container Requirements

In addition to `data/processed/verified/`, `backend/reconstruction.py` loads five verified metadata/boundary CSVs at runtime:
- `outputs/metrics.csv`
- `outputs/sensor_boundaries.csv`
- `outputs/lidar_boundaries.csv`
- `data/processed/s1_meta.csv`
- `data/processed/s2_meta.csv`

`.dockerignore` explicitly excludes non-essential files in `outputs/*` while whitelisting those three `outputs/*.csv` files, and `Dockerfile` copies both those CSVs and `data/processed/{s1,s2}_meta.csv` into the runtime image so `/api/boundaries/*`, `/api/transects/{id}`, and `/api/analysis/{id}` operate identically in containers.

## 3. Spatial Support, Datum & Scientific Constraints

- **LiDAR native support:**
  - The June–October Duck pipeline reach (`y = 700–1199 m`, documented in the archived validation summary) spans `17,654` common `1 m` cells with `-0.268 m` median vertical change and `~11,684 m²` lowering `> 0.1 m`.
  - The map-native paired bundle (`y = 700–1190 m`) contains `17,466` paired `1 m` cells (`−0.269 m` median, `−0.314 m` mean).
  - Resampled UTM layers and 10 m overlap diagnostics (`168` strict 4-sensor cells at ≥50% LiDAR coverage; `1,310` NISAR valid study cells) use distinct masks and must never be conflated.
- **Foreshore slope independence & vertical datum:**
  - Optical tide adjustments use foreshore slopes exported from separate independent QC-flag-1 calibration scans (`data/processed/verified/physics/duck_foreshore_slopes.json`), not the evaluation LiDAR scan being scored.
  - Duck Mean High Water at NOAA Station `8651370` (`1983–2001` tidal epoch) is `1.026 m MLLW = 0.359 m NAVD88` (`NAVD88 0 m = 0.667 m MLLW`).
  - Current live NOAA conditions displayed in `About` are never substituted into June or October retrospective tide calculations.
- **No false NISAR attribution:**
  - The `49.7%` horizontal RMSE reduction (`7.42 m → 3.73 m` over 36 October MHW positions) applies solely to tide-corrected Sentinel-2 NDWI optical boundaries.
  - NISAR HH waterline extraction (`nisar-hh-land-water-candidate`) failed the physical comparability check and remains exploratory; adding NISAR in terrain ablation (`Model C`, `0.2582 m`) did not outperform Sentinel-only (`Model B`, `0.2549 m`).

## 4. Reproducing the Archived Historical Pipeline

The pre-cleanup three-date historical validation pipeline (`src/`, `run_validation.py`, NetCDF cubes `data/processed/*.nc`, earlier `outputs/`, historical figures, and the legacy static viewer) is preserved in Git tag `archive/pre-cleanup-v1` (branch `archive/historical-validation`). To reproduce it in an isolated temporary directory without modifying `main`:

```sh
hist_dir="$(mktemp -d)"
git archive archive/pre-cleanup-v1 | tar -xf - -C "$hist_dir"
.venv/bin/python -m pip install -r "$hist_dir/requirements-validation.txt"
"$hist_dir/.venv/bin/python" "$hist_dir/run_validation.py" --skip-download --skip-png
```

Calibration foreshore slopes (`data/processed/verified/physics/duck_foreshore_slopes.json`) can likewise be verified against the archived calibration NetCDF:

```sh
cal_dir="$(mktemp -d)"
git archive archive/pre-cleanup-v1 data/processed/lidar_calibration.nc data/processed/lidar_calibration_meta.csv | tar -xf - -C "$cal_dir"
.venv/bin/python scripts/build_duck_calibration.py "$cal_dir/data/processed" "$cal_dir/duck_foreshore_slopes.json"
diff data/processed/verified/physics/duck_foreshore_slopes.json "$cal_dir/duck_foreshore_slopes.json"
```
