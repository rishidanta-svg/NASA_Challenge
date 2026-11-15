# Review of the previous package (`nasa-challenge-verification.zip`, Gemini version)

Reviewed 15 Nov 2026. Every claim below was checked against the files and the data; the evidence is given for each. Severity reflects the risk to judging (Validity, Presentation) and to the team's credibility.

## What the package actually contained

- `src/`, `run_validation.py`, `outputs/` and `data/processed/` are a **copy of the team's validation pipeline taken at 10:53, before NISAR was working**. Every CSV and figure is byte-identical to that run; `outputs/run_flags.json` says `"have_nisar": false`.
- `VALIDATION_SUMMARY.md` and `CITATIONS.md` are unedited outputs of that same stale run (regenerating them from the zip's CSVs reproduces them exactly).
- Gemini's own additions: `README.md`, `CLAUDE.md`, the web app in `dist/` and `outputs/littoral_profiles_duck_frf.json`.

## Critical

| # | Mistake | Evidence | Fix in this package |
|---|---|---|---|
| 1 | **The submission had no NISAR results**, although the challenge is about NISAR. | `run_flags.json`: `have_nisar: false`; summary finding: "NOT YET RUN"; no `nisar_profiles.nc` in `data/processed/`. | NISAR HH/HV for all three passes (June, September, October) are scored, with the ablation. 12/12 self-checks pass. |
| 2 | **The shipped NISAR code does not work.** The README says it is "implemented and verified syntactically", which only proves it parses. | `src/nisar.py` uses `earthaccess.open()`, whose file-size probe fails on ASF's redirect. Running it raised `FileNotFoundError` on the June granule (reproduced). | Replaced with an HTTPS range-request reader. It was run: about 21 MB is read from each ~5 GB granule; EPSG and pixel size are read from the files. |
| 3 | **The app showed made-up data by default, named after real sensors.** | `app.js` draws a synthetic coastline, a "NISAR · L-band HH / HV" layer made of seeded random rectangles (`rand()`, `seed=9`), a random "Elevation change" layer, a pier that is not surveyed, and profiles from a formula (`height()`) with invented boundaries (`radar: 39+i*2`, `waterJune: 92-i`, `waterOctober: 85-i`). | Every synthetic element is removed. The map is the real lidar elevation change (2 m cells); profiles and edges are real. |
| 4 | **The real data was hidden behind a manual import.** Judges opening the app would only ever see the made-up version. | The Duck profiles appear only after the user clicks Import and picks `outputs/littoral_profiles_duck_frf.json`. | The data is bundled (`dist/data.js`) and loads on start, including when `index.html` is opened directly from disk (tested with headless Chrome). |
| 5 | **The "RADAR" line mixed two dates and named no sensor.** | Each JSON transect has one `radar` value: the average of the June and October Sentinel-1 VV edges (y = 1150: (68.5 + 58.0) / 2 = 63.25). That hides differences of up to 10.5 m between dates. It was shown on both profiles as "Radar transition", next to a "NISAR" layer. | Separate June, September and October edges for every sensor (S2 NDWI/MNDWI, S1 VV/VH, NISAR HH/HV), each labelled. |
| 6 | **`CLAUDE.md` still held superseded numbers and causal wording**, and the README linked it as "Evidence Rules". | It listed 4,607 m², x ≈ 60 m, 98 → 86 m, radar transition 80–85 m, ρ ≈ 0.07 and Hs 4.29 m. None of these is produced by the code in the package, and several contradict it (pipeline: 11,684 m² at a 0.1 m threshold; NISAR HH edge median 52–55 m on the descending passes). The pitch said "after a nor'easter" (causal) and "because it's tracking the dune" (only PLAUSIBLE). | Rewritten: the rules are kept and the superseded numbers removed. Results must be read from the generated summary. |

## High

| # | Mistake | Evidence | Fix |
|---|---|---|---|
| 7 | **The README cherry-picks results.** | It says the tide correction "shifts pooled RMSE to 4.0 m" but omits that it is worse on 2 of 3 dates (tag: NOT DEMONSTRATED (mixed)). It says the radar edge and dune toe "moved less than one 10 m pixel" but omits the 10.4 m row-by-row change error. It also writes "SUPPORTED / PLAUSIBLE" as one tag. | The README carries no result numbers; it points to the generated summary and the app, where each claim keeps its rule-based tag. |
| 8 | **The README calls the app a "coastal reconstruction" UI.** | "First UI release for Duck coastal reconstruction." The project rules say reconstruction and fusion are future work and must not be claimed. | Removed. |
| 9 | **Hand-typed result numbers in the README** go stale on any re-run. | For example "10 PASS, 1 NOT RUN", already wrong once NISAR runs. | Removed; the numbers live only in generated files. |
| 10 | **No `requirements.txt`**, so the documented `python run_validation.py` fails on a clean machine. | There was no dependency list. The login steps were also in a confusing order: "save to `~/.netrc`, then run the login script". | Added `requirements.txt` with the exact versions used, plus virtual-environment setup steps. |
| 11 | **The Timeline and Evidence pages were placeholders**, although the same zip had the real data. | Timeline cards read "PLANNED RECORD"; the dataset register said "Awaiting data" for all four sources. | The Timeline lists all 12 real acquisitions with UTC time, hours from the lidar scan and the water level at that moment. Sources lists real product IDs and the caveats. |
| 12 | **Two required screens were missing.** | The project brief lists "What each sensor actually sees" and "Can we trust this boundary?"; neither existed. | Added the "Sensors & trust" page: an accuracy table and all 17 findings with tags, both generated from the pipeline, with the tagging rules shown. |
| 13 | **Optical water lines were drawn on the lidar profile with no timing context.** | Sentinel-2 was imaged 7.5–8.5 h before the lidar scan; in October the water was 0.77 m higher. Drawn as "OCT WATER" on the lidar profile, it suggests the two were taken at the same moment. | The Timeline shows each image's time and water level; the claims explain the tide effect. |
| 14 | **Profile lines bridged gaps in the lidar data.** | The JSON points have x-gaps of up to 6 m that were drawn as continuous lines. | Lines break where the lidar has no data. |
| 15 | **No lidar reference lines in the app.** Nothing in the UI showed what the satellites are scored against, and two of the five chosen transects (y = 750 and 1150 m) have no measurable dune toe. | The JSON had no dune toe and no wet/dry edge. | Lidar dune toe, wet/dry edge and contour are shown on the map and the profile for all 50 rows. The app starts on the row nearest y = 950 m that has a dune toe on both dates. |

## Medium and low

| # | Mistake | Fix |
|---|---|---|
| 16 | `outputs/littoral_profiles_duck_frf.json` had no generating script, so it was not reproducible. | Replaced by `dist/data.js`, written by `src/export_app_data.py` on every run. A new self-check confirms the app's numbers equal the CSVs. |
| 17 | Compiled `__pycache__/*.pyc` files shipped in the zip. | Excluded. |
| 18 | Unverifiable test claims ("Browser checks confirmed ..."), alongside an admission that mobile and file import were never tested. | The app was tested here at desktop and phone width (no sideways scrolling) and from `file://`. |
| 19 | SVG chart text at 6.5–8 px, unreadable on a projector. | Minimum 10 px. |
| 20 | Import and export of "unverified" user data inside a validation app invites showing data that was never checked. | Removed. The app shows only pipeline output. |
| 21 | No licence, although the challenge asks for open source. | Flagged in the README for the team to choose; not decided on the team's behalf. |

## Also fixed while rebuilding (not Gemini's mistakes)

- The image renderer (kaleido) has an intermittent startup race that made clean runs fail. Graphs now use one persistent renderer, retry inside the process, and `run_validation.py` re-runs the graph steps in a fresh process up to 3 times. During the final check the race occurred once and the retry recovered.
- The tide download now covers the two Sentinel-1 dates (23 June, 4 October), so the timeline shows the water level for every image. This does not change any score.

## How this package was checked

- Full pipeline run with fresh downloads (lidar, tide, Sentinel-1, Sentinel-2, NISAR), then a run from the included data: **12/12 self-checks PASS** (see `outputs/self_checks.csv`).
- Every result CSV is byte-identical to the separately verified run.
- App: no console errors; map clicks, date switching, toggles and all four pages work at 1440 × 900 and 375 × 812; it also loads from `file://`.
