# Project context: NASA Space Apps Challenge 2026 ("Dancing with the SARs")

> Rules and context for AI coding assistants working in this repository. The team's original handoff notes contained preliminary numbers; those are **superseded** by the pipeline results in `VALIDATION_SUMMARY.md` and must not be quoted.

## Status and deadline
- **Event:** NASA International Space Apps Challenge 2026. The team is in India.
- **Final submission is due by midnight on 15 Nov 2026.** Confirm the exact timezone on the submission page.
- **Challenge:** **#5 "Dancing with the SARs".** (The team first chose #8, then switched. Submit under #5.)
- **Brief:** an interactive application using NASA–ISRO NISAR radar data to track and visualise surface change; hypothesise drivers, discuss polarizations, suggest future NISAR applications; open source, user friendly, actionable.
- **Judging:** Influence/Impact, Creativity, Validity, Relevance, Presentation.

## Team
- Five members; Python and Java; no formal remote-sensing background. Everyone must be able to explain the findings in their own words.

## The project
**Question:** when several Earth-observation sensors disagree about a changing coastline, which features does each one actually detect, what really changed, and how confident should we be?

**Site:** Duck, NC (USACE FRF), alongshore y = 700–1190 m; lidar scans matched to NISAR passes on 2026-06-19, 2026-09-29 and 2026-10-16 (exact UTC times in `CITATIONS.md`).

**What is submitted:** a multisensor discrepancy analysis (validation pipeline + app). Not an erosion detector, and not a fused or reconstructed coastline; fusion is future work.

**Results:** read them from `VALIDATION_SUMMARY.md` (generated) or `dist/data.js` (generated). Do not type result numbers into slides, the README or the app by hand.

## Rules
- Every number in the app, report or pitch must come from code or data in this repo. Run `python run_validation.py --skip-download` after any change; it ends with self-checks that must all pass.
- Keep claims at the evidence level the summary assigns (SUPPORTED / PLAUSIBLE / NOT DEMONSTRATED). The tags come from written rules in `src/make_report.py`; do not upgrade them by hand.
- Never merge physically different features (waterline, wet/dry edge, dune toe, contour) into one "coastline".
- Say "beach lowering" or "elevation change", not "erosion". Make no causal storm claims: no wave or storm data is in this repo.
- Detection limits: state pixel sizes (from product metadata); shifts smaller than one pixel are not resolvable.
- Cite every dataset with product or granule ID, UTC time, URL and access date (`CITATIONS.md`, generated).
- No third-party images; our own plots only; follow NASA logo rules; disclose AI use.
- Treat this as a single-site case study; describe transfer to other coasts (e.g. Odisha, Kerala, Puducherry) only as future work.
- Keep a recorded backup demo; make the repo public, add a licence and check every link before submitting.

## Data access (as used by the pipeline)
- **FRF lidar:** `https://chldata.erdc.dren.mil/thredds/dodsC/frf/geomorphology/DEMs/duneLidarDEM/...` (OPeNDAP; no login).
- **Tides:** NOAA CO-OPS API, station 8651370, NAVD88, metric, GMT (no login).
- **Sentinel-2 L2A:** Earth Search on AWS STAC (no login).
- **Sentinel-1 RTC:** Microsoft Planetary Computer STAC (anonymous signing; no login).
- **NISAR L2 GCOV:** NASA Earthdata / ASF via `earthaccess`; needs a free Earthdata Login (`python src/earthdata_login.py`). Only the site window is read over HTTPS range requests.
