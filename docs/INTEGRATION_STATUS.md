# Integrated Poltergeist status — 15 November 2026

The branch review/coastal-consolidation combines the cleaned map-first UI with every reviewed team update through the following snapshots:

| Source | Integrated snapshot | Contribution |
|---|---|---|
| main | f0ae952 | Three-date independent validation, corrected NISAR scenes, calibration surveys, waves and generated reports |
| feature/duck-nisar-analysis | e28f5ed | NISAR HH extraction, buffered nested spatial elevation-change ablation, physics workflow and environment fixes |
| feature/duck-physics-fusion | 5003315 | Included as ancestor of e28f5ed; optical corrections, datum handling, independent slope artifact, measured profiles |
| feature/full-integration / fix_pyarrow_dependency_conflicts | 7ca1f75 | Included as ancestor of e28f5ed; unified API and explicit environmental loading errors, PyArrow 21 pin |
| data/duck-unified-v1 | 0b690ad | Included as ancestor; all 28 acquisitions and 45 verified release assets |

## Delivered

- No return to the crowded interface. Findings now reads current /api/coastal/observations and /api/coastal/nisar, with horizontal optical validation clearly separate from vertical terrain errors.
- All available science overlays can be selected under Layers → More satellite comparisons, including optical/tide/setup, Sentinel rasters and differences, coverage/disagreement and exploratory NISAR HH candidates.
- NISAR candidate lines remain explicitly marked as failed shoreline comparisons. Isolated candidate points are rendered; unavailable dates are not silently substituted for exact-date products.
- Measured profile plots use true paired LiDAR support and retain gaps. The older Bayesian model is not drawn as a predicted beach surface or presented as current physics.
- Exports include current physics, selected transect observations and NISAR experiment metadata, including source acquisition pairs and withheld statuses.
- Corrected metadata, local/remote NISAR input options, source-CRS window selection, input audits and signed acquisition gaps are retained alongside the new team pipeline.
- Root requirements.txt now selects the compatible Python 3.11 integrated stack. Team's original science-version pins remain in legacy/requirements-science-verified.txt for historical reproducibility.
- A single launcher starts the matching API/UI ports and CORS configuration; README explains that the local terminal must stay open.

## Verification

- 44 Python/backend tests passed, including source-ID/datum/withholding tests, NISAR ablation and spatial hold-out regression checks.
- 17 frontend tests passed with POLTERGEIST_PYTHON configured, including four tests validating real backend JSON against frontend schemas.
- TypeScript and Vite production build passed. A large initial map bundle warning remains; this does not invalidate the build.
- Full offline numerical pipeline passed: 14 self-checks PASS; refreshed reports, citations, application data and HTML plots. Existing PNGs retained using --skip-png because local Chrome image export is unavailable.
- Unified processed-data validator passed: 28 observations, 40,600 pixel rows, 290,341 environmental rows, 694 nearest matches, 168 comparison cells and 45 verified files.
- Browser manually checked connected current findings, NISAR metrics/withholding, scientific layer selection and exploratory labelling. Updated browser-test scenarios are supplied; a Chrome CLI test run was not performed here.

## Remaining work

| Issue | Status / next step |
|---|---|
| Independent temporal or new-site validation | Pending research; one change interval and one coastline do not establish generalization |
| Demonstrated benefit from NISAR | Not demonstrated: B RMSE 0.2549 m vs C 0.2582 m; retain the unfavorable ablation honestly |
| NISAR waterline validity | Failed for both scenes; candidates remain exploratory, shoreline error scores withheld |
| Calibrated prediction intervals and erosion/deposition detection limits | Withheld; requires defensible measurement/registration uncertainty and independent coverage testing |
| Timing, registration and general physical assumptions | Source times, geometry and caveats are exposed; asynchronous data and unresolved co-registration cannot be cured by UI integration |
| Production hosting | Not deployed: needs reachable HTTPS Python API and a frontend build configured for it |
| Google photorealistic terrain | Optional; no API key/billing project supplied. Existing Esri imagery plus measured/regional elevation remains the map |
| Map performance | Non-blocking large-bundle warning; defer code splitting until performance work is scheduled |

These are scientific/deployment limitations, not hidden missing-data or schema integration tasks. No improved NISAR terrain model or erosion forecast is enabled by this merge.
