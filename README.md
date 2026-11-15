# Poltergeist — coastal observatory

Integrated map-first UI, verified multisensor observations, optical tide/setup corrections and independently evaluated NISAR experiments for Duck, North Carolina. Research tool; not an operational erosion forecast.

## Run locally

Use Python 3.11 and Node.js 22 or newer:

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm --prefix frontend ci
.venv/bin/python scripts/run_local.py
```

On Windows use `.venv\Scripts\python.exe` in place of `.venv/bin/python`. Keep that terminal open: the UI and API are local processes, not a hosted service. Open http://localhost:5173. If a port is occupied use `--api-port 8015 --web-port 5175`; the launcher connects the matching API/CORS settings automatically. It never installs dependencies or kills existing services.

The active UI is `frontend/`. The separate historical validation viewer in root `dist/` and the older prototype in `legacy/` remain for provenance; neither is the integrated map application.

## What is connected

- 28-acquisition unified data with 45 checksummed release assets and acquisition-matched environment records.
- Real satellite and LiDAR layers, measured 2D/3D terrain, profile plots, survey comparison and exact acquisition metadata.
- Optical NDWI/MNDWI, tide-only correction and explicitly experimental mean-wave setup.
- Exploratory NISAR HH candidates with failed shoreline comparability clearly labelled.
- 168-cell buffered spatial elevation-change ablation, including same-row zero-change and training-mean baselines.
- Current Findings separates observations, exploratory experiments and archived models. Available overlays are exposed under Layers → More satellite comparisons.

NISAR has not demonstrated added value in the tested terrain model; C increases RMSE versus B. Classification, reliable prediction intervals and deployment as an improved terrain model remain withheld. Main's three-date historical validation is separate from the current June–October map experiment. See [final integration status](docs/INTEGRATION_STATUS.md).

## Verify

```sh
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python physics-data-foundation/validate_collection.py --processed-only --output data/processed/verified/unified
.venv/bin/python run_validation.py --skip-download --skip-png
npm --prefix frontend run build
```

The numerical pipeline refreshes summaries, citations and tables. `--skip-png` retains existing PNGs when Chrome/Kaleido image export is unavailable; HTML figures are regenerated. Source reacquisition requires Earthdata credentials and network access; offline scoring uses committed processed inputs.

Frontend contract tests: in `frontend/` run `POLTERGEIST_PYTHON=/absolute/path/to/.venv/bin/python npm test`. Ordinary `npm test` runs unit tests and skips only the Python-backed contract suite when its interpreter is not configured. Browser tests: build for the desired API, then `POLTERGEIST_PYTHON=/absolute/path/to/.venv/bin/python npm run e2e` (Chrome required).

## Data and science references

- [Current physics workflow](docs/duck-physics.md)
- [NISAR methods, results and withholding](docs/duck-nisar.md)
- [Dataset handoff](physics-data-foundation/HANDOFF.md)
- [Reproduction and audit](docs/REPRODUCTION.md)
- [Historical independent validation](VALIDATION_SUMMARY.md)

## Production hosting

Option A — **Single container (recommended)**: The root `Dockerfile` builds `frontend/dist/` with same-origin API routes (`VITE_API_BASE_URL=""`), installs `requirements-api.txt`, and runs `uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-8000}` with `GET /health`. When `frontend/dist/index.html` is present, FastAPI serves both the compiled SPA and `/api/*` from the same origin.

Option B — **Separate frontend & API**: Host the FastAPI backend (`uvicorn backend.app:app`) with `POLTERGEIST_CORS_ORIGINS=https://your-frontend-origin`, build the UI with `VITE_API_BASE_URL=https://your-api-host npm --prefix frontend run build`, and serve `frontend/dist/`. Do not deploy the historical root `dist/` archive. Original source-environment pins are retained in `legacy/requirements-science-verified.txt`; the integrated install uses the compatible API/validation stack above.
