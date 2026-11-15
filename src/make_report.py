"""Write CITATIONS.md and VALIDATION_SUMMARY.md.

Every number is read from CSVs produced by the pipeline, and every
SUPPORTED / PLAUSIBLE / NOT DEMONSTRATED tag is assigned by the written rules in
TAG_RULES below (also printed in the summary), never chosen by hand.
"""
from pathlib import Path
import os
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("SARS_OUT", ROOT / "outputs"))
PROC = ROOT / "data" / "processed"
ACCESS = "2026-11-15"
DATES = ["2026-06", "2026-09", "2026-10"]
BN = {"B1_wetdry": "wet/dry edge", "B2_dunetoe": "dune toe", "B3_contour": "contour"}
NAME = {"S2_NDWI": "Sentinel-2 NDWI", "S2_MNDWI": "Sentinel-2 MNDWI", "S1_VV": "Sentinel-1 VV",
        "S1_VH": "Sentinel-1 VH", "NISAR_HH": "NISAR HH", "NISAR_HV": "NISAR HV",
        "EXP_tideaware_S2": "S2 NDWI + tide correction (EXPERIMENTAL)",
        "EXP_radar_S1VV+NISARHH": "S1 VV + NISAR HH (EXPERIMENTAL)",
        "ABL_radar_S1VV_only": "Ablation: S1 VV alone, same rows"}

TAG_RULES = [
    "**Beach lowering**: SUPPORTED if the median lidar elevation change is lower than −(lidar accuracy bound for QC flag 1, 0.1 m per the FRF metadata).",
    "**Which feature a sensor matches** (compared on the same rows for all three lidar lines): "
    "SUPPORTED if that lidar line has the lowest RMSE on every date and the pooled RMSE is within one pixel; "
    "PLAUSIBLE if it has the lowest pooled RMSE but not on every date, or pooled RMSE exceeds one pixel; otherwise NOT DEMONSTRATED.",
    "**A sensor does NOT track a feature**: SUPPORTED if RMSE exceeds one pixel on every date and the pooled bias exceeds one pixel.",
    "**Method A is better than method B**: SUPPORTED if A has lower RMSE on every date and the pooled 95% intervals do not overlap; "
    "NOT DEMONSTRATED (mixed) if A is better pooled but worse on some date; otherwise NOT DEMONSTRATED.",
    "**Change claims** use one pair of dates only, so the best possible tag is PLAUSIBLE: given when the June-to-October change error "
    "(RMSE, upper 95% bound) is within one pixel, or when both median shifts are smaller than one pixel; otherwise NOT DEMONSTRATED.",
    "Differences between methods that are both smaller than one pixel are reported but are not treated as resolvable.",
]


# ------------------------------------------------------------------ helpers
def g(M, p, b, d="pooled"):
    r = M[(M["product"] == p) & (M.lidar_boundary == b) & (M.date == d)]
    return r.iloc[0] if len(r) and np.isfinite(r.iloc[0].RMSE_m) else None


def f1(v):
    return f"{v:.1f}"


def tag_feature_match(S, p, b):
    s = S[S["product"] == p]
    if s.empty:
        return "NOT DEMONSTRATED", ""
    best = {d: s[s.date == d].set_index("lidar_boundary").RMSE_m.idxmin() for d in DATES + ["pooled"]
            if s[s.date == d].RMSE_m.notna().any()}
    pooled = s[(s.date == "pooled") & (s.lidar_boundary == b)].iloc[0]
    every = all(best.get(d) == b for d in DATES if d in best)
    detail = "; ".join(f"{d}: closest to {BN[best[d]]}" for d in DATES if d in best)
    if every and pooled.RMSE_m <= pooled.pixel_m:
        return "SUPPORTED", detail
    if best.get("pooled") == b:
        return "PLAUSIBLE", detail
    return "NOT DEMONSTRATED", detail


def tag_not_tracking(M, p, b):
    rs = [g(M, p, b, d) for d in DATES]
    pooled = g(M, p, b)
    if pooled is None or any(r is None for r in rs):
        return "NOT DEMONSTRATED"
    ok = all(r.RMSE_m > r.pixel_m for r in rs) and abs(pooled.bias_m) > pooled.pixel_m
    return "SUPPORTED" if ok else "NOT DEMONSTRATED"


def tag_better(M, a, b, tgt):
    A = [g(M, a, tgt, d) for d in DATES]; B = [g(M, b, tgt, d) for d in DATES]
    pa, pb = g(M, a, tgt), g(M, b, tgt)
    if pa is None or pb is None:
        return "NOT DEMONSTRATED", []
    per = [(d, x.RMSE_m < y.RMSE_m) for d, x, y in zip(DATES, A, B) if x is not None and y is not None]
    worse = [d for d, ok in per if not ok]
    no_overlap = pa.RMSE_hi < pb.RMSE_lo
    if not worse and no_overlap:
        return "SUPPORTED", worse
    if pa.RMSE_m < pb.RMSE_m and worse:
        return "NOT DEMONSTRATED (mixed)", worse
    return "NOT DEMONSTRATED", worse


def tag_change(c):
    if c is None or c.N < 5:
        return "NOT DEMONSTRATED"
    if c.RMSE_hi <= c.pixel_m:
        return "PLAUSIBLE"
    if abs(c.median_sensor_shift_m) < c.pixel_m and abs(c.median_lidar_shift_m) < c.pixel_m:
        return "PLAUSIBLE"
    return "NOT DEMONSTRATED"


def hours(a, b):
    ta = pd.Timestamp(a); tb = pd.Timestamp(b)
    ta = ta.tz_localize(None) if ta.tzinfo else ta
    tb = tb.tz_localize(None) if tb.tzinfo else tb
    return (tb - ta).total_seconds() / 3600


# ------------------------------------------------------------------ citations
def citations():
    lm = pd.read_csv(PROC / "lidar_scan_meta.csv")
    s2 = pd.read_csv(PROC / "s2_meta.csv")
    s1 = pd.read_csv(PROC / "s1_meta.csv")
    L = ["# Data citations", "", f"All data accessed {ACCESS}. All times UTC.", "",
         "| Dataset | Product / granule ID | Acquisition (UTC) | URL |", "|---|---|---|---|"]
    for r in lm.itertuples():
        L.append(f"| USACE FRF dune lidar DEM (duneLidarDEM, hourly) | {Path(r.opendap_url).name}, coregQCFlag {int(r.coregQCFlag)} | {r.scan_utc} | {r.opendap_url} |")
    nm = PROC / "nisar_meta.csv"
    if nm.exists():
        for r in pd.read_csv(nm).itertuples():
            L.append(f"| NASA-ISRO NISAR L2 GCOV (provisional), HH/HV | {r.concept_id} ({r.granule_ur}) | {r.begin_utc} to {r.end_utc} | {r.url} |")
    else:
        for cid in ["G4250721321-ASF", "G4331248374-ASF", "G4376256706-ASF"]:
            L.append(f"| NASA-ISRO NISAR L2 GCOV (provisional), HH/HV | {cid} | see CMR record | https://cmr.earthdata.nasa.gov/search/concepts/{cid} (not yet downloaded) |")
    for r in s1.itertuples():
        L.append(f"| Copernicus Sentinel-1 RTC (Microsoft Planetary Computer), VV/VH, relative orbit {r.relative_orbit} {r.orbit_state} | {r.item_id} | {r.acquisition_utc} | {r.url} |")
    for r in s2.itertuples():
        L.append(f"| Copernicus Sentinel-2 L2A (Earth Search on AWS), processing offset applied: {r.boa_offset_applied} | {r.item_id} | {r.acquisition_utc} | {r.self_href} |")
    L += ["| NOAA CO-OPS water level, station 8651370 Duck NC (6-min, NAVD88, metric) | product=water_level | 2026-06-18/19, 2026-09-28/29, 2026-10-16/17 | https://api.tidesandcurrents.noaa.gov/api/prod/datagetter |",
          "| NOAA CO-OPS tidal datums, station 8651370 (epoch 1983-2001) | MHW, NAVD88 | n/a | https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/8651370/datums.json |",
          "", "Contains modified Copernicus Sentinel data (2026). Lidar courtesy of the USACE Field Research Facility, Duck NC.",
          "Lidar QC definitions (coregQCFlag 1: plane-matching co-registration, RMS reflector error < 0.1 m, assessment-plane offsets < 0.1 m) are from the FRF file metadata.",
          "AI use: analysis code was written with assistance from Claude (Anthropic) and must be reviewed and understood by the team."]
    (ROOT / "CITATIONS.md").write_text("\n".join(L) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ summary
def summary():
    M = pd.read_csv(OUT / "metrics.csv")
    S = pd.read_csv(OUT / "matrix_same_rows.csv")
    C = pd.read_csv(OUT / "change_metrics.csv")
    s = pd.read_csv(OUT / "lidar_sanity.csv", index_col=0)["value"]
    tide = pd.read_csv(OUT / "tide_correction_inputs.csv").set_index("date")
    lb = pd.read_csv(OUT / "lidar_boundaries.csv")
    s2m = pd.read_csv(PROC / "s2_meta.csv").set_index("date_key")
    s1m = pd.read_csv(PROC / "s1_meta.csv").set_index("date_key")
    lm = pd.read_csv(PROC / "lidar_scan_meta.csv").set_index("date_key")
    sc_path = OUT / "self_checks.csv"
    have_nisar = (PROC / "nisar_meta.csv").exists()
    z3 = lb.B3_contour_z.iloc[0]
    BN["B3_contour"] = f"{z3:.1f} m contour"
    ch = lambda p, b: (lambda r: r.iloc[0] if len(r) else None)(C[(C["product"] == p) & (C.lidar_boundary == b)])

    radar = ["S1_VV", "S1_VH"] + (["NISAR_HH", "NISAR_HV"] if have_nisar else [])
    L = ["# Validation summary: which coastal boundary does each sensor see?", "",
         "Duck, NC (USACE FRF), alongshore y = 700-1190 m, 50 rows at 10 m spacing; June, late September and October 2026.",
         "Ground truth: FRF tower lidar (QC flag 1). Error = sensor − lidar (+ = sensor further seaward). "
         "Tags are assigned by the rules at the end of this page, from the numbers in `outputs/`.", "",
         "## What we measured",
         f"- Three lidar lines per row, kept separate: the **wet/dry edge** (seaward limit of lidar ground returns; FRF removes water, so this is where water/swash begins), "
         f"the **dune toe** (slope break at the foot of the dune; only where the dune face is in view) and a **fixed {z3:.2f} m NAVD88 contour** (chosen by a coverage rule).",
         "- Sentinel-2 water edges (NDWI, MNDWI). The only tuned setting, the index threshold, is chosen on training rows only (5-fold spatial block cross-validation) "
         "and must find an edge on at least 90% of training rows on every date.",
         "- Radar edges: the strongest seaward drop in backscatter after an 11 m smoothing, no tuning (Sentinel-1 VV/VH"
         + (", NISAR HH/HV)." if have_nisar else "). NISAR: not yet run, see below."),
         "- Bias, MAE, RMSE, % of rows within one pixel, and 95% block-bootstrap intervals (1000 resamples of 50 m blocks).", "",
         "## When each image was taken (hours before (−) or after (+) the lidar scan)", "",
         "| Date | Sentinel-2 | Sentinel-1 |" + (" NISAR |" if have_nisar else ""), "|---|---|---|" + ("---|" if have_nisar else "")]
    nmeta = pd.read_csv(PROC / "nisar_meta.csv").set_index("date_key") if have_nisar else None
    for d in DATES:
        row = f"| {d} | {hours(lm.loc[d,'scan_utc'], s2m.loc[d,'acquisition_utc']):+.1f} h | {hours(lm.loc[d,'scan_utc'], s1m.loc[d,'acquisition_utc']):+.1f} h |"
        if have_nisar:
            row += (f" {hours(lm.loc[d,'scan_utc'], nmeta.loc[d,'begin_utc']):+.1f} h |" if d in nmeta.index else " none |")
        L.append(row)

    L += ["", "## Accuracy against the lidar line each sensor is meant to see (all dates pooled)", "",
          "| Sensor | Lidar line | N rows | Bias (m) | RMSE (m) [95% CI] | Within 1 pixel |", "|---|---|---|---|---|---|"]
    table = [(p, "B1_wetdry") for p in ["S2_NDWI", "S2_MNDWI", "EXP_tideaware_S2"]] + [(p, "B2_dunetoe") for p in radar]
    if have_nisar:
        table += [("EXP_radar_S1VV+NISARHH", "B2_dunetoe"), ("ABL_radar_S1VV_only", "B2_dunetoe")]
    for p, b in table:
        r = g(M, p, b)
        if r is None:
            continue
        L.append(f"| {NAME[p]} | {BN[b]} | {int(r.N)} | {r.bias_m:+.1f} | {f1(r.RMSE_m)} [{f1(r.RMSE_lo)}-{f1(r.RMSE_hi)}] | {r.pct_within_1px:.0f}% of {r.pixel_m:.0f} m |")

    # ---------------- findings
    F = []
    lowering_area = int(s["area_lowering_gt_thr_m2"])
    low_tag = "SUPPORTED" if -s["median_dz_m"] > s["detect_threshold_m"] else "NOT DEMONSTRATED"
    F.append(f"**{low_tag}: the beach lowered between June and October.** Median lidar elevation change {s['median_dz_m']:.3f} m over "
             f"{int(s['common_cells_1m2'])} common 1 m cells; {lowering_area} m² lowered by more than {s['detect_threshold_m']:.1f} m "
             f"(the accuracy bound of QC flag 1). This is 'beach lowering', not shown to be net sand loss.")
    for p in ["S2_NDWI", "S2_MNDWI"]:
        t, det = tag_feature_match(S, p, "B1_wetdry")
        r = g(M, p, "B1_wetdry")
        per = ", ".join(f"{d} {f1(g(M, p, 'B1_wetdry', d).RMSE_m)} m" for d in DATES)
        F.append(f"**{t}: {NAME[p]} marks the lidar wet/dry edge.** Pooled RMSE {f1(r.RMSE_m)} m [{f1(r.RMSE_lo)}-{f1(r.RMSE_hi)}] "
                 f"(per date: {per}). Same-row comparison: {det}.")
    nir = s2m.offshore_nir_reflectance_median
    F.append(f"**Data-quality note (June Sentinel-2):** open-ocean near-infrared reflectance was {nir['2026-06']:.3f} in June against "
             f"{nir['2026-09']:.3f} (Sept) and {nir['2026-10']:.3f} (Oct). Bright water like this suggests sun glint or haze, which weakens the water signal; "
             "it is the likely reason MNDWI is least accurate in June.")
    for p in radar:
        t, det = tag_feature_match(S, p, "B2_dunetoe")
        r = g(M, p, "B2_dunetoe")
        F.append(f"**{t}: the {NAME[p]} edge marks the dune toe.** Pooled RMSE {f1(r.RMSE_m)} m [{f1(r.RMSE_lo)}-{f1(r.RMSE_hi)}] "
                 f"on {int(r.N)} rows in {int(r.n_blocks)} alongshore blocks (the dune face is only in view on part of the beach). Same-row comparison: {det}.")
    p = "S1_VV"; w = g(M, p, "B1_wetdry")
    F.append(f"**{tag_not_tracking(M, p, 'B1_wetdry')}: the Sentinel-1 VV edge is not the waterline.** Against the lidar wet/dry edge: RMSE {f1(w.RMSE_m)} m, "
             f"bias {w.bias_m:+.1f} m (landward) pooled; per date RMSE " + ", ".join(f"{f1(g(M, p, 'B1_wetdry', d).RMSE_m)} m" for d in DATES) + ".")
    t, worse = tag_better(M, "EXP_tideaware_S2", "S2_NDWI", "B1_wetdry")
    a, b = g(M, "EXP_tideaware_S2", "B1_wetdry"), g(M, "S2_NDWI", "B1_wetdry")
    per = "; ".join(f"{d}: {f1(g(M, 'S2_NDWI', 'B1_wetdry', d).RMSE_m)} → {f1(g(M, 'EXP_tideaware_S2', 'B1_wetdry', d).RMSE_m)} m" for d in DATES)
    F.append(f"**{t}: correcting Sentinel-2 for the tide improves the waterline (EXPERIMENTAL; uses the lidar beach slope from training rows, so it is not satellite-only).** "
             f"The October image was taken when the water was {tide.loc['2026-10','wl_at_S2_m'] - tide.loc['2026-10','wl_at_lidar_m']:.2f} m higher than at the lidar scan, "
             f"and the correction removes most of that month's bias ({g(M, 'S2_NDWI', 'B1_wetdry', '2026-10').bias_m:+.1f} → {g(M, 'EXP_tideaware_S2', 'B1_wetdry', '2026-10').bias_m:+.1f} m). "
             f"Pooled RMSE {f1(b.RMSE_m)} → {f1(a.RMSE_m)} m, but per date: {per}"
             + (f" — worse on {', '.join(worse)}." if worse else "."))
    c_raw, c_cor = ch("S2_NDWI", "B3_contour"), ch("EXP_tideaware_S2", "B3_contour")
    c_cor_wd = ch("EXP_tideaware_S2", "B1_wetdry")
    F.append(f"**{tag_change(c_cor)}: after the tide correction, the Sentinel-2 waterline's June-to-October shift matches the retreat of the lidar "
             f"{z3:.1f} m contour.** Sentinel-2 moved {c_cor.median_sensor_shift_m:+.1f} m and the contour {c_cor.median_lidar_shift_m:+.1f} m on the same rows "
             f"(change error RMSE {f1(c_cor.RMSE_m)} m [{f1(c_cor.RMSE_lo)}-{f1(c_cor.RMSE_hi)}], N = {int(c_cor.N)}). "
             f"**{tag_change(c_cor_wd)}** for the lidar wet/dry edge, the feature Sentinel-2 matches on most dates: it moved only "
             f"{c_cor_wd.median_lidar_shift_m:+.1f} m (change error RMSE {f1(c_cor_wd.RMSE_m)} m). Which of the two the satellite shift reflects is unresolved. "
             f"Without the tide correction the Sentinel-2 edge moved {c_raw.median_sensor_shift_m:+.1f} m, so most of the raw shift is tide, not beach. One pair of dates only.")
    for p in radar:
        c = ch(p, "B2_dunetoe")
        if c is None:
            continue
        F.append(f"**{tag_change(c)}: the {NAME[p]} edge stayed put, like the dune toe.** Median shift {c.median_sensor_shift_m:+.1f} m vs dune toe "
                 f"{c.median_lidar_shift_m:+.1f} m on the same {int(c.N)} rows; but the row-by-row change error is {f1(c.RMSE_m)} m "
                 f"[{f1(c.RMSE_lo)}-{f1(c.RMSE_hi)}], so stability is shown on average, not row by row.")
    if have_nisar:
        t, worse = tag_better(M, "EXP_radar_S1VV+NISARHH", "ABL_radar_S1VV_only", "B2_dunetoe")
        a, b = g(M, "EXP_radar_S1VV+NISARHH", "B2_dunetoe"), g(M, "ABL_radar_S1VV_only", "B2_dunetoe")
        F.append(f"**NISAR ablation — {t}: adding NISAR HH to Sentinel-1 VV improves the dune line (EXPERIMENTAL).** With NISAR RMSE {f1(a.RMSE_m)} m "
                 f"[{f1(a.RMSE_lo)}-{f1(a.RMSE_hi)}]; without NISAR, same rows, {f1(b.RMSE_m)} m [{f1(b.RMSE_lo)}-{f1(b.RMSE_hi)}]. "
                 "NISAR passes used: " + "; ".join(f"{r.Index} {r.direction} track {r.track}" for r in nmeta.itertuples())
                 + ". The September pass looks from the opposite direction, which can move a radar edge.")
    else:
        F.append("**NOT YET RUN: NISAR accuracy and the NISAR ablation.** No NASA Earthdata login was available. Run `.venv/bin/python src/earthdata_login.py`, "
                 "then `.venv/bin/python run_validation.py`; NISAR rows, the ablation and its tag are added automatically.")
    L += ["", "## Findings", ""] + [f"{i}. {x}" for i, x in enumerate(F, 1)]

    L += ["", "## Where this could be wrong",
          "- **The lidar never reaches the still-water line** (FRF removes water returns), so the wet/dry edge depends on FRF's automatic filter and on waves at scan time.",
          "- **Timing:** see the timing table; tide and waves differ between each image and the lidar scan. Sentinel-1 scenes all come from one orbit "
          f"(relative orbit {int(s1m.relative_orbit.iloc[0])}, {s1m.orbit_state.iloc[0]}) to keep the viewing direction constant, which puts the June and September "
          f"scenes {hours(lm.loc['2026-06','scan_utc'], s1m.loc['2026-06','acquisition_utc'])/24:.1f} and "
          f"{hours(lm.loc['2026-09','scan_utc'], s1m.loc['2026-09','acquisition_utc'])/24:.1f} days after the lidar.",
          "- **Image quality:** the June Sentinel-2 water is unusually bright (finding on data quality).",
          "- **Pixel size:** 10 m (Sentinel-2 NDWI, Sentinel-1) and 20 m (MNDWI); differences smaller than one pixel are not resolvable.",
          "- **Geolocation:** each product is used on its own map grid with no extra co-registration.",
          "- **Edge rules:** a different smoothing, threshold or dune-toe rule would move the numbers by metres.",
          "- **Small samples:** the dune toe is visible on a minority of rows, so its intervals rest on few alongshore blocks; three dates; one ~500 m site.",
          "- **The tide correction uses lidar** (beach slope), so it is a physics check, not a satellite-only method.",
          "- **Tidal datum epoch** for MHW is 1983-2001.",
          "- **NISAR data are provisional** (NISAR_L2_GCOV_PROVISIONAL_V1). A newer NISAR_L2_GCOV_V1 collection exists but, when searched, "
          "held no granule for these dates over the site.", "",
          "## How this transfers",
          "The method needs a reference elevation survey, a tide gauge and the satellite images, so it can be repeated wherever a survey overlaps a NISAR pass, "
          "for example on eroding Indian coasts such as Odisha, Kerala or Puducherry. That is future work.", "",
          "## How claims are tagged", ""] + [f"- {r}" for r in TAG_RULES]
    L += ["", "## Self-checks", ""]
    if sc_path.exists():
        sc = pd.read_csv(sc_path)
        L += ["| Check | Status | Detail |", "|---|---|---|"] + [f"| {r.check} | {r.status} | {r.detail} |" for r in sc.itertuples()]
    else:
        L.append("(self-checks not run yet)")
    L += ["", "Figures: `outputs/figures/` (PNG and interactive HTML). Tables: `outputs/*.csv`. Sources: `CITATIONS.md`."]
    (ROOT / "VALIDATION_SUMMARY.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    citations()
    summary()
    print("wrote CITATIONS.md and VALIDATION_SUMMARY.md")
