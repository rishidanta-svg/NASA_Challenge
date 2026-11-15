"""Export everything the web app shows into dist/data.js.

The app contains NO hand-typed numbers: every value it displays (map, profiles,
boundaries, accuracy table, tags, timeline) is written here from the pipeline's
CSV/NetCDF outputs. Loaded as a plain <script>, so the app also works from file://.
"""
from pathlib import Path
import json
import re
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import xarray as xr

import make_report as mr
from score import tide_at

ROOT = Path(__file__).resolve().parents[1]
OUT, PROC, DIST = ROOT / "outputs", ROOT / "data" / "processed", ROOT / "dist"
DATES = ["2026-06", "2026-09", "2026-10"]
PRODUCTS = {  # product -> (label, the lidar line it is compared with, experimental?)
    "S2_NDWI": ("Sentinel-2 NDWI (optical)", "B1_wetdry", False),
    "S2_MNDWI": ("Sentinel-2 MNDWI (optical)", "B1_wetdry", False),
    "S1_VV": ("Sentinel-1 VV (C-band radar)", "B2_dunetoe", False),
    "S1_VH": ("Sentinel-1 VH (C-band radar)", "B2_dunetoe", False),
    "NISAR_HH": ("NISAR HH (L-band radar)", "B2_dunetoe", False),
    "NISAR_HV": ("NISAR HV (L-band radar)", "B2_dunetoe", False),
    "EXP_tideaware_S2": ("S2 NDWI + tide correction", "B1_wetdry", True),
}
BLAB = {"B1_wetdry": "lidar wet/dry edge", "B2_dunetoe": "lidar dune toe", "B3_contour": "lidar contour"}


def clean(v, nd=2):
    return None if v is None or (isinstance(v, float) and not np.isfinite(v)) else round(float(v), nd)


def main():
    ds = xr.open_dataset(PROC / "lidar_scans.nc")
    X, Y = ds.xFRF.values, ds.yFRF.values
    lb = pd.read_csv(OUT / "lidar_boundaries.csv")
    sb = pd.read_csv(OUT / "sensor_boundaries.csv")
    M = pd.read_csv(OUT / "metrics.csv")
    S = pd.read_csv(OUT / "matrix_same_rows.csv")
    sanity = pd.read_csv(OUT / "lidar_sanity.csv", index_col=0)["value"]
    z3 = float(lb.B3_contour_z.iloc[0])
    BLAB["B3_contour"] = f"lidar {z3:.1f} m contour"
    mr.BN["B3_contour"] = f"{z3:.1f} m contour"  # used in the tag detail text
    have_nisar = (PROC / "nisar_meta.csv").exists()

    # ---- elevation-change map (Oct - June), 2 m blocks, centimetres
    dz = (ds.elevation.sel(date="2026-10") - ds.elevation.sel(date="2026-06"))
    dz2 = dz.coarsen(yFRF=2, xFRF=2, boundary="trim").median()
    grid = {"x0": float(dz2.xFRF.values[0]), "dx": float(dz2.xFRF.values[1] - dz2.xFRF.values[0]),
            "y0": float(dz2.yFRF.values[0]), "dy": float(dz2.yFRF.values[1] - dz2.yFRF.values[0]),
            "nx": int(dz2.sizes["xFRF"]), "ny": int(dz2.sizes["yFRF"]),
            "dz_cm": [None if not np.isfinite(v) else int(round(v * 100)) for v in dz2.values.ravel()]}

    # ---- profiles: 10 m row medians (same as the pipeline), per date
    rows = sorted(lb.y.unique().tolist())
    profiles = []
    for y in rows:
        p = {"y": int(y), "x0": float(X[0]), "dx": float(X[1] - X[0]), "z": {}}
        for d in DATES:
            band = ds.elevation.sel(date=d).sel(yFRF=slice(y - 5, y + 4)).median("yFRF").values
            p["z"][d] = [clean(v) for v in band]
        p["lidar"] = {d: {b: clean(lb[(lb.date == d) & (lb.y == y)][b].item(), 1) for b in BLAB} for d in DATES}
        p["sensors"] = {}
        for prod in PRODUCTS:
            s = sb[(sb["product"] == prod) & (sb.y == y)]
            if len(s):
                p["sensors"][prod] = {d: clean(s[s.date == d].boundary_x.item(), 1) if (s.date == d).any() else None for d in DATES}
        profiles.append(p)

    # ---- accuracy table with rule-based tags (same rules as the summary)
    table = []
    for prod, (label, tgt, exp) in PRODUCTS.items():
        r = mr.g(M, prod, tgt)
        if r is None:
            continue
        tag, detail = mr.tag_feature_match(S, prod, tgt) if not exp else ("EXPERIMENTAL", "")
        per = {d: clean(mr.g(M, prod, tgt, d).RMSE_m, 1) if mr.g(M, prod, tgt, d) is not None else None for d in DATES}
        table.append({"product": prod, "label": label, "compared_with": BLAB[tgt], "N": int(r.N),
                      "bias_m": clean(r.bias_m, 1), "rmse_m": clean(r.RMSE_m, 1), "rmse_lo": clean(r.RMSE_lo, 1),
                      "rmse_hi": clean(r.RMSE_hi, 1), "pixel_m": clean(r.pixel_m, 0),
                      "pct_within_pixel": clean(r.pct_within_1px, 0), "rmse_by_date": per,
                      "tag": tag, "detail": detail, "experimental": exp})

    # ---- claims: the numbered findings exactly as generated in VALIDATION_SUMMARY.md
    text = (ROOT / "VALIDATION_SUMMARY.md").read_text()
    block = text.split("## Findings")[1].split("## Where this could be wrong")[0]
    claims = []
    section = "main"
    for line in block.strip().splitlines():
        if line.startswith("## Independent test"):
            section = "independent"
        m = re.match(r"\d+\. \*\*(.+?)\*\*\s*(.*)", line.strip())
        if not m:
            continue
        head, rest = m.group(1), m.group(2)
        tag = next((t for t in ["NOT DEMONSTRATED (mixed)", "NOT DEMONSTRATED", "SUPPORTED", "PLAUSIBLE", "NOT YET RUN"]
                    if head.startswith(t) or head.split("—")[-1].strip().startswith(t)), "NOTE")
        head = re.sub(r"^(.*?—\s*)?(SUPPORTED|PLAUSIBLE|NOT DEMONSTRATED \(mixed\)|NOT DEMONSTRATED|NOT YET RUN):\s*", r"\1", head)
        claims.append({"tag": tag, "headline": re.sub(r"\*\*", "", head), "detail": re.sub(r"\*\*", "", rest), "section": section})
    caveats = [re.sub(r"\*\*", "", l[2:]) for l in text.split("## Where this could be wrong")[1].split("##")[0].strip().splitlines() if l.startswith("- ")]

    # ---- timeline: every acquisition with its UTC time and the water level then
    lm = pd.read_csv(PROC / "lidar_scan_meta.csv").set_index("date_key")
    acq = []
    def add(sensor, d, t, pid, extra=""):
        acq.append({"sensor": sensor, "date_key": d, "utc": pd.Timestamp(t).strftime("%Y-%m-%d %H:%M"),
                    "product_id": pid, "hours_from_lidar": round(mr.hours(lm.loc[d, "scan_utc"], t), 1), "note": extra})
    for d, r in lm.iterrows():
        add("FRF lidar", d, r.scan_utc, Path(r.opendap_url).name, f"coregQCFlag {int(r.coregQCFlag)}")
    for r in pd.read_csv(PROC / "s2_meta.csv").itertuples():
        add("Sentinel-2", r.date_key, r.acquisition_utc, r.item_id, f"offshore NIR {r.offshore_nir_reflectance_median:.3f}")
    for r in pd.read_csv(PROC / "s1_meta.csv").itertuples():
        add("Sentinel-1", r.date_key, r.acquisition_utc, r.item_id, f"{r.orbit_state}, relative orbit {r.relative_orbit}")
    if have_nisar:
        for r in pd.read_csv(PROC / "nisar_meta.csv").itertuples():
            add("NISAR", r.date_key, r.begin_utc, r.concept_id, f"{r.direction}, track {r.track}")
    for a in acq:
        try:
            a["water_level_navd88_m"] = round(tide_at({0: pd.Timestamp(a["utc"]).isoformat()})[0], 2)
        except ValueError:
            a["water_level_navd88_m"] = None  # tide record not fetched for this time
    acq.sort(key=lambda a: a["utc"])

    # ---- independent test (held-out dates and places) vs simple baselines
    strict = []
    ip = OUT / "improvements_position.csv"
    if ip.exists():
        IP = pd.read_csv(ip)
        for (grp, prod), d in IP.groupby(["group", "product"], sort=False):
            r = d[d.date == "pooled"].iloc[0]
            strict.append({"group": grp, "method": mr.SNAME.get(prod, prod), "is_baseline": prod.startswith("BASE"),
                           "N": int(r.N), "rmse_m": clean(r.RMSE_m, 1), "rmse_lo": clean(r.RMSE_lo, 1), "rmse_hi": clean(r.RMSE_hi, 1),
                           "rmse_by_date": {x: clean(d[d.date == x].RMSE_m.iloc[0], 1) for x in DATES}})

    data = {
        "strict": strict,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "note": "Generated by src/export_app_data.py from outputs/ and data/processed/. Do not edit by hand.",
        "site": {"name": "Duck, North Carolina — USACE Field Research Facility", "lat": [36.183704, 36.188260],
                 "lon": [-75.753384, -75.750335], "y_range": [int(min(rows)), int(max(rows))],
                 "frame": "FRF local coordinates: x cross-shore (increasing toward the ocean), y alongshore, metres; elevations NAVD88"},
        "lowering": {"median_dz_m": round(float(sanity["median_dz_m"]), 3), "cells": int(sanity["common_cells_1m2"]),
                     "area_m2": int(sanity["area_lowering_gt_thr_m2"]), "threshold_m": float(sanity["detect_threshold_m"])},
        "contour_z": z3, "have_nisar": have_nisar, "dates": DATES,
        "grid": grid, "profiles": profiles, "table": table, "claims": claims, "caveats": caveats,
        "rules": [re.sub(r"\*\*", "", r) for r in mr.TAG_RULES], "acquisitions": acq,
        "products": {k: {"label": v[0], "compared_with": BLAB[v[1]], "experimental": v[2]} for k, v in PRODUCTS.items()},
    }
    DIST.mkdir(exist_ok=True)
    (DIST / "data.js").write_text("window.LITTORAL_DATA = " + json.dumps(data, separators=(",", ":")) + ";\n")
    (OUT / "littoral_profiles_duck_frf.json").unlink(missing_ok=True)  # superseded by dist/data.js
    print(f"wrote dist/data.js ({(DIST / 'data.js').stat().st_size / 1e3:.0f} kB): {len(profiles)} rows, "
          f"{len(table)} sensors, {len(claims)} claims, {len(acq)} acquisitions")


if __name__ == "__main__":
    main()
