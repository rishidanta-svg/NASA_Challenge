# Validation summary: which coastal boundary does each sensor see?

Duck, NC (USACE FRF), alongshore y = 700-1190 m, 50 rows at 10 m spacing; June, late September and October 2026.
Ground truth: FRF tower lidar (QC flag 1). Error = sensor − lidar (+ = sensor further seaward). Tags are assigned by the rules at the end of this page, from the numbers in `outputs/`.

## What we measured
- Three lidar lines per row, kept separate: the **wet/dry edge** (seaward limit of lidar ground returns; FRF removes water, so this is where water/swash begins), the **dune toe** (slope break at the foot of the dune; only where the dune face is in view) and a **fixed 1.50 m NAVD88 contour** (chosen by a coverage rule).
- Sentinel-2 water edges (NDWI, MNDWI). The only tuned setting, the index threshold, is chosen on training rows only (5-fold spatial block cross-validation) and must find an edge on at least 90% of training rows on every date.
- Radar edges: the strongest seaward drop in backscatter after an 11 m smoothing, no tuning (Sentinel-1 VV/VH, NISAR HH/HV).
- Bias, MAE, RMSE, % of rows within one pixel, and 95% block-bootstrap intervals (1000 resamples of 50 m blocks).

## When each image was taken (hours before (−) or after (+) the lidar scan)

| Date | Sentinel-2 | Sentinel-1 | NISAR |
|---|---|---|---|
| 2026-06 | -8.5 h | +118.5 h | -0.6 h |
| 2026-09 | -18.7 h | +132.4 h | -0.3 h |
| 2026-10 | -7.5 h | -0.6 h | +0.3 h |

## Accuracy against the lidar line each sensor is meant to see (all dates pooled)

| Sensor | Lidar line | N rows | Bias (m) | RMSE (m) [95% CI] | Within 1 pixel |
|---|---|---|---|---|---|
| Sentinel-2 NDWI | wet/dry edge | 150 | -2.1 | 5.4 [4.9-5.9] | 93% of 10 m |
| Sentinel-2 MNDWI | wet/dry edge | 150 | -0.2 | 9.4 [8.3-10.5] | 99% of 20 m |
| S2 NDWI + tide correction (EXPERIMENTAL) | wet/dry edge | 150 | -0.0 | 4.0 [3.3-4.6] | 100% of 10 m |
| Sentinel-1 VV | dune toe | 42 | +0.4 | 9.2 [7.9-10.1] | 86% of 10 m |
| Sentinel-1 VH | dune toe | 42 | +2.5 | 11.8 [8.9-12.9] | 86% of 10 m |
| NISAR HH | dune toe | 42 | -4.6 | 17.5 [14.7-20.9] | 33% of 10 m |
| NISAR HV | dune toe | 42 | -3.5 | 23.9 [18.9-26.9] | 29% of 10 m |
| S1 VV + NISAR HH (EXPERIMENTAL) | dune toe | 42 | -2.1 | 9.4 [8.8-9.7] | 76% of 10 m |
| Ablation: S1 VV alone, same rows | dune toe | 42 | +0.4 | 9.2 [7.9-10.1] | 86% of 10 m |

## Findings

1. **SUPPORTED: the beach lowered between June and October.** Median lidar elevation change -0.268 m over 17654 common 1 m cells; 11684 m² lowered by more than 0.1 m (the accuracy bound of QC flag 1). This is 'beach lowering', not shown to be net sand loss.
2. **PLAUSIBLE: Sentinel-2 NDWI marks the lidar wet/dry edge.** Pooled RMSE 5.4 m [4.9-5.9] (per date: 2026-06 3.0 m, 2026-09 2.7 m, 2026-10 8.5 m). Same-row comparison: 2026-06: closest to wet/dry edge; 2026-09: closest to wet/dry edge; 2026-10: closest to 1.5 m contour.
3. **PLAUSIBLE: Sentinel-2 MNDWI marks the lidar wet/dry edge.** Pooled RMSE 9.4 m [8.3-10.5] (per date: 2026-06 12.4 m, 2026-09 3.4 m, 2026-10 10.1 m). Same-row comparison: 2026-06: closest to wet/dry edge; 2026-09: closest to wet/dry edge; 2026-10: closest to 1.5 m contour.
4. **Data-quality note (June Sentinel-2):** open-ocean near-infrared reflectance was 0.085 in June against 0.003 (Sept) and 0.005 (Oct). Bright water like this suggests sun glint or haze, which weakens the water signal; it is the likely reason MNDWI is least accurate in June.
5. **PLAUSIBLE: the Sentinel-1 VV edge marks the dune toe.** Pooled RMSE 9.2 m [7.9-10.1] on 42 rows in 5 alongshore blocks (the dune face is only in view on part of the beach). Same-row comparison: 2026-06: closest to dune toe; 2026-09: closest to 1.5 m contour; 2026-10: closest to dune toe. Independent test: simply assuming the dune toe sits at its typical position is much closer (1.8 m vs 9.2 m on the same 42 rows), so this edge is near the dune but adds no information about where exactly the dune toe is.
6. **PLAUSIBLE: the Sentinel-1 VH edge marks the dune toe.** Pooled RMSE 11.8 m [8.9-12.9] on 42 rows in 5 alongshore blocks (the dune face is only in view on part of the beach). Same-row comparison: 2026-06: closest to dune toe; 2026-09: closest to 1.5 m contour; 2026-10: closest to dune toe.
7. **PLAUSIBLE: the NISAR HH edge marks the dune toe.** Pooled RMSE 17.5 m [14.7-20.9] on 42 rows in 5 alongshore blocks (the dune face is only in view on part of the beach). Same-row comparison: 2026-06: closest to dune toe; 2026-09: closest to 1.5 m contour; 2026-10: closest to dune toe. Independent test: simply assuming the dune toe sits at its typical position is much closer (1.8 m vs 17.5 m on the same 42 rows), so this edge is near the dune but adds no information about where exactly the dune toe is.
8. **PLAUSIBLE: the NISAR HV edge marks the dune toe.** Pooled RMSE 23.9 m [18.9-26.9] on 42 rows in 5 alongshore blocks (the dune face is only in view on part of the beach). Same-row comparison: 2026-06: closest to dune toe; 2026-09: closest to dune toe; 2026-10: closest to dune toe.
9. **SUPPORTED: the Sentinel-1 VV edge is not the waterline.** Against the lidar wet/dry edge: RMSE 31.9 m, bias -25.5 m (landward) pooled; per date RMSE 33.8 m, 23.6 m, 36.7 m.
10. **NOT DEMONSTRATED (mixed): correcting Sentinel-2 for the tide improves the waterline (EXPERIMENTAL; uses the lidar beach slope from training rows, so it is not satellite-only).** The October image was taken when the water was 0.77 m higher than at the lidar scan, and the correction removes most of that month's bias (-8.2 → -2.8 m). Pooled RMSE 5.4 → 4.0 m, but per date: 2026-06: 3.0 → 4.1 m; 2026-09: 2.7 → 4.0 m; 2026-10: 8.5 → 3.8 m — worse on 2026-06, 2026-09.
11. **NOT DEMONSTRATED: after the tide correction, the Sentinel-2 waterline's June-to-October shift matches the retreat of the lidar 1.5 m contour.** Sentinel-2 moved -5.8 m and the contour -7.5 m on the same rows (change error RMSE 2.9 m [2.4-3.5], N = 45). **PLAUSIBLE** for the lidar wet/dry edge, the feature Sentinel-2 matches on most dates: it moved only -0.5 m (change error RMSE 6.0 m). Which of the two the satellite shift reflects is unresolved. Without the tide correction the Sentinel-2 edge moved -10.4 m, so most of the raw shift is tide, not beach. One pair of dates only. **Not confirmed by the independent test:** with the beach slope taken from separate calibration scans instead of the evaluation lidar, the tide-corrected shift is +1.4 m and its change error 9.0 m, no better than assuming no change (8.4 m). The match above depended on the evaluation lidar's own slope.
12. **PLAUSIBLE: the Sentinel-1 VV edge stayed put, like the dune toe.** Median shift -1.5 m vs dune toe -2.0 m on the same 13 rows; but the row-by-row change error is 10.4 m [2.7-16.0], so stability is shown on average, not row by row. As a measurement of dune-toe movement it is worse than simply assuming no change (10.4 m vs 2.6 m on the same 13 rows).
13. **PLAUSIBLE: the Sentinel-1 VH edge stayed put, like the dune toe.** Median shift -0.5 m vs dune toe -2.0 m on the same 13 rows; but the row-by-row change error is 11.5 m [2.6-17.5], so stability is shown on average, not row by row.
14. **PLAUSIBLE: the NISAR HH edge stayed put, like the dune toe.** Median shift +0.0 m vs dune toe -2.0 m on the same 13 rows; but the row-by-row change error is 21.9 m [11.9-26.2], so stability is shown on average, not row by row. As a measurement of dune-toe movement it is worse than simply assuming no change (21.9 m vs 2.6 m on the same 13 rows).
15. **PLAUSIBLE: the NISAR HV edge stayed put, like the dune toe.** Median shift +1.0 m vs dune toe -2.0 m on the same 13 rows; but the row-by-row change error is 26.1 m [18.6-33.7], so stability is shown on average, not row by row.
16. **NISAR ablation — NOT DEMONSTRATED: adding NISAR HH to Sentinel-1 VV improves the dune line (EXPERIMENTAL).** With NISAR RMSE 9.4 m [8.8-9.7]; without NISAR, same rows, 9.2 m [7.9-10.1]. NISAR passes used: 2026-06 descending track 69; 2026-09 ascending track 162; 2026-10 descending track 69. The September pass looks from the opposite direction, which can move a radar edge.
17. **Note — NISAR's edge position depends on which way the satellite looks (cause NOT DEMONSTRATED).** Against the dune toe, the NISAR HH edge sits -10.5 m (2026-06, descending), -10.8 m (2026-10, descending) and +10.4 m (2026-09, ascending). The offset is consistent within one viewing direction and flips sign between directions. Radar viewing geometry on the sloping dune face or a geolocation offset could each cause this; neither was tested. Viewing direction does not explain all of NISAR's larger error: on the descending passes alone NISAR HH RMSE is 21.6 m (2026-06), 12.2 m (2026-10) against Sentinel-1 VV 10.0 m (2026-06), 4.1 m (2026-10).

## Independent test: held-out dates and places, against simple baselines

Each fold holds out one whole date and one 100 m stretch of beach (15 folds). Thresholds, sensor offsets and weights are learned only from other dates and other stretches. The physics uses beach slopes from separate calibration lidar scans (2026-06 slope 0.133, 2026-09 slope 0.075, 2026-10 slope 0.059), tide from the NOAA gauge and waves from the FRF 17 m Waverider; runup is the Stockdon et al. (2006) R2% formula with its published coefficients, nothing tuned. Every method in a group is scored on exactly the same rows.

| Group | Method | N rows | RMSE (m) [95% CI] | RMSE by date (Jun / Sep / Oct) |
|---|---|---|---|---|
| waterline | Typical position (median of training lidar) | 150 | 7.1 [6.4-7.7] | 6.6 / 9.0 / 5.2 |
| waterline | Sentinel-2 NDWI | 150 | 6.1 [5.6-6.6] | 5.4 / 3.1 / 8.5 |
| waterline | Sentinel-2 NDWI + tide (independent slope) | 150 | 3.0 [2.5-3.5] | 2.8 / 3.1 / 3.1 |
| waterline | Sentinel-2 NDWI + tide + wave runup | 150 | 3.4 [2.6-4.2] | 3.5 / 3.6 / 3.2 |
| dune line | Typical position (median of training lidar) | 42 | 1.8 [1.6-2.1] | 2.3 / 1.4 / 1.4 |
| dune line | Sentinel-1 VV | 42 | 9.2 [7.9-10.1] | 10.0 / 11.7 / 4.1 |
| dune line | NISAR HH | 42 | 17.5 [14.7-20.9] | 21.6 / 15.7 / 12.2 |
| dune line | Plain average of S1 VV and NISAR HH | 42 | 9.4 [8.8-9.7] | 9.9 / 10.8 / 7.2 |
| dune line | Sentinel-1 VV, offset-calibrated | 42 | 9.6 [7.8-10.4] | 10.3 / 12.2 / 4.5 |
| dune line | Weighted S1 VV + VH (calibrated) | 42 | 7.8 [5.6-8.9] | 4.9 / 12.0 / 5.8 |
| dune line | Weighted S1 VV + VH + NISAR HH + HV (calibrated) | 42 | 8.6 [6.1-10.0] | 8.3 / 12.0 / 4.3 |
| dune line, NISAR calibratable rows | Typical position (median of training lidar) | 30 | 1.9 [1.6-2.3] | 2.3 / — / 1.4 |
| dune line, NISAR calibratable rows | Sentinel-1 VV, offset-calibrated | 30 | 8.3 [4.4-11.4] | 10.3 / — / 4.5 |
| dune line, NISAR calibratable rows | NISAR HH, offset-calibrated per viewing direction | 30 | 15.0 [10.8-18.3] | 19.1 / — / 6.4 |

### Independent-test findings

1. **SUPPORTED: Sentinel-2 NDWI + tide (independent slope) locates the wet/dry edge better than guessing its typical position.** 3.0 m [2.5-3.5] vs 7.1 m [6.4-7.7] on the same 150 rows; better on every date. Not satellite-only: it also needs the tide gauge and a beach slope from a lidar survey taken days earlier.
2. **NOT DEMONSTRATED (mixed): Sentinel-2 NDWI locates the wet/dry edge better than guessing its typical position.** 6.1 m [5.6-6.6] vs 7.1 m [6.4-7.7] on the same 150 rows; worse on 2026-10.
3. **NOT DEMONSTRATED: adding wave runup physics to the tide correction improves the Sentinel-2 waterline.** With runup 3.4 m [2.6-4.2], tide only 3.0 m [2.5-3.5]; worse on 2026-06, 2026-09, 2026-10. Waves were small on all dates, so runup differences were small.
4. **SUPPORTED: for the dune toe, the typical-position guess beats every radar method.** Typical position 1.8 m [1.6-2.1]; best radar method (weighted Sentinel-1 VV + VH) 7.8 m [5.6-8.9]. The dune toe barely moves along this beach or between dates, while radar edges scatter by several metres from row to row.
5. **NISAR ablation (independent test) — NOT DEMONSTRATED: adding calibrated NISAR improves the dune line.** With NISAR 8.6 m [6.1-10.0], without 7.8 m [5.6-8.9]; worse on 2026-06, 2026-09.
6. **NOT DEMONSTRATED: offset-calibrated NISAR HH locates the dune line better than calibrated Sentinel-1 VV.** 15.0 m vs 8.3 m on the 30 rows where NISAR could be calibrated (its offset depends on viewing direction, and only one pass looks from the ascending side, so September cannot be calibrated from other dates).
7. **NOT DEMONSTRATED: Sentinel-2 NDWI + tide + wave runup measures the June-to-October movement of the lidar wet/dry edge better than assuming no change.** Change error 3.3 m [2.6-4.1] vs no change 5.0 m [3.5-6.2] on the same 50 rows (lidar median shift -0.5 m, method -0.7 m).
8. **NOT DEMONSTRATED: Sentinel-2 NDWI + tide + wave runup measures the June-to-October movement of the lidar contour better than assuming no change.** Change error 6.6 m [5.7-7.3] vs no change 8.4 m [6.2-10.0] on the same 45 rows (lidar median shift -7.5 m, method -1.6 m).
9. **NOT DEMONSTRATED: Weighted S1 VV + VH (calibrated) measures the June-to-October movement of the lidar dune toe better than assuming no change.** Change error 3.9 m [3.2-4.5] vs no change 2.6 m [2.2-3.1] on the same 13 rows (lidar median shift -2.0 m, method -4.7 m).

## Where this could be wrong
- **The lidar never reaches the still-water line** (FRF removes water returns), so the wet/dry edge depends on FRF's automatic filter and on waves at scan time.
- **Timing:** see the timing table; tide and waves differ between each image and the lidar scan. Sentinel-1 scenes all come from one orbit (relative orbit 106, ascending) to keep the viewing direction constant, which puts the June and September scenes 4.9 and 5.5 days after the lidar.
- **Image quality:** the June Sentinel-2 water is unusually bright (finding on data quality).
- **Pixel size:** 10 m (Sentinel-2 NDWI, Sentinel-1) and 20 m (MNDWI); differences smaller than one pixel are not resolvable.
- **Geolocation:** each product is used on its own map grid with no extra co-registration.
- **Edge rules:** a different smoothing, threshold or dune-toe rule would move the numbers by metres.
- **Small samples:** the dune toe is visible on a minority of rows, so its intervals rest on few alongshore blocks; three dates; one ~500 m site.
- **The tide correction uses lidar** (beach slope), so it is a physics check, not a satellite-only method.
- **Tidal datum epoch** for MHW is 1983-2001.
- **Location errors matter:** shifting every edge by 5 m changes pooled RMSE to S2 NDWI 8.7/5.8 m (from 5.4 m); S1 VV 10.3/10.7 m (from 9.2 m); NISAR HH 19.4/16.8 m (from 17.5 m) for a 5 m landward/seaward shift, so a geolocation error of half a pixel is comparable to the differences between methods.
- **NISAR data are provisional** (NISAR_L2_GCOV_PROVISIONAL_V1). A newer NISAR_L2_GCOV_V1 collection exists but, when searched, held no granule for these dates over the site.

## How this transfers
The method needs a reference elevation survey, a tide gauge and the satellite images, so it can be repeated wherever a survey overlaps a NISAR pass, for example on eroding Indian coasts such as Odisha, Kerala or Puducherry. That is future work.

## How claims are tagged

- **Beach lowering**: SUPPORTED if the median lidar elevation change is lower than −(lidar accuracy bound for QC flag 1, 0.1 m per the FRF metadata).
- **Which feature a sensor matches** (compared on the same rows for all three lidar lines): SUPPORTED if that lidar line has the lowest RMSE on every date and the pooled RMSE is within one pixel; PLAUSIBLE if it has the lowest pooled RMSE but not on every date, or pooled RMSE exceeds one pixel; otherwise NOT DEMONSTRATED.
- **A sensor does NOT track a feature**: SUPPORTED if RMSE exceeds one pixel on every date and the pooled bias exceeds one pixel.
- **Method A is better than method B**: SUPPORTED if A has lower RMSE on every date and the pooled 95% intervals do not overlap; NOT DEMONSTRATED (mixed) if A is better pooled but worse on some date; otherwise NOT DEMONSTRATED.
- **Change claims** use one pair of dates only, so the best possible tag is PLAUSIBLE: given when the June-to-October change error (RMSE, upper 95% bound) is within one pixel, or when both median shifts are smaller than one pixel; otherwise NOT DEMONSTRATED.
- Differences between methods that are both smaller than one pixel are reported but are not treated as resolvable.
- **Independent test**: each fold holds out one whole date and one 100 m stretch of beach; everything tuned or calibrated uses only other dates and other stretches, and no evaluation lidar enters any method. A method beats a simple baseline only under the 'method A is better than method B' rule above. A change beats 'no change' (PLAUSIBLE at best, one pair of dates) only if its upper 95% bound is below the lower bound of 'no change'. A main-analysis finding that the independent test does not confirm is downgraded to NOT DEMONSTRATED or carries a note.

## Self-checks

| Check | Status | Detail |
|---|---|---|
| Three lidar scans loaded at the document's matched times | PASS | 2026-06: 2026-06-19T00:31:03 UTC; 2026-09: 2026-09-29T10:33:03 UTC; 2026-10: 2026-10-16T23:33:04 UTC |
| All lidar scans QC flag 1 | PASS | flags [1, 1, 1], max RMS reflector error 0.097 m |
| Median Jun->Oct lidar change recomputed independently | PASS | -0.268 m over 17654 common 1 m cells (reported as computed) |
| NISAR granule IDs match the team's document | PASS | 2026-06: G4250721321-ASF, 2026-09: G4331248374-ASF, 2026-10: G4376256706-ASF |
| Sentinel-1/2 product IDs agree with their acquisition dates and are used for the right date | PASS | all consistent |
| S2 thresholds independently recomputed from training folds only, and applied to the held-out fold | PASS | match for all 5 folds x 2 indices; folds: 0: y 700-790, 1: y 800-890, 2: y 900-990, 3: y 1000-1090, 4: y 1100-1190 |
| FRF transform fitted to FRF's own lat/lon | PASS | max residual 0.003 m; FRF x-axis azimuth 72.30 deg in UTM 18N (handoff: 69.97 deg from NC State Plane north; differs by the grid convergence between the two projections) |
| Units: lidar boundaries inside the lidar x-range (m); datum NAVD88 | PASS | x 62-103 m within grid 40-169 m; NAVD88 (geoid12b) |
| Units: satellite times are UTC | PASS | 6 timestamps end in Z |
| Re-running the scoring reproduces identical outputs | PASS | byte-identical: metrics.csv, sensor_boundaries.csv, change_metrics.csv, matrix_same_rows.csv |
| Every number in the summary's results table matches metrics.csv | PASS | 9 rows checked |
| Physics uses separate calibration lidar scans (never the evaluated scans), all QC flag 1 | PASS | 2026-06: 2026-06-15 19:31:04 (3.2 days before); 2026-09: 2026-09-22 10:33:03 (7.0 days before); 2026-10: 2026-10-09 23:33:04 (7.0 days before) |
| Independent test folds exclude the held-out date and place (baseline recomputed for all 15 folds x 2 groups) | PASS | all folds match |
| Web app (dist/data.js) shows the same accuracy and lowering numbers as the CSVs | PASS | 7 sensors, 26 claims, 50 rows checked |

Figures: `outputs/figures/` (PNG and interactive HTML). Tables: `outputs/*.csv`. Sources: `CITATIONS.md`.
