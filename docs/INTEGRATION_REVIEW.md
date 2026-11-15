> Historical snapshot. Current consolidated status: [INTEGRATION_STATUS.md](INTEGRATION_STATUS.md).

# Repository integration review — 15 November 2026

## Snapshot and local copies
All five remote branch histories and tracked file bytes were fetched from rishidanta-svg/NASA_Challenge. Main is checked out in NASA_Challenge; the four other branches are separately materialized under NASA_Challenge_branches. No GitHub branch or deployed site was changed during this audit.

| Branch | Snapshot | Tracked files | What it contributes |
|---|---|---:|---|
| main | 261bec7 | 55 | Original static UI; LiDAR/Sentinel validation pipeline; metrics, figures, profile export; generalized-Bayesian boundary estimates; latest single-acquisition NISAR reader and products |
| feature/map-visualization | 6102698 | 51 | React/TypeScript/MapLibre UI; 2D/3D terrain, sensor slots, swipe comparison, cross-sections, NOAA client, schemas and tests |
| littoral/geospatial-pipeline | fb9f3ae | 98 | Radar/LiDAR extraction and alignment scripts; 86 files in two processed bundles including manifests; real raster subsets, quality masks and georeferenced transects |
| feature/full-integration | 028da6e | 202 | Prior main + map branch + geospatial branch; FastAPI metadata, raster/DEM tiles and profiles; connected React frontend |
| feature/physics-data-foundation | cc07533 | 214 | Everything in full-integration plus 12 acquisition/build/validation/package files and documentation for a unified observation collection |

The last branch is a descendant of full-integration, which already merges map-visualization and geospatial-pipeline. Do not import these four branches as unrelated parallel codebases. Latest main is one newer commit beyond their shared main ancestor. A local trial merge of latest main with physics-data-foundation succeeds without textual conflicts and contains 218 tracked paths. Textual success is not scientific or API compatibility.

## Checks actually performed
- Original branch tracked-file inventories and commit ancestry inspected.
- 26 LiDAR and 58 comparison assets checked against manifest sizes and SHA-256: all 84 matched. These checks verify repository integrity, not the scientific validity of every upstream claim.
- React frontend: TypeScript passed; 13 unit tests passed; Vite production build passed. Initial JS is approximately 1.51 MB minified / 430 KB gzip and emits the configured size warning.
- FastAPI: all five backend tests passed, including real raster color/geometry checks, COG bytes, profile extraction and a controlled terrain encoding test. This is not a new live-service/browser end-to-end validation.
- Opened all four main NetCDFs. LiDAR has three dates on a 500×130 grid; Sentinel-1/2 each have three dates and 50×351 profiles; main's NISAR has only one June date and 50×351 profiles.
- Consolidated candidate selfcheck executed: first three checks pass, then it crashes because nisar_meta.csv lacks concept_id.
- Browser/UI appearance and external basemap/NOAA connectivity were not newly tested in this audit. Earlier branch documentation contains separate historical test claims.

## Priority blockers

### 1. Generated physics collection is not in Git
physics-data-foundation/data/ does not exist in the checkout; its .gitignore excludes data/. README/QA describe duck_observations.nc, Parquet pixel tables, 28 acquisitions, 19 additional Sentinel records and acquisition-matched environmental tables, but those outputs are not delivered by the branch. Get the package_collection.py ZIP plus checksums from its producer, or rebuild from accessible source inputs. Do not display these records as loaded based solely on QA prose.

### 2. Two different June NISAR observations
The geospatial bundle uses June 18 23:53:35 UTC and October 16 23:53:31 UTC. Main's new file uses June 30 23:53:34 UTC and has no October NISAR profile. Its June LiDAR scan is June 19 00:31:03 UTC: the separation is 11 days 23:22:31, not 37 minutes. Preserve all observations by full acquisition ID and time. Do not overwrite one with the other under a generic June slot or reuse a near-synchronous claim.

### 3. Reproduction/schema regression
main src/score.py now reads r.granule; src/selfcheck.py still reads concept_id and checks the older paired granules. The new local NISAR reader requires an untracked HDF5 under data/raw/nisar and processes only one hardcoded granule. It also selects UTM bounds before verifying/reprojecting the source CRS (the shipped source declares EPSG:32618). Normalize metadata rather than discarding either ingestion route. Update selfchecks and regenerate summary/citation outputs. Existing README/VALIDATION_SUMMARY say NISAR not yet run, while run_flags.json says true: documentation is stale relative to outputs.

### 4. Analysis quantities do not match
main outputs/reconstructed_state.csv estimates waterline and dune-toe cross-shore positions, including withheld/ambiguous results and approximate uncertainty diagnostics. The frontend AnalysisSchema instead expects a full elevation profile z_m with sigma_m. These are different physical quantities. Add a feature-boundary analysis endpoint/schema and render markers/intervals. Do not convert boundary RMSE or posterior spread into elevation uncertainty or manufacture a reconstructed beach surface.

### 5. Existing API leaves useful science disconnected
/api/transects/{id} returns boundaries: []; /api/analysis/{id} explicitly returns unavailable. Sentinel raster slots remain unfilled. Main has Sentinel profiles and boundary/score CSVs, but these are not automatically exposed by the FastAPI catalog. Build adapters using acquisition IDs, proper x-reference conversion and per-feature metadata.

### 6. Deployment is still separate
The published Littoral site serves the original static dist/. The new application builds to frontend/dist/ and defaults to http://localhost:8000. Merely pushing these branches does not deploy the new app or its Python API. Choose a reachable HTTPS API host and set VITE_API_BASE_URL/CORS, or precompute appropriate static data/tiles. The current Sites static deployment does not execute the supplied FastAPI/rasterio process. Current live NOAA observations must remain distinct from conditions at June/October acquisitions. Reconcile Littoral versus POLTERGEIST branding and retain the desired Explore/Analyze/Timeline/Evidence navigation.

## Recommended integration order
1. Use full-integration's React map + FastAPI + verified June18/October16 bundles as the working functional base. Retain latest main's algorithms and outputs separately.
2. Normalize exact acquisition identifiers/timestamps, CRS, vertical datum and profiles; distinguish absent, measured and inferred data.
3. Fix NISAR metadata/selfchecks and regeneration; add June30 as an additional observation, not a substitute.
4. Expose Sentinel boundaries, validation metrics and feature-separated reconstruction through typed endpoints. Use withheld status and uncertainty caveats honestly.
5. Obtain the missing physics collection, verify its hashes/QA, then wire acquisition-matched environmental history and additional scenes.
6. Restore/polish the requested multi-workspace UI around the functional geospatial core.
7. Run end-to-end validation and deploy frontend plus reachable backend with production settings.

## Scientific display limits
Committed reconstruction_metrics.csv reports Bayesian RMSE 7.188 m vs 7.161 m for its baseline on the same 41 accepted LiDAR-reference rows; this is not a demonstrated accuracy improvement. Its useful result is uncertainty/ambiguity handling. Error scales depend on LiDAR-based validation and should not be advertised as universally calibrated posterior uncertainty or wholly independent new-site performance. Different LiDAR pipelines use different masks/support: 17,654 versus 17,466 native paired cells and their median statistics cannot be interchanged without lineage. No lower-than-pixel map sampling should be called native sensor resolution.

## Local integration candidate
The review/coastal-consolidation branch is local only. It combines the source snapshots without resolving the semantic blockers listed above. No remote push or live replacement has been performed.
