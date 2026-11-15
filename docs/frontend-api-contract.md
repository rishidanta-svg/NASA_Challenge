# POLTERGEIST Frontend ↔ FastAPI Data Contract

This document defines the HTTP/JSON/GeoJSON/Tile contract consumed by the **POLTERGEIST** Map & Visualization frontend (`frontend/src/api/schemas.ts` and `frontend/src/api/client.ts`).

The frontend validates every response at runtime with Zod. Each verified dataset loads independently. Unavailable datasets show `AWAITING DATA`. The browser can query **NOAA CO-OPS Station 8651370 (Duck, NC)** directly if the API is unavailable.

---

## 1. Global Conventions

| Property | Requirement |
|---|---|
| **Base URL** | Configured via `VITE_API_BASE_URL` (default `http://localhost:8000`) |
| **CORS** | Allow origins `http://localhost:5173` and `http://localhost:4173`, method `GET`, header `Accept` |
| **GeoJSON CRS** | `EPSG:4326` (WGS84 `[longitude, latitude]` in decimal degrees, RFC 7946) |
| **Analysis CRS** | `EPSG:32618` (WGS84 / UTM Zone 18N, metres) |
| **Map Display Tiles** | `EPSG:3857` (Web Mercator XYZ `{z}/{x}/{y}`) |
| **Local Cross-Shore Frame** | USACE FRF local coordinates `(x_m, y_m)` in metres (`y = 700–1190 m` study reach) |
| **Timestamps** | ISO-8601 with explicit offset, UTC preferred (`"2026-06-18T15:42:11Z"`) |
| **Units** | Explicit SI unit string on every quantitative dataset (`"m"`, `"dB"`, `"m/s"`, `"°C"`, `"hPa"`) |
| **Not-Yet-Produced Data** | Return HTTP `200` with `{"status": "unavailable", "reason": "..."}` or HTTP `404` |
| **Errors** | RFC 7807 JSON (`{"title": "...", "status": 500, "detail": "..."}`) |

---

## 2. Overlay Slot Identifiers (`slot`)

The frontend provides independent scientific overlay slots (`frontend/src/config/slots.ts`). Each item returned by `GET /api/layers` maps into one slot via its `slot` field:

| `slot` | `group` | `sensor` | Physical Meaning | `inferred` |
|---|---|---|---|---|
| `lidar-dz` | `measured` | `LIDAR` | Measured bare-earth elevation change ($\Delta z$, m) | `false` |
| `nisar-hh` | `sensor` | `NISAR` | L-band GCOV backscatter, HH polarisation (dB) | `false` |
| `nisar-hv` | `sensor` | `NISAR` | L-band GCOV backscatter, HV polarisation (dB) | `false` |
| `lidar-elevation` | `measured` | `LIDAR` | Per-epoch bare-earth height (m NAVD88) | `false` |
| `lidar-coverage` | `measured` | `LIDAR` | Paired valid area fraction per 10 m cell | `false` |
| `nisar-hh-change`, `nisar-hv-change` | `sensor` | `NISAR` | October minus June scattering (dB) | `false` |
| `nisar-quality` | `sensor` | `NISAR` | GCOV valid-data support | `false` |
| `nisar-boundary` | `sensor` | `NISAR` | Extracted radar backscatter transition line (never equated with physical erosion) | `false` |
| `s1-vv` | `sensor` | `SENTINEL-1` | C-band backscatter, VV polarisation (dB) | `false` |
| `s1-vh` | `sensor` | `SENTINEL-1` | C-band backscatter, VH polarisation (dB) | `false` |
| `s1-vv-change`, `s1-vh-change` | `sensor` | `SENTINEL-1` | Repeat-pass Track 106 C-band difference, Oct 16 − Jun 30, 2026 (dB) | `false` |
| `s2-index` | `sensor` | `SENTINEL-2` | Cloud-screened optical spectral index (NDWI) | `false` |
| `s2-ndwi-change` | `sensor` | `SENTINEL-2` | Clear-sky optical NDWI difference, Oct 16 − Jun 18, 2026 | `false` |
| `s2-boundary` | `sensor` | `SENTINEL-2` | Instantaneous optical waterline at acquisition timestamp | `false` |
| `all-sensor-overlap` | `measured` | `OTHER` | 4-sensor joint valid overlap mask (`168 / 1,450` 10 m cells) | `false` |
| `model-dz` | `model` | `MODEL` | Physics-informed model elevation change estimate (m) | `true` |
| `model-sigma` | `model` | `MODEL` | Model $1\sigma$ uncertainty (m) | `true` |

 Additionally, high-resolution USACE LiDAR DEM epochs for 3D terrain rendering can be published in `GET /api/layers` with `kind: "raster_dem"` and `encoding: "terrarium"`.

---

## 3. Endpoints

### 3.1 `GET /api/study-area`
Returns the Duck FRF study area polygon in `EPSG:4326` and metadata.

```json
{
  "type": "Feature",
  "geometry": {
    "type": "Polygon",
    "coordinates": [[
      [-75.753384, 36.183704],
      [-75.750335, 36.183704],
      [-75.750335, 36.188260],
      [-75.753384, 36.188260],
      [-75.753384, 36.183704]
    ]]
  },
  "properties": {
    "name": "Duck FRF study area",
    "analysis_crs": "EPSG:32618",
    "frf_y_range_m": [700, 1190],
    "transect_ids": ["FRF-Y700", "FRF-Y800", "FRF-Y900", "FRF-Y1000", "FRF-Y1100", "FRF-Y1190"]
  }
}
```

### 3.2 `GET /api/acquisitions`
Chronological list of verified satellite and LiDAR acquisitions over Duck FRF (June–October 2026).

```json
[
  {
    "id": "NISAR_L2_GCOV_20260618T225100Z",
    "sensor": "NISAR",
    "product": "L2_GCOV",
    "acquired_at": "2026-06-18T22:51:00Z",
    "polarizations": ["HH", "HV"],
    "orbit_direction": "ascending",
    "qa": { "rtc_applied": true },
    "source_url": "https://asf.alaska.edu/"
  }
]
```

### 3.3 `GET /api/layers`
List of layer descriptors populating the scientific slots (and optional `raster_dem` LiDAR 3D terrain sources).

```json
[
  {
    "id": "lidar-dz-2026-oct-jun",
    "slot": "lidar-dz",
    "title": "USACE LiDAR Δz (Oct − Jun 2026)",
    "group": "measured",
    "sensor": "LIDAR",
    "kind": "raster_xyz",
    "tiles": ["http://localhost:8000/api/tiles/lidar-dz/{z}/{x}/{y}.png"],
    "tile_size": 256,
    "bounds": [-75.753384, 36.183704, -75.750335, 36.188260],
    "units": "m",
    "quantity": "Bare-earth elevation difference",
    "colormap": {
      "type": "diverging",
      "min": -1.5,
      "max": 1.5,
      "stops": [[-1.5, "#8c2d04"], [0.0, "#f2e6d8"], [1.5, "#0f5e7a"]]
    },
    "acquired_at": null,
    "epoch_label": "Oct 2026 − Jun 2026",
    "reference_date": null,
    "native_crs": "EPSG:32618",
    "native_resolution_m": 1.0,
    "vertical_datum": "NAVD88",
    "inferred": false,
    "status": "available",
    "provenance": {
      "source": "USACE FRF Dune/Beach LiDAR",
      "product_id": "FRF_LIDAR_202606_202610"
    }
  }
]
```

### 3.4 `GET /api/terrain/change`
Summary descriptor and statistics for the primary LiDAR elevation-change product.

### 3.5 `GET /api/transects` & `GET /api/transects/{id}`
- `GET /api/transects`: GeoJSON `FeatureCollection` of `LineString` shore-normal transects (`FRF-750`, `FRF-850`, `FRF-950`, `FRF-1050`, `FRF-1150`). Each feature's `properties` includes `x_origin_frf_m` (the USACE FRF cross-shore `x` coordinate at the transect line start) and `x_reference`.
- `GET /api/transects/{id}`: Transect geometry plus:
  - `profiles[]`: Measured June and October 2026 1 m USACE LiDAR elevation profiles (`x_m` strictly increasing distance along the transect from `x_origin_frf_m`, `z_m` in `NAVD88 (geoid12b)` metres).
  - `boundaries[]`: Separate horizontal sensor and morphological boundary picks (`type: "radar" | "optical" | "terrain"`), including Sentinel-2 NDWI optical waterline, NISAR L-band HH and Sentinel-1 C-band VV/VH radar transitions, and LiDAR `B1_wetdry`, `B2_dunetoe`, `B3_contour` (`z = 1.50 m NAVD88`). Each pick carries both `x_m` (relative to transect line start, aligned with `profiles[].points[].x_m`) and `x_frf_m` (absolute FRF cross-shore distance in metres), plus `uncertainty_m`.

### 3.6 `GET /api/analysis/{id}`
Feature-separated coastal boundary reconstruction along transect `{id}` (`state_scope: "observed boundary features; not full terrain or bathymetry"`, `inferred: true`, `units: "m"`).
- Returns per-epoch (`2026-06`, `2026-09`, `2026-10`) horizontal boundary state:
  - `waterline`: Validated Sentinel-2 NDWI optical waterline (`x_frf_m`, `x_m`, spatial block-CV `cv_rmse_m`, `source`, `status`, `acquired_at`, `granule_id`, plus experimental tide-aware `tide_aware_experimental_x_frf_m` and `mndwi_x_frf_m`).
  - `dunetoe`: Generalized-Bayesian Sentinel-1 VV/VH dune-toe reconstruction (`accepted_x_frf_m` / `accepted_x_m` when accepted or `null` when withheld due to VV/VH disagreement, `bayes_map_x_frf_m`, `bayes_median_x_frf_m`, 90% credible interval `ci90_low_frf_m`..`ci90_high_frf_m`, `posterior_sd_m`, `vv_vh_disagreement_m`, `vv_vh_disagreement_limit_m`, raw `radar_vv_x_frf_m`, `radar_vh_x_frf_m`, `nisar_hh_x_frf_m`, `nisar_hv_x_frf_m`, and `status`).
  - `validation_lidar`: Independent LiDAR validation references (`wetdry_x_frf_m`, `dunetoe_x_frf_m`, `contour_1p5m_x_frf_m`, used for scoring only and never fused into satellite estimates).
- Includes `october_minus_june` horizontal shifts (`waterline_shift_m`, `dunetoe_shift_m`), cross-validated `skill` summary metrics, and a dedicated `physics_model` slot (`status: "unavailable" | "available"`, `points: [{x_m, z_m, sigma_m}]`) so vertical physics-model profile predictions are cleanly separated from horizontal boundary positions.

### 3.6b `GET /api/boundaries/{id}.geojson`
Returns `EPSG:4326` GeoJSON `FeatureCollection` polylines for the `nisar-boundary` (`nisar-boundary-june`, `nisar-boundary-october`) and `s2-boundary` (`s2-boundary-june`, `s2-boundary-october`) overlay slots across all 50 FRF rows (`y = 700..1190 m`).

### 3.7 `GET /api/environment/latest`, `GET /api/environment/acquisitions`, & `GET /api/comparisons/pairs`
- `GET /api/environment/latest`: Latest verified NOAA/USACE environmental measurements at Duck Pier (station `8651370`), with `observed_at` UTC timestamps, `units`, `datum`, and `qc_flag`.
- `GET /api/environment/acquisitions` & `GET /api/environment/acquisitions/{id}`: Matched acquisition-time environmental observations (`environment/nearest.parquet`, `environment/tide_stage.parquet`, `environment/antecedent.parquet`) and cross-date environmental contrasts (`environment/cross_date.parquet`) across all 28 verified acquisitions.
- `GET /api/comparisons/pairs`: Cross-date pair definitions (`cross_date_pairs.json`), per-sensor valid cell counts (`1,310` NISAR, `1,450` Sentinel-1, `1,442` Sentinel-2, `168` LiDAR 10 m & `all_sensor_valid_overlap`), and environmental contrasts.

### 3.8 Raster and observed-geometry assets

Raster descriptors use relative `/api/tiles/{id}/{z}/{x}/{y}.png` URLs. Resolve them against the configured API base. `GET /api/rasters/{id}.tif` returns the original registered COG. `GET /api/transects/observations.geojson` returns the measured line segments with gaps preserved. The main transect endpoint returns one selectable reference line per profile. Its horizontal distances are relative to the start of that line, with the FRF x origin described in `x_reference`.

The selectable LiDAR 3D sources encode the 1 m UTM display DEMs with Terrarium. Tiles use AWS regional terrain outside the valid LiDAR footprint. Scientific elevations and changes use the original NAVD88 LiDAR support and preserve NoData.
