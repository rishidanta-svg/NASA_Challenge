# POLTERGEIST — Coastal Observatory (NASA Space Apps 2026)

Interactive multi-sensor coastal observation platform for **Duck, North Carolina** (USACE Field Research Facility, June–October 2026), built with FastAPI, Rasterio, React, TypeScript, and MapLibre GL JS.

POLTERGEIST integrates airborne **USACE LiDAR** elevation truth, **Sentinel-2** optical shorelines, **Sentinel-1** C-band SAR, **NASA–ISRO NISAR** L-band SAR, and matched **NOAA / FRF** ocean-atmosphere telemetry so users can inspect coastal change without conflating satellite scattering signatures with verified erosion.

> **Research observatory notice:** Observed quantities, conditional tide-adjusted estimates, exploratory SAR signals, and withheld models are strictly distinguished throughout the API and UI.

---

## Core Capabilities

- **Guided Tour (5 interactive steps):** Walks users step-by-step through the Duck study area, NISAR HH/HV backscatter and temporal change, cross-sensor satellite swipe comparison, independent USACE LiDAR elevation truth (`CrossSection` profiles), and Sentinel-2 optical tide correction (*"Don't just detect change. Verify it."*).
- **Explore, Layers, Compare & Findings:** Interactive 2D/3D MapLibre terrain (`1 m` USACE LiDAR merged over AWS Terrarium), synchronized June vs. October swipe comparison, coordinate inspector (`WGS84` / `UTM 18N` / `USACE FRF`), measured cross-shore profiles with gap preservation, and downloadable JSON evidence bundles.
- **Unified Verified Dataset (`data/processed/verified/`):** 28 cataloged multi-sensor acquisitions, 45 checksummed assets, 4-epoch Parquet environmental telemetry tables (`nearest`, `tide_stage`, `antecedent`, `cross_date`), and strict explicit error reporting if required Parquet/GeoTIFF files are unavailable.

---

## Verified Methodology & Key Findings

1. **Physical Coastal Elevation Change (USACE LiDAR, Measured):**
   - **−0.268 m median beach lowering** across **17,654 matched 1 m cells** (`y = 700–1199 m`, June → October 2026), with approximately **11,684 m²** lowering more than `0.1 m`.
   - On the paired `y = 700–1190 m` map subset (`17,466` native paired cells), median vertical change is **−0.269 m** (mean **−0.314 m**).
   - *Limitation:* Measures vertical bare-earth surface change (`NAVD88`) between survey dates, not confirmed net sediment volume loss across the complete nearshore profile.

2. **Optical Waterline Accuracy via Tide Correction (Sentinel-2, Verified Retrospective):**
   - Translating instantaneous cloud-masked **Sentinel-2 NDWI** waterlines along independent pre-surveyed USACE foreshore slopes using matched **NOAA Station 8651370** water levels (`MHW = 0.359 m NAVD88 = 1.026 m MLLW`) reduces horizontal shoreline-position RMSE by **49.7%** (**7.42 m → 3.73 m**) across **36 matched October LiDAR MHW positions**.
   - *Limitation:* Attributed strictly to Sentinel-2 optical physics and prior foreshore slope/gauge data — not satellite-only, not claimed universal, and **never attributed to NISAR**. Experimental wave-setup sensitivity (`physics-s2-setup`) remains opt-in and non-operational.

3. **Multi-Sensor Radar Comparison & Negative Results (NISAR & Sentinel-1, Withheld / Exploratory):**
   - **Cross-sensor divergence:** **76 of 168 strict overlap cells** (**671 of 1,310** wider radar cells) exhibit opposite change signs between NISAR L-band ΔHH (`Track 069` descending) and Sentinel-1 C-band ΔVV (`Track 106` ascending). Wavelength differences, viewing geometry, overpass timing offsets (June `4.42 days`, October `45.2 min`), and moisture/wave conditions may all contribute; this dataset does not isolate a single cause.
   - **NISAR HH waterline candidate (`Exploratory`):** Fails the physical scene comparability screen (`39.95 m` June and `37.76 m` October landward offset vs. tide-transferred Sentinel-2); shoreline metrics are withheld.
   - **Spatial terrain ablation (`Withheld`):** Over 5 held-out 100 m alongshore blocks (`n = 168`), adding NISAR (`Model C`, `0.2582 m` RMSE) did not improve over Sentinel-1 + Sentinel-2 (`Model B`, `0.2549 m` RMSE). Terrain prediction deployment remains withheld.

---

## Local Development

Requirements: **Python 3.11** and **Node.js 22+**.

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm --prefix frontend ci
.venv/bin/python scripts/run_local.py
```

Open `http://localhost:5173`. Keep the launcher terminal open while exploring. Use `--api-port` / `--web-port` if default ports are occupied.

To run the API and frontend separately:

```sh
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
npm --prefix frontend run dev
```

---

## Verification & Tests

```sh
# 1. Backend API, Parquet telemetry, reconstruction, and NISAR withholding tests
.venv/bin/python -m pytest backend/tests -q

# 2. Unified dataset integrity check (28 observations, 45 verified assets)
.venv/bin/python physics-data-foundation/validate_collection.py --processed-only --output data/processed/verified/unified

# 3. Frontend typecheck, unit/contract suite, and production build
npm --prefix frontend run typecheck
POLTERGEIST_PYTHON="$(pwd)/.venv/bin/python" npm --prefix frontend test
npm --prefix frontend run build

# 4. Browser E2E tests (requires Google Chrome + Playwright)
POLTERGEIST_PYTHON="$(pwd)/.venv/bin/python" npm --prefix frontend run e2e
```

---

## Production Deployment

### Option A — Single Container (Recommended)
The root [Dockerfile](Dockerfile) builds `frontend/dist/` with same-origin API routes (`VITE_API_BASE_URL=""`), installs `requirements-api.txt`, copies `backend/`, `data/processed/verified/`, required `outputs/{metrics,sensor_boundaries,lidar_boundaries}.csv`, and `data/processed/{s1,s2}_meta.csv`, and serves both `/api/*` and the SPA on port `${PORT:-8000}` with healthcheck `GET /health`:

```sh
docker build -t poltergeist .
docker run -p 8000:8000 poltergeist
```

### Option B — Separate Frontend & API
Host `uvicorn backend.app:app --host 0.0.0.0 --port 8000` with `POLTERGEIST_CORS_ORIGINS=https://your-frontend-origin`, and build `frontend/` with `VITE_API_BASE_URL=https://your-api-origin npm --prefix frontend run build`.

---

## Documentation & Provenance

- [Duck Optical & Terrain Physics](docs/duck-physics.md)
- [Duck NISAR Experiments & API Handoff](docs/duck-nisar.md)
- [Frontend–API Data Contract](docs/frontend-api-contract.md)
- [Reproduction, Support Extent & Container Notes](docs/REPRODUCTION.md)
- [Verified Pipeline QA Notes](reports/duck_pipeline.md)
- [Data Citations](CITATIONS.md)
- *Historical archive:* The pre-cleanup validation pipeline (`src/`, `run_validation.py`, NetCDF tables, historical figures, and legacy prototype) is preserved intact in Git tag `archive/pre-cleanup-v1` and branch `archive/historical-validation`.
