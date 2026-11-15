# POLTERGEIST Frontend ↔ FastAPI Data Contract

This document defines the HTTP/JSON/GeoJSON/Tile contract consumed by the **POLTERGEIST** Map & Visualization frontend (`frontend/src/api/schemas.ts` and `frontend/src/api/client.ts`).

The frontend validates every response at runtime with Zod. While the FastAPI backend is offline or a specific dataset is not yet produced, the frontend remains functional using clearly watermarked `MOCK` overlays, `AWAITING DATA` slot badges, and direct browser queries to **NOAA CO-OPS Station 8651370 (Duck, NC)**.

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

The frontend provides 10 independent scientific overlay slots (`frontend/src/config/slots.ts`). Each item returned by `GET /api/layers` maps into one slot via its `slot` field:

| `slot` | `group` | `sensor` | Physical Meaning | `inferred` |
|---|---|---|---|---|
| `lidar-dz` | `measured` | `LIDAR` | Measured bare-earth elevation change ($\Delta z$, m) | `false` |
| `nisar-hh` | `sensor` | `NISAR` | L-band GCOV backscatter, HH polarisation (dB) | `false` |
| `nisar-hv` | `sensor` | `NISAR` | L-band GCOV backscatter, HV polarisation (dB) | `false` |
| `nisar-boundary` | `sensor` | `NISAR` | Extracted radar backscatter transition line (never equated with physical erosion) | `false` |
| `s1-vv` | `sensor` | `SENTINEL-1` | C-band backscatter, VV polarisation (dB) | `false` |
| `s1-vh` | `sensor` | `SENTINEL-1` | C-band backscatter, VH polarisation (dB) | `false` |
| `s2-index` | `sensor` | `SENTINEL-2` | Optical spectral index (e.g. NDWI / NDVI) | `false` |
| `s2-boundary` | `sensor` | `SENTINEL-2` | Instantaneous optical waterline at acquisition timestamp | `false` |
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
List of layer descriptors populating the 10 scientific slots (and optional `raster_dem` LiDAR 3D terrain sources).

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
- `GET /api/transects`: GeoJSON `FeatureCollection` of `LineString` shore-normal transects.
- `GET /api/transects/{id}`: Transect geometry plus `profiles[]` (strictly increasing `x_m` in metres, `z_m` in `NAVD88` metres) and separate `boundaries[]` (`type: "radar" | "optical" | "terrain"`).

### 3.6 `GET /api/analysis/{id}`
Physics-informed model output along transect `{id}`. Must declare `"inferred": true` and provide per-point `sigma_m` ($1\sigma$ uncertainty in metres).

### 3.7 `GET /api/environment/latest`
Latest verified NOAA/USACE environmental measurements at Duck Pier (station `8651370`), with `observed_at` UTC timestamps, `units`, `datum`, and `qc_flag`.
