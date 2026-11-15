# Reproduction and input audit

Use Python 3.11 (the geospatial stack pins NumPy 1.26.4). Create an isolated virtual environment, then install:

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-validation.txt
.venv/bin/python -m pip install -r requirements-api.txt
.venv/bin/python run_validation.py --skip-download
```

Add `--skip-png` on a machine without Chrome to regenerate science products, HTML plots and reports while retaining existing PNGs. PNG export is not part of numerical validation.

`--skip-download` reuses committed NetCDFs and verified raster bundles; Earthdata credentials and raw HDF5 files are unnecessary for scoring, reconstruction and reports. The pipeline first audits input schemas, bundle hashes and spatial supports. It exits nonzero if self-checks fail, while still refreshing `VALIDATION_SUMMARY.md` and `CITATIONS.md`. A nonzero result is not automatically a software crash: inspect `outputs/self_checks.csv`.

## NISAR input configuration

The main reader currently reproduces the single June30 GCOV product already used by main. It does not silently replace it with the June18 or October16 scenes from the separate geospatial pipeline.

```sh
.venv/bin/python src/nisar.py --input /absolute/path/NISAR_L2_PR_GCOV_024_069_D_070_4005_DHDH_A_20260630T235334_20260630T235409_P05023_N_F_J_001.h5 --output-dir /tmp/nisar-reproduction
```

`NISAR_INPUT` supplies the same input path; `--raw-dir` or `NISAR_RAW_DIR` chooses the search directory. Without either, the reader searches `data/raw/nisar/`. `--output-dir` defaults to `data/processed/`; use a separate directory to inspect reproduction without overwriting committed products. This reader does not download data. Unsupported acquisition IDs fail explicitly. PNG figure export uses Kaleido and requires an installed Chrome/Chromium browser. The source EPSG is read before transforming the UTM study window into source coordinates.

## Identity and timing

The metadata adapter accepts `granule`, legacy `granule_ur`, or CMR `concept_id`, preserving original fields. It rejects empty fields, duplicate monthly analysis slots, nonpositive spacing, timezone-free acquisition times and disagreements between granule timestamps and metadata. Monthly keys are analysis groups, not acquisition dates. Sentinel-1's September group includes an October4 observation; do not derive acquisition times from group labels.

Main uses June30 NISAR; the map bundle uses June18 and October16. The original document pairing check remains FAIL until the team confirms/reproduces the intended pairings. Neither timestamps nor expected IDs were edited to make it pass. `outputs/acquisition_time_gaps.csv` records signed satellite-minus-LiDAR gaps and the input lineage.

## Spatial support and limits

Main's native LiDAR change uses y=700..1199 and 17,654 common cells. The map-native support ends at1190 and has17,466 cells. Restricting main to700..1190 gives17,467 cells; all17,466 jointly valid differences are exactly equal. One remaining native mask difference at FRF x=56,y=700 is retained, not filled. Resampled UTM maps and10m comparisons have separate masks and counts. Their medians/areas must not be swapped.

`outputs/input_audit.json` records measured geometry/mask checks and bundle integrity. Integrity is not an independent accuracy assessment. The inferred boundary products are not elevation surfaces; CV RMSE is horizontal error, not vertical sigma. Matched-row Bayesian RMSE7.188m versus baseline7.161m does not establish improvement. The generated physics collection is still absent.

## Run integrated frontend/backend

```sh
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

In another terminal, run `npm ci` then `npm run dev` in `frontend/`. Open http://localhost:5173. For deployment set `VITE_API_BASE_URL` to an HTTPS API origin and `POLTERGEIST_CORS_ORIGINS` to the frontend origin; static hosting cannot run FastAPI.

Tests: `.venv/bin/python -m pytest backend/tests -q`; in `frontend/`, `npm test` and `npm run build`.
