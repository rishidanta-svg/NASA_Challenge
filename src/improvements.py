"""Strict independent test, simple baselines, wave-runup physics and calibrated NISAR use.

Responds to the audit points that apply to this project (see REVIEW notes):
  * Strict hold-out: each test fold is ONE date x ONE 100 m alongshore block; everything
    tuned or calibrated (thresholds, sensor offsets, weights) uses only rows from OTHER
    dates AND OTHER blocks. 3 dates x 5 blocks = 15 folds.
  * No evaluation lidar inside any method: the beach slope used by the physics comes from
    separate calibration scans taken days before each evaluation scan.
  * Simple baselines on exactly the same rows: "typical position" (median of the training
    rows' lidar line) for positions, and "no change" for June->October shifts.
  * Physics (waterline): the visible wet/dry line sits at tide + wave runup. Runup R2% from
    Stockdon et al. (2006), with fixed published coefficients and no tuning:
        R2 = 1.1 * (0.35*b*sqrt(H0*L0) + sqrt(H0*L0*(0.563*b^2 + 0.004)) / 2),  L0 = g*Tp^2/(2*pi)
    On a planar foreshore of slope b, a water-level difference dEta moves the line by dEta/b:
        x_at_lidar_time = x_at_image_time + [(tide+R2)_image - (tide+R2)_lidar] / b
    H0 is approximated by Hs at the 17 m Waverider (no deep-water back-shoaling).
  * NISAR (dune line): each radar edge gets an offset learned on training rows; NISAR
    offsets are learned separately per viewing direction (ascending/descending). Sensors
    are combined by inverse-variance weights from training residuals, with and without NISAR.
  * Location sensitivity: how RMSE changes if a sensor's edges are shifted by 5 or 10 m.
"""
from pathlib import Path
import os
import numpy as np
import pandas as pd
import xarray as xr

import score
from score import water_edges, train_objective, choose_threshold, metrics, tide_at, SEED
from frf import ROWS10, PROC

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("SARS_OUT", ROOT / "outputs"))
DATES = ["2026-06", "2026-09", "2026-10"]
G = 9.81


# ------------------------------------------------------------------ inputs
def folds():
    f = pd.DataFrame({"y": ROWS10})
    f["block"] = (np.arange(len(ROWS10)) // 10).astype(int)       # 100 m blocks for hold-out
    f["boot_block"] = (np.arange(len(ROWS10)) // 5).astype(int)   # 50 m blocks for intervals
    return f


def calibration_slope():
    """Median foreshore slope per date from the CALIBRATION scans (never evaluated)."""
    ds = xr.open_dataset(PROC / "lidar_calibration.nc")
    x = ds.xFRF.values
    out = {}
    for d in ds.date.values:
        sl = []
        for y in ROWS10:
            band = ds.elevation.sel(date=d).sel(yFRF=slice(y - 5, y + 4)).median("yFRF").values
            ok = np.isfinite(band)
            if ok.sum() < 6:
                continue
            xs, zs = x[ok], band[ok]
            m = xs >= xs.max() - 10
            if m.sum() >= 4:
                s = -np.polyfit(xs[m], zs[m], 1)[0]
                if s > 0.005:
                    sl.append(s)
        out[str(d)] = float(np.median(sl))
    return out


def waves_at(times):
    w = pd.read_csv(PROC / "waves_17m.csv", parse_dates=["time_utc"])
    w = w[(w.qcFlagE == 1) & w.Hs_m.notna() & w.Tp_s.notna()]
    ts = (w.time_utc - pd.Timestamp("1970-01-01")).dt.total_seconds().to_numpy()
    out = {}
    for k, s in times.items():
        t = pd.Timestamp(s)
        t = t.tz_localize(None) if t.tzinfo else t
        q = (t - pd.Timestamp("1970-01-01")).total_seconds()
        if np.min(np.abs(ts - q)) > 3 * 3600:
            raise ValueError(f"no QC'd wave record within 3 h of {s}")
        out[k] = (float(np.interp(q, ts, w.Hs_m)), float(np.interp(q, ts, w.Tp_s)))
    return out


def stockdon_r2(H0, Tp, b):
    L0 = G * Tp ** 2 / (2 * np.pi)
    return 1.1 * (0.35 * b * np.sqrt(H0 * L0) + np.sqrt(H0 * L0 * (0.563 * b ** 2 + 0.004)) / 2)


# ------------------------------------------------------------------ strict CV helpers
def strict_water(lidar, F, correct):
    """S2 NDWI edge, threshold tuned on other dates + other blocks; `correct(df)` -> corrected x."""
    da = xr.open_dataset(PROC / "s2_profiles.nc")["NDWI"]
    raw = {}
    for t in score.THR_GRID:
        df = water_edges(da, t).merge(F, on="y").merge(lidar[["date", "y", "B1_wetdry"]], on=["date", "y"])
        df["x_edge"] = correct(df)
        raw[t] = df
    out = []
    for d in DATES:
        for k in sorted(F.block.unique()):
            cands = []
            for t, df in raw.items():
                tr = df[(df.date != d) & (df.block != k)]
                cands.append((t, *train_objective(tr, "B1_wetdry"), df))
            t, cov, mae, df = choose_threshold(cands)
            te = df[(df.date == d) & (df.block == k)]
            out.append(te[["date", "y", "x_edge"]].assign(threshold=t))
    return pd.concat(out, ignore_index=True)


def strict_baseline(lidar, F, target):
    rows = []
    L = lidar.merge(F, on="y")
    for d in DATES:
        for k in sorted(F.block.unique()):
            tr = L[(L.date != d) & (L.block != k)][target]
            for y in F[F.block == k].y:
                rows.append((d, y, float(np.nanmedian(tr))))
    return pd.DataFrame(rows, columns=["date", "y", "x_edge"])


def strict_radar(lidar, F, sb, direction):
    """Calibrated radar edges and inverse-variance fusion for the dune toe."""
    L = sb[sb["product"].isin(["S1_VV", "S1_VH", "NISAR_HH", "NISAR_HV"])].pivot_table(
        index=["date", "y"], columns="product", values="boundary_x").reset_index()
    L = L.merge(lidar[["date", "y", "B2_dunetoe"]], on=["date", "y"]).merge(F, on="y")
    L["dir_S1"] = "S1"
    for p in ["NISAR_HH", "NISAR_HV"]:
        L[f"dir_{p}"] = L.date.map(direction)
    preds = []
    for d in DATES:
        for k in sorted(F.block.unique()):
            tr = L[(L.date != d) & (L.block != k) & L.B2_dunetoe.notna()]
            te = L[(L.date == d) & (L.block == k)].copy()
            cal = {}
            for p in ["S1_VV", "S1_VH", "NISAR_HH", "NISAR_HV"]:
                dcol = "dir_S1" if p.startswith("S1") else f"dir_{p}"
                want = te[dcol].iloc[0] if len(te) else None
                trp = tr[tr[dcol] == want] if p.startswith("NISAR") else tr
                r = (trp[p] - trp.B2_dunetoe).dropna()
                cal[p] = (r.mean(), r.var(ddof=1), len(r)) if len(r) >= 5 else (np.nan, np.nan, len(r))
            for _, row in te.iterrows():
                c = {p: row[p] - cal[p][0] for p in cal}           # offset-corrected edges
                w = {p: 1 / cal[p][1] for p in cal if np.isfinite(c[p]) and np.isfinite(cal[p][1]) and cal[p][1] > 0}
                fuse = lambda ps: (sum(w[p] * c[p] for p in ps if p in w) / sum(w[p] for p in ps if p in w)) \
                    if any(p in w for p in ps) else np.nan
                preds.append({"date": d, "y": row.y,
                              "S1VV_raw": row.S1_VV, "NISARHH_raw": row.NISAR_HH,
                              "MEAN_S1VV_NISARHH_raw": (row.S1_VV + row.NISAR_HH) / 2,
                              "S1VV_cal": c["S1_VV"], "NISARHH_cal": c["NISAR_HH"],
                              "FUSE_S1_only": fuse(["S1_VV", "S1_VH"]),
                              "FUSE_S1_NISAR": fuse(["S1_VV", "S1_VH", "NISAR_HH", "NISAR_HV"]),
                              "nisar_calibrated": bool(np.isfinite(c["NISAR_HH"]))})
    return pd.DataFrame(preds)


# ------------------------------------------------------------------ scoring
def score_group(pred, lidar, F, target, methods, pix, group):
    """Metrics for each method on the SAME rows (where every method and the target exist)."""
    j = pred.merge(lidar[["date", "y", target]], on=["date", "y"]).merge(F, on="y")
    common = j[methods + [target]].notna().all(axis=1)
    j = j[common]
    rows = []
    for m in methods:
        e = (j[m] - j[target]).to_numpy()
        for d in DATES + ["pooled"]:
            sel = np.ones(len(j), bool) if d == "pooled" else (j.date == d).to_numpy()
            rows.append(dict(group=group, product=m, lidar_boundary=target, date=d, pixel_m=pix,
                             **metrics(e[sel], pix, j.boot_block.to_numpy()[sel])))
    return pd.DataFrame(rows), j


def main():
    F = folds()
    lidar = pd.read_csv(OUT / "lidar_boundaries.csv")
    sb = pd.read_csv(OUT / "sensor_boundaries.csv")
    s2m = pd.read_csv(PROC / "s2_meta.csv").set_index("date_key")
    lm = pd.read_csv(PROC / "lidar_scan_meta.csv").set_index("date_key")
    nm = pd.read_csv(PROC / "nisar_meta.csv").set_index("date_key")
    slope = calibration_slope()
    wl_s2 = tide_at(s2m.acquisition_utc.to_dict()); wl_li = tide_at(lm.scan_utc.to_dict())
    wv_s2 = waves_at(s2m.acquisition_utc.to_dict()); wv_li = waves_at(lm.scan_utc.to_dict())
    phys = pd.DataFrame([{"date": d, "slope_calibration": slope[d],
                          "tide_image_m": wl_s2[d], "tide_lidar_m": wl_li[d],
                          "Hs_image_m": wv_s2[d][0], "Tp_image_s": wv_s2[d][1],
                          "Hs_lidar_m": wv_li[d][0], "Tp_lidar_s": wv_li[d][1],
                          "R2_image_m": stockdon_r2(*wv_s2[d], slope[d]),
                          "R2_lidar_m": stockdon_r2(*wv_li[d], slope[d])} for d in DATES])
    phys["shift_tide_m"] = (phys.tide_image_m - phys.tide_lidar_m) / phys.slope_calibration
    phys["shift_tide_runup_m"] = ((phys.tide_image_m + phys.R2_image_m) - (phys.tide_lidar_m + phys.R2_lidar_m)) / phys.slope_calibration
    phys.to_csv(OUT / "improvements_physics_inputs.csv", index=False, float_format="%.4f")
    P = phys.set_index("date")

    # ---- waterline group (target: lidar wet/dry edge)
    w = strict_water(lidar, F, lambda df: df.x_edge).rename(columns={"x_edge": "S2_raw"})
    w = w.merge(strict_water(lidar, F, lambda df: df.x_edge + df.date.map(P.shift_tide_m))
                .rename(columns={"x_edge": "S2_tide"})[["date", "y", "S2_tide"]], on=["date", "y"])
    w = w.merge(strict_water(lidar, F, lambda df: df.x_edge + df.date.map(P.shift_tide_runup_m))
                .rename(columns={"x_edge": "S2_tide_runup"})[["date", "y", "S2_tide_runup"]], on=["date", "y"])
    w = w.merge(strict_baseline(lidar, F, "B1_wetdry").rename(columns={"x_edge": "BASE_typical"}), on=["date", "y"])
    MW = ["BASE_typical", "S2_raw", "S2_tide", "S2_tide_runup"]
    Mw, jw = score_group(w, lidar, F, "B1_wetdry", MW, 10.0, "waterline")

    # ---- dune line group (target: lidar dune toe)
    direction = nm.direction.to_dict()
    r = strict_radar(lidar, F, sb, direction)
    r = r.merge(strict_baseline(lidar, F, "B2_dunetoe").rename(columns={"x_edge": "BASE_typical"}), on=["date", "y"])
    MD = ["BASE_typical", "S1VV_raw", "NISARHH_raw", "MEAN_S1VV_NISARHH_raw", "S1VV_cal", "FUSE_S1_only", "FUSE_S1_NISAR"]
    Md, jd = score_group(r, lidar, F, "B2_dunetoe", MD, 10.0, "dune line")
    Mn, _ = score_group(r, lidar, F, "B2_dunetoe", ["BASE_typical", "S1VV_cal", "NISARHH_cal"], 10.0,
                        "dune line, NISAR calibratable rows")
    M = pd.concat([Mw, Md, Mn], ignore_index=True)
    M.to_csv(OUT / "improvements_position.csv", index=False, float_format="%.3f")
    pd.concat([w.assign(group="waterline"), r.assign(group="dune line")]).to_csv(
        OUT / "improvements_predictions.csv", index=False, float_format="%.2f")

    # ---- June -> October change vs a "no change" baseline, same rows
    crow = []
    for group, pred, methods, targets in [("waterline", w, ["S2_raw", "S2_tide", "S2_tide_runup"], ["B1_wetdry", "B3_contour"]),
                                          ("dune line", r, ["S1VV_raw", "NISARHH_raw", "FUSE_S1_only", "FUSE_S1_NISAR"], ["B2_dunetoe"])]:
        for tgt in targets:
            pv = pred.pivot_table(index="y", columns="date", values=methods)
            lv = lidar.pivot(index="y", columns="date", values=tgt)
            j = pd.DataFrame({"y": lv.index, "lidar_shift": (lv["2026-10"] - lv["2026-06"]).to_numpy()})
            for m in methods:
                j[m] = (pv[(m, "2026-10")] - pv[(m, "2026-06")]).reindex(lv.index).to_numpy()
            j["NO_CHANGE"] = 0.0
            j = j.merge(F, on="y")
            j = j[j[methods + ["lidar_shift"]].notna().all(axis=1)]
            for m in ["NO_CHANGE"] + methods:
                e = (j[m] - j.lidar_shift).to_numpy()
                crow.append(dict(group=group, product=m, lidar_boundary=tgt, pixel_m=10.0,
                                 median_pred_shift_m=float(np.median(j[m])) if len(j) else np.nan,
                                 median_lidar_shift_m=float(np.median(j.lidar_shift)) if len(j) else np.nan,
                                 **metrics(e, 10.0, j.boot_block.to_numpy())))
    pd.DataFrame(crow).to_csv(OUT / "improvements_change.csv", index=False, float_format="%.3f")

    # ---- location sensitivity: shift a sensor's edges by delta metres
    grow = []
    for p, tgt in [("S2_NDWI", "B1_wetdry"), ("S1_VV", "B2_dunetoe"), ("NISAR_HH", "B2_dunetoe")]:
        j = sb[sb["product"] == p].merge(lidar[["date", "y", tgt]], on=["date", "y"])
        e = (j.boundary_x - j[tgt]).dropna().to_numpy()
        for dlt in [-10, -5, 0, 5, 10]:
            grow.append(dict(product=p, lidar_boundary=tgt, shift_m=dlt, N=len(e),
                             RMSE_m=float(np.sqrt(np.mean((e + dlt) ** 2)))))
    pd.DataFrame(grow).to_csv(OUT / "improvements_geolocation.csv", index=False, float_format="%.3f")

    P_ = M[M.date == "pooled"].set_index(["group", "product"])
    print(phys.round(3).to_string(index=False))
    print("\nStrict hold-out, pooled RMSE (m) on identical rows:")
    print(P_[["N", "RMSE_m", "RMSE_lo", "RMSE_hi"]].round(2).to_string())
    print("\nChange vs no-change:")
    print(pd.DataFrame(crow)[["group", "product", "lidar_boundary", "N", "median_pred_shift_m", "median_lidar_shift_m", "RMSE_m", "RMSE_lo", "RMSE_hi"]].round(2).to_string(index=False))


if __name__ == "__main__":
    main()
