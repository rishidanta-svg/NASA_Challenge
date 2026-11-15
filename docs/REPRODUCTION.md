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

The reader supports the three corrected June18/September29/October16 acquisitions. Offline inputs are matched against their complete granule names in `data/processed/nisar_meta.csv`, rather than silently being assigned to June. The earlier June30 product is no longer the main validation input.

```sh
.venv/bin/python src/nisar.py --input /absolute/path/to/exact-granule-name.h5 --output-dir /tmp/nisar-reproduction
```

Repeat `--input` for several files, or supply `--raw-dir` / `NISAR_RAW_DIR`. `NISAR_INPUT` supplies a single path. A separate output directory avoids replacing committed products. No local input means authenticated HTTPS range access to the three recorded granules. Unknown IDs and duplicate analysis epochs fail explicitly. Local and remote routes use the source CRS before selecting pixels; offline input does not require importing Earthdata authentication code.

## Identity and timing

The metadata adapter accepts `granule`, legacy `granule_ur`, or CMR `concept_id`, preserving original fields. It rejects empty fields, duplicate monthly analysis slots, nonpositive spacing, timezone-free acquisition times and disagreements between granule timestamps and metadata. Monthly keys are analysis groups, not acquisition dates. Sentinel-1's September group includes an October4 observation; do not derive acquisition times from group labels.

Main and the map share the June18/October16 NISAR scenes; main also has a September29 ascending pass. The corrected main inputs now pass the original document pairing check. `outputs/acquisition_time_gaps.csv` records signed satellite-minus-LiDAR gaps and the input lineage.

## Spatial support and limits

Main's native LiDAR change uses y=700..1199 and 17,654 common cells. The map-native support ends at1190 and has17,466 cells. Restricting main to700..1190 gives17,467 cells; all17,466 jointly valid differences are exactly equal. One remaining native mask difference at FRF x=56,y=700 is retained, not filled. Resampled UTM maps and10m comparisons have separate masks and counts. Their medians/areas must not be swapped.

`outputs/input_audit.json` records measured geometry/mask checks and bundle integrity. Integrity is not an independent accuracy assessment. The inferred boundary products are not elevation surfaces; CV RMSE is horizontal error, not vertical sigma. Matched-row Bayesian RMSE7.188m versus baseline7.161m does not establish improvement. The unified physics collection is delivered and separately verified.

## Run integrated frontend/backend

```sh
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

In another terminal, run `npm ci` then `npm run dev` in `frontend/`. Open http://localhost:5173. For deployment set `VITE_API_BASE_URL` to an HTTPS API origin and `POLTERGEIST_CORS_ORIGINS` to the frontend origin; static hosting cannot run FastAPI.

Tests: `.venv/bin/python -m pytest backend/tests -q`; in `frontend/`, `npm test` and `npm run build`.
