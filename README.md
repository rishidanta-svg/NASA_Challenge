# NASA Space Apps Challenge 2026 — Challenge #5: Dancing with the SARs

**Multisensor Coastal Boundary Validation & Littoral Workstation (Duck, NC — USACE FRF)**

When Earth-observation satellites disagree about a changing coastline, which physical feature does each sensor actually detect, what changed on the beach, and how confident should we be?

This repository pairs the **quantitative boundary validation pipeline** (`run_validation.py`, `src/`, `outputs/`) with the **Littoral — Coastal Analysis Workstation** static web UI (`dist/`). Independent NASA Space Apps project, not an official operational service.

---

## Run the integrated Littoral map

The React and MapLibre app and FastAPI data service run together from this checkout. See the [local setup and integration QA](docs/full-integration.md).

---

## Key Validation Deliverables & Quick Links

- **Plain-English Validation Report:** [`VALIDATION_SUMMARY.md`](VALIDATION_SUMMARY.md)
- **Full Dataset Citations & Acquisition Metadata (UTC):** [`CITATIONS.md`](CITATIONS.md)
- **Project Context & Evidence Rules:** [`CLAUDE.md`](CLAUDE.md)
- **Pipeline Entry Point:** [`run_validation.py`](run_validation.py) and modular scripts in [`src/`](src/)
- **Preprocessed Ground-Truth & Satellite Profiles:** [`data/processed/`](data/processed/)
- **Validation CSV Tables & Imported UI Profile Bundle:** [`outputs/`](outputs/) (including [`outputs/littoral_profiles_duck_frf.json`](outputs/littoral_profiles_duck_frf.json))
- **Projector-Ready Plotly Figures (PNG & HTML):** [`outputs/figures/`](outputs/figures/)

---

## Study Site & Headline Findings (`y = 700–1190 m`, June–October 2026)

- **Beach lowering (SUPPORTED):** Co-registered USACE FRF tower lidar (`coregQCFlag 1`, max RMS reflector error `0.097 m`) measured a median elevation change of **−0.268 m** over `17,654` common `1 m` cells (`11,684 m²` lowered by more than `0.1 m`).
- **Optical waterline (PLAUSIBLE):** Using 5-fold spatial block cross-validation (`100 m` alongshore blocks; `1,000`-resample `50 m` block bootstrap), **Sentinel-2 NDWI** locates the lidar wet/dry edge with pooled RMSE **5.4 m [4.9–5.9]** (`93%` within one `10 m` pixel, `N = 150`). An experimental tide correction using training-fold beach slope shifts pooled RMSE to **4.0 m [3.3–4.6]**.
- **Radar back-beach edge (SUPPORTED / PLAUSIBLE):** **Sentinel-1 VV** does **not** track the waterline (RMSE **31.9 m**, bias **−25.5 m** landward vs. wet/dry edge; `SUPPORTED`) and instead aligns with the **lidar dune toe** (pooled RMSE **9.2 m [7.9–10.1]**, `N = 42`; `PLAUSIBLE`). Both the Sentinel-1 VV edge (`−1.5 m`) and lidar dune toe (`−2.0 m`) moved less than one `10 m` pixel between June and October.
- **NISAR status:** main contains June30 profiles; the verified map bundle separately contains June18/October16 scenes. Acquisition times and pairings are preserved. The original document pairing check remains unresolved.
- **Automated Self-Checks:** see [`outputs/self_checks.csv`](outputs/self_checks.csv); a failed scientific pairing check is retained and does not prevent the final report being refreshed.
- **Reproduction and input validation:** [`docs/REPRODUCTION.md`](docs/REPRODUCTION.md).

---

## Reconstruction Algorithm: Robust Generalized-Bayesian Fusion

The current reconstruction layer is implemented in `src/reconstruct.py`. It keeps
the validated Sentinel-2 NDWI waterline separate from the Sentinel-1 dune-toe
estimate. For the dune toe, it combines VV/VH evidence using Student-t
observation likelihoods with a small uniform outlier component and a uniform
cross-shore prior. Because VV and VH come from the same Sentinel-1 acquisition,
their log-likelihood contributions are tempered (power 0.5 each) rather than
treated as independent observations. Large VV/VH disagreements are flagged and
the fused point estimate is withheld. LiDAR is used only after estimation for
independent scoring.

**Current local validation result (2026-11-15):** 132 of 150 alongshore rows
received accepted Bayesian dune-toe estimates; 18 were flagged as ambiguous.
On the 41 accepted rows with LiDAR dune-toe references, Bayesian RMSE was
**7.19 m**, compared with **7.16 m** for the v1 inverse-variance baseline on
those same rows. The baseline on all 42 matched rows had RMSE **7.08 m**.
Therefore, this run does **not** demonstrate an accuracy improvement from the
Bayesian estimator. Its current demonstrated benefit is explicit uncertainty
handling and withholding estimates where the two radar polarizations conflict.
The model is a generalized-Bayesian approximation, not a fully calibrated
posterior: the VV/VH dependence is tempered rather than estimated from
independent calibration data. Further validation is required before claiming
superior accuracy or operational performance.

## Reproducing the Validation Pipeline

### 1. Reproduce metrics, figures, and reports from included preprocessed data (no credentials needed)
```bash
python run_validation.py --skip-download
```

### 2. Re-fetch FRF lidar, NOAA tides, Sentinel-1 RTC, Sentinel-2 L2A, and include NISAR GCOV
Create a free [NASA Earthdata Login](https://urs.earthdata.nasa.gov) and save credentials to `~/.netrc` (or export `EARTHDATA_TOKEN`), then run:
```bash
python src/earthdata_login.py
python run_validation.py
```
This streams only the Duck, NC site window from the NISAR HDF5 granules over HTTPS, runs `lidar_boundaries.py`, `lidar_sanity.py`, `score.py`, `figures.py`, `selfcheck.py`, and regenerates `CITATIONS.md`, `VALIDATION_SUMMARY.md`, `outputs/*.csv`, and `outputs/figures/*`.

---

## Littoral — Coastal Analysis Workstation (`dist/`)

First UI release for Duck coastal reconstruction.

### Run
Serve `dist/` using any static HTTP server (e.g. `python -m http.server 8000 --directory dist`). No build step or runtime dependencies. Font loading is optional; system fallbacks work offline.

### Loading Real Duck FRF Profiles into the UI
1. Open the served `dist/` workstation in your browser.
2. Click **Import** (or open **Evidence**) and select [`outputs/littoral_profiles_duck_frf.json`](outputs/littoral_profiles_duck_frf.json).
3. This loads 5 real Duck FRF cross-shore transects (`y = 750, 850, 950, 1050, 1150 m`, June 19 & October 16, 2026 USACE lidar in `NAVD88 (geoid12b)` plus Sentinel-1 VV and Sentinel-2 NDWI boundary positions) directly into the Explore and Analyze views.

### Working interactions
Four workspaces; synthetic map pan/zoom; selectable linked transects; layer controls; acquisition comparison swipe; profile hover readouts; analysis alignment sensitivity; timeline filters; schema-checked browser-local profile imports; session JSON export and help dialog.

### Data state
All initial geometry and curves in `dist/` are synthetic until a profile JSON (such as `outputs/littoral_profiles_duck_frf.json`) is imported. No raster or actual satellite observation is embedded in `dist/`. Dataset register describes planned inputs. Profile template downloads from Evidence. Imports replace profiles, not the schematic map. Session export includes the profiles; imported sessions restore profiles only, not every saved display setting. No server upload or persistent browser storage is used.

### Profile contract
JSON `label` + `profiles[]`. Each profile: unique `id`, `label`, `units: m`, `source`, `verticalDatum`, `june: [{x,z}]`, `october: [{x,z}]`. Cross-shore `x` values must strictly increase. Both epochs must use a common local horizontal and vertical reference. Optional boundaries: `{radar, waterJune, waterOctober}`, all in the same `x` frame. June/October remain fixed UI epoch slots in this release. Do not load differently dated observations without first adapting the epoch model.

Before real-data integration: replace schematic map with georeferenced layers, connect actual acquisition records and datum/QA metadata, add field-validation and uncertainty displays. Imported values are rendered as supplied, not scientifically verified.

### Checks (UI)
JavaScript syntax passed. Profile ingestion accepted a valid fixture and rejected duplicate IDs, unsorted distances, nonfinite heights, wrong units and missing source. Browser checks confirmed transect selection updates the linked profile, expanded analysis preserves selection, alignment slider updates, event filters work and the evidence register opens. Profile file selection and mobile browser layout have not yet been end-to-end tested.
