# Duck NISAR experiments

The two experiments reuse the verified Duck dataset in `data/processed/verified/unified` and the existing optical/tide and LiDAR workflow. Processing version `duck-nisar-hh-v1` applies to the current results. Neither experiment adds terrain predictions to the app.

## Verified inputs and HH extraction

The June 18 and October 16 NISAR L-band scenes share descending Track 069, Frame 070, left look, frequency-A HH and HV, 10 m native posting, producer version 1.0.11, and provisional CRID P05023. The API compares the manifest and HDF5 subset provenance to the raster grid and times, requires valid subswath support, positive number of looks and zero input-data exception flags, and checks `10 log10(gamma0)` against the published dB values. The checked repeat support is 1,310 cells for each polarization. The ancillary incidence grid spans about 39.73°–40.19° in both scenes. Its posting is 500 m, so it serves as scene geometry rather than a 10 m predictor.

The [NASA/ASF GCOV guide](https://nisar-docs.asf.alaska.edu/gcov/) describes the calibrated gamma-zero quantity. The [provisional issues bulletin](https://nisar-docs.asf.alaska.edu/provisional-known-issues/) applies to the source release. The joint L+S banding caveat is inapplicable to these L-only scenes. The diagnostic-mode exceptions name other track/frame combinations. The local masks and exact grid checks confirmed the retained support. They cannot rule out an upstream incomplete-L0B artifact, subtle radiometric or geolocation error, or establish a scene noise floor. No scene defect was inferred solely from the product maturity.

The HH-only extraction fits an Otsu threshold to all 1,310 shared HH cells per scene after a single masked 3×3 median. It retains dark components connected to a valid offshore seed at FRF x ≥160 m. A candidate is the midpoint of a 10 m sample bracket, with bright land toward the dune, dark connected pixels toward the ocean and a unique crossing along each FRF transect. Crossings are on a 10 m sampling step. Gaps stay open in the map geometry. These choices use the [FRF orientation and offshore coordinate](https://essd.copernicus.org/articles/15/5135/2023/essd-15-5135-2023.html) and build on [SAR shoreline and HH contrast research](https://doi.org/10.1080/21664250.2018.1560685) and [SAR threshold and connected-water extraction](https://www.mdpi.com/2071-1050/15/9/7199).

| HH extraction | June | October |
|---|---:|---:|
| Candidate rows of 50 | 39 | 37 |
| Otsu threshold in dB | −15.41 | −14.21 |
| Candidate FRF x range | 60–90 m | 60–80 m |
| Available rows at nominal threshold −1 dB / +1 dB | 48 / 30 | 40 / 26 |
| Largest shift on shared rows across ±1 dB perturbations | 20 m | 10 m |
| Available rows with unfiltered Otsu | 31 | 29 |
| Largest shared-row shift with unfiltered Otsu | 20 m | 40 m |

### Physically comparable shoreline check

After freezing the HH extractions, the app transfers the existing cloud-screened Sentinel-2 NDWI position to the NISAR acquisition's observed NOAA water level using the existing seaward-positive equation `x_norm = x_obs + (η_obs − η_ref) / m` and the prior independent USACE foreshore slope. Both water levels share the same Duck station datum. The screen uses the measured P10–P90 slope sensitivity range, expanded by one full nominal posting from each sensor (20 m total). That expansion is a conservative comparability tolerance. The screen requires a majority of matched positions to be consistent before any instantaneous-waterline comparison proceeds. It does not optimize the HH threshold or use evaluation LiDAR. Tide adjustment between sensors is conditional on a locally planar foreshore and time separation under 12 hours. Swash and beach change between overpasses are unresolved.

Only 2 of 39 June positions and 1 of 37 October positions were consistent. Candidate positions were typically **39.95 m landward in June** and **37.76 m landward in October** of the transferred optical waterline. Time gaps were about 7.85 hours from Sentinel‑2 to NISAR. The scene-level instantaneous-waterline test failed in both acquisitions. The API reports the separate exploratory HH brightness transition and withholds tide-corrected NISAR shoreline positions and LiDAR shoreline RMSE, MAE and bias.

In October, 27 candidate rows intersected the 36 LiDAR mean-high-water reference rows spatially. Zero passed the required scene comparability screen. NISAR was 20.75 minutes later than LiDAR. June has no matched fixed-MHW LiDAR reference. The weaker June wet/dry-return proxy had 48 rows, 39 with a geometric candidate; NISAR was 37.19 minutes earlier than LiDAR. Neither proxy is included in an MHW error score. The existing independent October optical comparison still reports 7.42 m raw and 3.73 m tide-corrected RMSE over all 36 reference rows.

## Terrain-change ablation

The target is measured October-minus-June elevation in metres NAVD88 (geoid12b) on the verified 168-cell strict overlap grid. The paired 1 m measurements contribute to that target, without generating extra NISAR training samples. The 1,310-cell unlabeled feature inventory includes each date's HH and HV, the changes and each date's HH−HV contrast and its change. Model A uses June HH/HV and October-minus-June HH/HV. These four variables retain the October information without also penalizing redundant copies. Model B uses Sentinel-2 B04/B11/MNDWI and Sentinel-1 VV/VH changes. Model C combines A and B. Environmental conditions and incidence are only interpretive metadata.

Each model predicts identical rows in five held-out 100 m FRF alongshore strips. Training excludes the entire test strip and another 30 m on either side. Inner buffered spatial validation selects the ridge penalty on the training set. Standardization, training-mean baseline and fit are recalculated in each fold. No spatially smoothed features or LiDAR predictors are used. All metrics below use prediction minus measured elevation change and pool only the held-out predictions. The data come from one temporal interval.

| Model | n | RMSE (m) | MAE (m) | Bias (m) |
|---|---:|---:|---:|---:|
| Zero change | 168 | 0.4237 | 0.3286 | +0.3150 |
| Training-fold mean | 168 | 0.2962 | 0.2364 | −0.0121 |
| A · NISAR only | 168 | 0.2990 | 0.2381 | −0.0199 |
| B · Sentinel-1 and Sentinel-2 | 168 | 0.2549 | 0.2066 | −0.0074 |
| C · B plus NISAR | 168 | 0.2582 | 0.2110 | −0.0098 |

NISAR increased pooled RMSE by **0.00329 m (+1.29%)** and MAE by **0.00437 m**. C had lower RMSE in just one of five strips. This is a local, descriptive ablation. The small difference does not establish a universal ranking and does not support deploying C as an improved terrain detector. Sentinel‑1's repeat-pass selection leads to a June pairing 11.96 days after NISAR and an October pairing 56.08 minutes earlier. The ablation cannot separate frequency value from acquisition timing. Classification is withheld because a defensible pixel-level detection limit cannot be derived from the available survey uncertainties. The 148 negative and 20 positive values are observed signs. The existing 76-of-168 NISAR–Sentinel-1 opposite-sign result still describes scattering disagreement.

## Frontend handoff

- `GET /api/coastal/nisar` returns `processing_version`, `input_qa`, `shoreline` and `terrain_ablation`.
- `input_qa` provides source acquisition identity, time, calibration, QA checks, incidence and unlabeled feature coverage. Its `supported` status means the local data checks passed.
- `shoreline.epochs.{june,october}` provides candidate availability, rejection reasons, threshold sensitivity, and `comparability` and `validation` objects. Render the candidate as exploratory. `waterline_status: failed` and `validation.*.status: withheld` indicate that it must not appear as an estimated or validated waterline. `methods: null` and `n: 0` represent absent comparable validation.
- `terrain_ablation` provides acquisition pairs, protocol, model features, pooled and per-strip metrics plus the paired `C_minus_B_rmse_m`, percent and `terrain_model_deployment` status. Positive deltas mean higher held-out error when adding NISAR. The optional `?include_samples=true` exposes per-transect extraction diagnostics, any qualifying shoreline reference rows, and 168 measured and out-of-fold terrain comparison rows.
- `GET /api/layers` exposes slot `nisar-hh-land-water-candidate` with IDs `nisar-hh-land-water-candidate-june` and `nisar-hh-land-water-candidate-october`. Fetch each at `/api/boundaries/{id}.geojson`. Geometries are WGS84 lines, plus points for isolated candidates. Switch on the exact acquisition date and keep the exploratory label visible. `qa.waterline_status` is independent of layer availability. The legacy NISAR gradient edge and the radar-disagreement layer remain separately addressable.

To reproduce from the checkout:

```sh
.venv/bin/python -m pytest -q backend/tests
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8016
curl -fsS 'http://127.0.0.1:8016/api/coastal/nisar?include_samples=true'
```
