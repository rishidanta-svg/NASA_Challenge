# Duck physics-guided coastal observations

The FastAPI and React workflow reads the published Duck handoff at `data/processed/verified/unified` ([data commit](https://github.com/rishidanta-svg/NASA_Challenge/commit/0b690ad)). It uses the specific June and October observations from `cross_date_pairs.json`. Processing version `duck-physics-v1` labels the optical products and radar diagnostic. Measured LiDAR inherits the verified LiDAR manifest's processing version.

## Waterlines

- NDWI is the default optical edge. MNDWI, `(B03 - B11) / (B03 + B11)`, is available as a separate comparison. The published MNDWI was calculated on the native 20 m SWIR grid. The API uses the harmonized index rasters with the clear and index-valid flags. The fixed thresholds (NDWI 0 and MNDWI 0.10) come from the existing Duck extraction. A unique crossing requires contiguous clear samples on both sides, with connected seaward water support of at least one native posting. The 1 m interpolation along FRF rows does not change the sensor resolution. Line geometries break wherever a crossing is unavailable.
- FRF x increases **seaward**. The tide-only model uses `x_c = x_o + (η - z_ref)/m`. The default reference is Duck mean high water, **1.026 m MLLW = 0.359 m NAVD88**. NOAA identifies NAVD88 zero as 0.667 m above MLLW at station 8651370, using the 1983–2001 tidal epoch. Inputs must be in metres relative to a compatible datum at that station. The model matches observed tide by exact scene ID and rejects unqualified observations outside the handoff's time tolerance. The archived calibration surveys were taken 2.9 and 6.7 days before the respective optical acquisitions. Corrected results assume the pier observation represents the study reach and the surveyed foreshore segment is locally planar. [FRF coordinates](https://essd.copernicus.org/articles/15/5135/2023/essd-15-5135-2023.html) · [NOAA 8651370 benchmark sheet](https://tidesandcurrents.noaa.gov/benchmarks/8651370.html) · [Vos et al., 2020](https://doi.org/10.1029/2020GL088365)
- `m` is the local median of positive seaward slopes measured in independent QC 1 USACE scans, in m/m. The source survey times and measured P10–P90 slope spread travel with each correction. The first-order variance is `σ_extract² + (σ_η/m)² + ((z_ref-η)σ_m/m²)² + σ_registration²` for independent errors and fixed reference level. Duck lacks a complete set of credible error terms. Its API therefore reports `sigma_m: null` and a physical slope-sensitivity interval computed from the measured P10–P90 slope spread. That interval does not include other errors or represent a confidence interval.
- Optional mean setup uses `L₀ = gTₚ²/(2π)`, `η_setup = 0.35 m sqrt(H₀L₀)`, and adds `η_setup/m` to the seaward-positive correction for a fixed reference. For comparisons to a different observation time, the setup difference between acquisitions is used. `H₀` is reverse-shoaled and refracted from colocated, QC-screened 17.4 m buoy height, period and direction. The approximation assumes linear waves, shore-parallel contours, no dissipation and incident directions with a physically admissible deep-water direction. It represents mean setup, separate from swash or extreme runup. It is conditional on unresolved differences between pier and beach setup. Wave inputs that fail those checks withhold the option. The UI requires explicitly selecting the setup overlay. [Stockdon et al., 2006](https://pubs.usgs.gov/publication/70030520) · [USGS deep-water transformation notes](https://pubs.usgs.gov/ds/602/readme.pdf) · [FRF buoy depth](https://tethys-engineering.pnnl.gov/sites/default/files/publications/SNL_SAND2022-14224.pdf)

## Terrain, radar, and API

- LiDAR change is `z_oct - z_jun` in NAVD88 (geoid12b) on valid native pairs. The server checks datum, timestamp, coregistration QC, raster grids and the difference and support against the published 1 m product. The 1 m map and 10 m coverage retain the published support. The existing strict mask remains 168 cells. Paired transect elevations and signed vertical change are served as measured observations.
- Radar change subtracts stored calibrated gamma-zero dB directly, independently for HH, HV, VV and VH. The API verifies the change and mask against the published comparison. The HH/VV layer flags opposite signs over 671 of 1,310 shared radar cells, including 76 of the 168 strict overlap cells. No detection limit for a statistically significant change is available for these scenes. The flags are directional, with no implied erosion or data failure. NISAR Track 69 is descending and Sentinel-1 Track 106 is ascending. The June Sentinel-1 repeat pass follows NISAR by 11.96 days and the October pass precedes NISAR by 56.08 minutes. The products carry source IDs, acquisition times, quality and acquisition context. The Sentinel-1 incidence bounds are for the scene. NISAR bounds come from the ancillary incidence grid.
- `GET /api/coastal/observations` provides evidence, product statuses and pooled/per-date validation. Add `?include_samples=true` to recompute from the paired predictions and reference positions. `/api/analysis/FRF-950` includes per-transect `coastal_observations` with acquisition-tagged raw, tide and setup positions, context and reasons. `/api/transects/FRF-950` returns source profiles and paired vertical differences. `/api/layers` advertises current optical/radar GeoJSON, which is served from `/api/boundaries/{id}.geojson`. `/api/terrain/change` remains the measured 1 m LiDAR map entry point. The native archive, the existing terrain upload contract, and the archived boundary models retain their original formats.
- The analysis UI shows product availability, acquisition context, physical sensitivity and retrospective error. The live NOAA station panel serves current conditions separately. Wind, gusts, rain, air pressure and temperatures are contextual when available; the correction consumes neither those fields nor live observations. Optical overlays match the exact timeline date. An unavailable scene returns no substitute. The radar layer is labeled with its separate pair dates.

## Validation

Errors are horizontal estimated FRF x minus the LiDAR reference x. The runtime comparison holds the **same raw crossing** fixed for tide and setup and scores methods on the same rows per comparison.

| Reference and sample | Raw RMSE / MAE / bias (m) | Tide RMSE / MAE / bias (m) | RMSE reduction |
|---|---:|---:|---:|
| October 0.36 m NAVD88 LiDAR contour, n=36 | 7.42 / 7.15 / −7.15 | 3.73 / 3.31 / −3.16 | 49.7% |
| June and October seaward LiDAR-return proxy at the survey-time gauge level, n=96 | 6.36 / 5.28 / −3.44 | 4.80 / 4.10 / +4.03 | 24.6% |
| June proxy, n=48 | 2.97 / 2.38 / +1.28 | 4.30 / 3.51 / +3.37 | −44.9% |
| October proxy, n=48 | 8.49 / 8.17 / −8.17 | 5.24 / 4.70 / +4.70 | 38.2% |

Experimental setup on the same 36 October contour rows gave **2.19 m RMSE, 1.88 m MAE, −0.94 m bias**. On the same 48 October survey-proxy rows setup gave **4.18 m RMSE, 3.57 m MAE, +3.48 m bias**. The June wave setup comparison at the survey-time proxy was withheld because the buoy wave direction could not be reverse-refracted to deep water. The June LiDAR scan did not yield a matched fixed-MHW contour. The cloud-screened positions are 7.50 and 8.47 hours apart from their respective LiDAR acquisitions. The seaward edge of LiDAR ground returns is a proxy affected by swash and survey filtering. These comparisons are retrospective and local, with one fixed-contour date and spatially correlated rows. There is no demonstrated held-out skill for the latest map configuration or reason to enable setup by default.

The separately reproduced [strict legacy benchmark](https://github.com/rishidanta-svg/NASA_Challenge/blob/1a6573e/outputs/improvements_position.csv) used June, September and October and a separate extraction/threshold fit for each method, trained outside the test date and 100 m stretch. It used only prior independent LiDAR scans for slope and targeted the seaward-return proxy at each survey-time tide. On the same 150 rows, its raw→tide RMSE was **6.083→3.016 m** (50.4% reduction), MAE **5.180→2.553 m**, and bias **−0.658→+0.272 m**. Legacy tide + R2% runup yielded **3.449 m RMSE**. That runup experiment differs from the current mean-setup option. The [legacy dune displacement change test](https://github.com/rishidanta-svg/NASA_Challenge/blob/1a6573e/outputs/improvements_change.csv) produced **11.026 m RMSE** with radar fusion versus **2.598 m** for no change (13 rows). The distinct [Bayesian dune position test](https://github.com/rishidanta-svg/NASA_Challenge/blob/261bec7/outputs/reconstruction_metrics.csv) reproduced **7.188 m RMSE** versus **7.161 m** for its matched baseline (41 rows). Both remain traceable historical results. No NISAR-based terrain prediction is included in the current workflow.

## Reproduction commands

From the repository root with API dependencies installed and the verified bundle in place:

```sh
.venv/bin/python -m pytest -q backend/tests
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
curl -fsS 'http://127.0.0.1:8000/api/coastal/observations?include_samples=true'
(cd frontend && npm ci && npm test && npm run build && npm run e2e)
```

The archived check uses the existing validation dependencies (NumPy, pandas, xarray, pyproj and netCDF4). This keeps the historical code and results separate from the API and the current branch's data.

```sh
legacy_dir="$(mktemp -d)"
git archive 1a6573e data/processed outputs/lidar_boundaries.csv src | tar -xf - -C "$legacy_dir"
mkdir "$legacy_dir/reproduced"
SARS_OUT="$legacy_dir/reproduced" .venv/bin/python "$legacy_dir/src/score.py"
SARS_OUT="$legacy_dir/reproduced" .venv/bin/python "$legacy_dir/src/improvements.py"
.venv/bin/python scripts/build_duck_calibration.py "$legacy_dir/data/processed" "$legacy_dir/duck_foreshore_slopes.json"
diff data/processed/verified/physics/duck_foreshore_slopes.json "$legacy_dir/duck_foreshore_slopes.json"

bayes_dir="$(mktemp -d)"
git archive 261bec7 data/processed outputs src | tar -xf - -C "$bayes_dir"
.venv/bin/python "$bayes_dir/src/reconstruct.py"
```
