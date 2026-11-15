# POLTERGEIST local integration

The integration branch starts at GitHub main `dacae77`. It incorporates the MapLibre frontend and verified Duck geospatial artifacts through separate merge commits. The map reads the checked-in bundles under `data/processed/verified/`. Initial setup needs Internet access for dependencies, and the running app uses OpenFreeMap, AWS Terrarium and NOAA CO-OPS.

## Start locally

From the repository root, use Python 3.9 or newer and Node 22 or newer.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-api.txt
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

In a second terminal from the repository root:

```sh
cd frontend
npm ci
npm run dev
```

Open [the local map](http://localhost:5173). The map opens at the Duck study area. Enable HH, HV, elevation, change, or coverage in Scientific Overlays. Use the timeline to switch between acquisitions, or the 3D Terrain button and 3D DEM Source menu to select AWS, June LiDAR or October LiDAR.

Set `POLTERGEIST_DATA_DIR` to a directory containing the `lidar/` and `comparison/` bundles if you want a different data release. Set `POLTERGEIST_CORS_ORIGINS` to a comma-separated list of allowed browser origins for custom hosting. Defaults cover the Vite development and preview ports on the loopback host. `VITE_API_BASE_URL` controls the browser API origin.

## Data and display

- The analysis bundle keeps the 10 m UTM Zone 18N radar lattice. The display service reprojects XYZ tiles to Web Mercator with Rasterio. Scientific PNGs use source values and preserve transparent NoData. The original registered COGs are served at `/api/rasters/{id}.tif`.
- The June and October HH/HV layers display calibrated GCOV backscatter in dB. The two radar change overlays display October minus June scattering in dB. The LiDAR change overlay displays October minus June elevation in NAVD88 meters.
- The survey profiles and coordinate lines are based on the verified FRF bundle. The original measured segments are available with gaps preserved at `/api/transects/observations.geojson`. The selectable lines provide one reference baseline per profile. Profile distances begin at the first paired observation, and plotted lines break across missing samples.
- The 3D LiDAR sources provide approximately 1 m elevation where measured and use AWS Terrarium for background or gaps. This mixed terrain is for display. The source datasets may have different vertical references and resolution at the display seams.
- NOAA CO-OPS observations preserve source timestamps and flags. Tide predictions are labeled separately. Values unavailable at Duck Pier remain N/A. [NOAA CO-OPS Data API](https://api.tidesandcurrents.noaa.gov/api/prod/)
- Sentinel and physics-informed model slots remain awaiting data in this integration. The original validation pipeline and its outputs remain in the repository.

## Run the checks

```sh
.venv/bin/python -m pip install 'pytest>=8,<9'
.venv/bin/python -m pytest backend/tests
cd frontend
npm run typecheck
npm run test
npm run build
npm run e2e
```

Playwright starts or reuses FastAPI and the frontend preview. Its end-to-end check uses installed Google Chrome and reaches the actual basemap, terrain and environmental services. Screenshots are written under `frontend/test-results/`.

## Integration QA

| Check | Result |
|---|---|
| FastAPI integration tests | 5 passed |
| TypeScript and Vite | Typecheck and production build passed. Vite reports a large initial frontend bundle |
| Vitest | 13 passed |
| Playwright in Google Chrome | 1 passed. Checked the real basemap, all four NISAR HH/HV rasters, both elevation epochs, radar and LiDAR changes, coverage, the selected survey profile, the LiDAR DEM and live NOAA station 8651370. The test recorded zero failed scientific tile responses and zero uncaught page errors |
| Coordinate and numeric checks | Compared an XYZ radar pixel with its source value after EPSG:32618 → EPSG:3857 reprojection. Decoded a real LiDAR height from Terrarium within 1/256 m. Confirmed nearest-neighbor NoData transparency and original COG bytes. A COG byte-range request returned 206 |
| FRF-950 cross-section | First paired location is FRF x = 50 m, WGS84 −75.752447523°, 36.185873289°. Original June and October heights are 7.962424 m and 7.966601 m NAVD88 |

Chrome screenshots captured at the study area:

- [2D measured elevation change and meter legend](evidence/duck-2d-measured-change.png)
- [June radar and measured FRF-950 profiles](evidence/duck-june-radar.png)
- [October radar](evidence/duck-october-radar.png)
- [October LiDAR terrain at 2× vertical exaggeration](evidence/duck-3d-lidar.png)

The browser showed current water level, wind, air temperature and pressure. NOAA returned no water-temperature reading, which appeared as N/A. The imagery and study-frame placement were checked at the shoreline and reference transects. Absolute physical radar–LiDAR registration still requires surveyed control.
