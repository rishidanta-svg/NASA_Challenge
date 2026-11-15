# Poltergeist final experience

This release builds on the integrated team platform at `1ce2239` without changing model predictions or input data.

- Task-first Explore panel: a measured study result, direct change-map action, two-survey comparison, profile shortcut, and plain-language guidance.
- The change-map action activates the actual October-minus-June LiDAR overlay. Comparison restricts the quick choices to epoch-specific products and explains that the background image is not survey-dated.
- Printable self-contained HTML study brief with survey provenance, horizontal optical validation, separately labelled vertical NISAR errors, and scope limits. Print from the downloaded brief to save a PDF.
- CSV export of the selected measured profile, with explicit FRF coordinates, survey times, vertical datum and empty missing returns. Measured change is never interpolated across gaps.
- Fixed schema stripping of `rmse_reduction_percent`; the visible optical improvement is derived from the matched raw and corrected RMSE values.
- Corrected MHW datum (0.359 m NAVD88), ground-based LiDAR description and timing/frequency confounding. EO instrument explanations are in About.
- Quieter layer catalog and inspector, monochrome UI badges, small-screen layout, keyboard controls, retry state, graphics error boundary and lazy map loading. Initial application JS is approximately 441 kB before compression; MapLibre loads separately.
- Fixed production map canvas sizing when MapLibre CSS loads after application styles.
- Added HTTPX SOCKS support for proxy environments. Survey terrain failures switch to explicitly labelled regional terrain; regional terrain failures return to 2D. Neither fallback invents beach heights. External terrain/imagery still depend on upstream availability. Local survey terrain requests timed out at the regional AWS background service during release checking.

## Verification

- Frontend: 20 checks passed, including real FastAPI response contracts and scientific export checks.
- Backend: 45 tests passed.
- Production build and `git diff --check` passed.
- Browser checks used the compiled application served by FastAPI at the same origin, not only Vite: Explore, measured layer selection, comparison, findings, profile controls, downloaded study brief, terrain fallback and phone layout.
- The downloaded brief was checked for measured mean -0.31 m, optical errors 7.42/3.73 m, NISAR ablation errors 0.2549/0.2582 m, and original survey identifiers.

## Run the packaged application

```sh
VITE_API_BASE_URL= npm --prefix frontend run build
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Install `requirements-api.txt` in a Python 3.11 environment and run `npm ci` in `frontend/` first. Open http://localhost:8000. An empty build-time API base uses the same server as the UI. The existing Dockerfile packages both components for an HTTPS application host. GitHub source publication alone does not deploy the Python application.
