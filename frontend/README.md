# POLTERGEIST — Duck FRF 2D + 3D Coastal Map & Visualization Frontend

Interactive 2D and 3D scientific coastal workstation for **Duck FRF, North Carolina** (`36.183704°–36.188260° N`, `−75.753384° to −75.750335° W`, FRF `y = 700–1190 m`), built with **React 18**, **TypeScript**, and **MapLibre GL JS**.

## Free Mapping & Environmental Stack
- **MapLibre GL JS v5**: 2D and 3D WebGL map engine (`EPSG:3857` display, `EPSG:32618` analysis CRS, USACE FRF local coordinate transform).
- **OpenFreeMap**: Free vector basemap styles (`liberty`, `positron`, `dark`, `fiord`) with automatic preservation of scientific overlays on style changes.
- **AWS Terrain Tiles (Terrarium)**: `https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png` (`raster-dem`, `tileSize: 256`, `encoding: "terrarium"`) for 2D hillshading, client-side elevation contours (`maplibre-contour`), regional elevation sampling, and 3D terrain relief (`1×` default vertical exaggeration).
- **Live NOAA CO-OPS Station 8651370 (Duck, NC)**: Real, timestamped water level (`NAVD88`), wind speed/gust/direction, air temperature, water temperature, barometric pressure, and tide predictions fetched directly until FastAPI `/api/environment/latest` is online.

## Quick Start

```bash
# Node 22 LTS is installed locally at ~/.local/node/bin
export PATH="$HOME/.local/node/bin:$PATH"

cd frontend
npm run dev         # Start development server at http://localhost:5173
npm run typecheck   # TypeScript strict check
npm test            # Vitest unit test suite (FRF transforms, Terrarium, Zod schemas, API client)
npm run build       # Production bundle in frontend/dist/
npm run e2e         # Playwright E2E browser verification (2D + 3D + NOAA)
```

## FastAPI Integration Contract
See [`../docs/frontend-api-contract.md`](../docs/frontend-api-contract.md) for the full endpoint and schema specification (`VITE_API_BASE_URL`, default `http://localhost:8000`).
