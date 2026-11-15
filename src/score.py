"""Validation: sensor boundaries vs lidar ground truth.

Edge rules (documented, fixed in advance):
  Water indices (S2 NDWI / MNDWI): first seaward crossing of a threshold, scanning
    from x = 20 m. The threshold is the ONLY tuned setting. It is chosen on training
    blocks only (5-fold spatial block CV): among thresholds that find an edge on at
    least MIN_COVERAGE of the training rows on EVERY date, the one with the lowest
    training MAE. (Without the coverage rule a threshold could look accurate simply
    by finding no edge on hard rows.)
  Radar (S1 VV/VH, NISAR HH/HV): strongest seaward DROP in backscatter (dB) within
    x = 20..150 m after an 11 m running mean (frf.max_gradient_edge). No tuning.
Sign convention: x increases seaward; error = sensor - lidar > 0 means sensor is seaward.
"""
from pathlib import Path
import json
import os
import numpy as np
import pandas as pd
import xarray as xr

from frf import ROWS10, PROC, edge_crossing, max_gradient_edge

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("SARS_OUT", ROOT / "outputs"))
OUT.mkdir(parents=True, exist_ok=True)
SEED = 20261115
N_BOOT = 1000
FOLD_BLOCK = 10      # rows per CV fold (5 folds of 100 m)
BOOT_BLOCK = 5       # rows per bootstrap block (50 m)
MIN_COVERAGE = 0.9   # a threshold must find an edge on >= 90% of training rows on every date
THR_GRID = np.round(np.arange(-0.40, 0.401, 0.05), 2)
BOUNDS = ["B1_wetdry", "B2_dunetoe", "B3_contour"]
DATES = ["2026-06", "2026-09", "2026-10"]


# ---------------------------------------------------------------- loading
def load_products():
    prods, meta = {}, {}
    s2 = xr.open_dataset(PROC / "s2_profiles.nc"); m2 = pd.read_csv(PROC / "s2_meta.csv")
    for v, pix in [("NDWI", "pixel_m_green_nir"), ("MNDWI", "pixel_m_swir16")]:
        prods[f"S2_{v}"] = s2[v]
        meta[f"S2_{v}"] = {r.date_key: dict(pixel_m=getattr(r, pix), acquisition_utc=r.acquisition_utc,
                                           product_id=r.item_id) for r in m2.itertuples()}
    s1 = xr.open_dataset(PROC / "s1_profiles.nc"); m1 = pd.read_csv(PROC / "s1_meta.csv")
    for v in ["VV", "VH"]:
        prods[f"S1_{v}"] = s1[v]
        meta[f"S1_{v}"] = {r.date_key: dict(pixel_m=r.pixel_m, acquisition_utc=r.acquisition_utc,
                                           product_id=r.item_id) for r in m1.itertuples()}
    nis = PROC / "nisar_profiles.nc"
    if nis.exists():
        n = xr.open_dataset(nis); mn = pd.read_csv(PROC / "nisar_meta.csv")
        for v in ["HH", "HV"]:
            prods[f"NISAR_{v}"] = n[v]
            meta[f"NISAR_{v}"] = {r.date_key: dict(pixel_m=max(r.pixel_m_x, r.pixel_m_y),
                                                  acquisition_utc=r.begin_utc, product_id=r.granule)
                                  for r in mn.itertuples()}
    return prods, meta


def folds():
    f = pd.DataFrame({"y": ROWS10})
    f["fold"] = (np.arange(len(ROWS10)) // FOLD_BLOCK).astype(int)
    f["boot_block"] = (np.arange(len(ROWS10)) // BOOT_BLOCK).astype(int)
    return f


# ---------------------------------------------------------------- edges
def radar_edges(da):
    x = da.x.values
    rows = [(d, y, max_gradient_edge(x, da.sel(date=d, y=y).values, 20, 150, sign=-1))
            for d in da.date.values for y in ROWS10]
    return pd.DataFrame(rows, columns=["date", "y", "x_edge"])


def water_edges(da, thr):
    x = da.x.values
    sel = x >= 20
    rows = [(d, y, edge_crossing(x[sel], da.sel(date=d, y=y).values[sel], thr, rising=True))
            for d in da.date.values for y in ROWS10]
    return pd.DataFrame(rows, columns=["date", "y", "x_edge"])


def train_objective(df, target):
    """(min per-date coverage, MAE) on rows where the lidar target exists."""
    d = df[df[target].notna()]
    cov = d.groupby("date").x_edge.apply(lambda s: s.notna().mean())
    err = (d.x_edge - d[target]).abs()
    return float(cov.min()), float(err.mean()) if err.notna().any() else np.inf


def choose_threshold(cands):
    """cands: list of (thr, min_cov, mae). Coverage rule first, then lowest MAE."""
    ok = [c for c in cands if c[1] >= MIN_COVERAGE]
    if ok:
        return min(ok, key=lambda c: c[2])
    return max(cands, key=lambda c: (c[1], -c[2]))  # fallback, flagged in output


def cv_water_edges(da, lidar, target, F, correct=None):
    """Out-of-fold edges. `correct(df, k)` optionally adjusts edges using only
    information from folds other than k; tuning is done on the corrected edges."""
    raw = {t: water_edges(da, t).merge(F, on="y").merge(lidar[["date", "y", target]], on=["date", "y"])
           for t in THR_GRID}
    out, chosen = [], []
    for k in sorted(F.fold.unique()):
        cands = []
        for t, df in raw.items():
            dfk = df.copy()
            if correct is not None:
                dfk["x_edge"] = correct(dfk, k)
            cands.append((t, *train_objective(dfk[dfk.fold != k], target), dfk))
        t, cov, mae, dfk = choose_threshold(cands)
        chosen.append({"fold": k, "threshold": t, "train_min_coverage": cov, "train_mae_m": mae,
                       "coverage_rule_met": cov >= MIN_COVERAGE})
        out.append(dfk[dfk.fold == k][["date", "y", "x_edge"]].assign(threshold=t))
    return pd.concat(out, ignore_index=True), pd.DataFrame(chosen)


# ---------------------------------------------------------------- physics (experimental)
def foreshore_slope():
    """tan(beta) per date and row: linear fit over the seaward-most 10 m of lidar data."""
    ds = xr.open_dataset(PROC / "lidar_scans.nc")
    x = ds.xFRF.values
    rows = []
    for d in ds.date.values:
        e = ds.elevation.sel(date=d)
        for y in ROWS10:
            band = e.sel(yFRF=slice(y - 5, y + 4)).median("yFRF").values
            ok = np.isfinite(band)
            if ok.sum() < 6:
                rows.append((d, y, np.nan)); continue
            xs, zs = x[ok], band[ok]
            m = xs >= xs.max() - 10
            slope = -np.polyfit(xs[m], zs[m], 1)[0] if m.sum() >= 4 else np.nan
            rows.append((d, y, slope if slope > 0.005 else np.nan))
    return pd.DataFrame(rows, columns=["date", "y", "tanb"])


def tide_at(times):
    t = pd.read_csv(PROC / "tide_8651370.csv")
    ts = (pd.to_datetime(t["Date Time"]) - pd.Timestamp("1970-01-01")).dt.total_seconds().to_numpy()
    wl = pd.to_numeric(t["Water Level"], errors="coerce").to_numpy()
    ok = np.isfinite(wl)
    ts, wl = ts[ok], wl[ok]
    out = {}
    for k, s in times.items():
        tt = pd.Timestamp(s)
        tt = tt.tz_localize(None) if tt.tzinfo else tt
        w = (tt - pd.Timestamp("1970-01-01")).total_seconds()
        if w < ts.min() or w > ts.max():
            raise ValueError(f"tide record does not cover {s}")
        near = np.min(np.abs(ts - w))
        if near > 15 * 60:
            raise ValueError(f"no tide observation within 15 min of {s}")
        out[k] = float(np.interp(w, ts, wl))
    return out


# ---------------------------------------------------------------- metrics
def metrics(err, pix, blocks):
    rng = np.random.default_rng(SEED)  # same data -> same intervals
    ok = np.isfinite(err)
    e, b = err[ok], blocks[ok]
    n = len(e)
    nb = len(np.unique(b))
    base = dict(N=n, n_blocks=nb)
    if n < 5:
        return {**base, **{k: np.nan for k in ["bias_m", "MAE_m", "RMSE_m", "pct_within_1px", "bias_lo", "bias_hi",
                                                "MAE_lo", "MAE_hi", "RMSE_lo", "RMSE_hi"]}}
    ub = np.unique(b)
    boots = {"bias": [], "MAE": [], "RMSE": []}
    for _ in range(N_BOOT):
        pick = rng.choice(ub, size=len(ub), replace=True)
        s = np.concatenate([e[b == k] for k in pick])
        boots["bias"].append(s.mean()); boots["MAE"].append(np.abs(s).mean())
        boots["RMSE"].append(np.sqrt((s ** 2).mean()))
    q = {k: np.percentile(v, [2.5, 97.5]) for k, v in boots.items()}
    return {**base, "bias_m": e.mean(), "MAE_m": np.abs(e).mean(), "RMSE_m": np.sqrt((e ** 2).mean()),
            "pct_within_1px": 100 * np.mean(np.abs(e) <= pix),
            "bias_lo": q["bias"][0], "bias_hi": q["bias"][1], "MAE_lo": q["MAE"][0], "MAE_hi": q["MAE"][1],
            "RMSE_lo": q["RMSE"][0], "RMSE_hi": q["RMSE"][1]}


def main():
    F = folds()
    F.to_csv(OUT / "cv_folds.csv", index=False)
    lidar = pd.read_csv(ROOT / "outputs" / "lidar_boundaries.csv")
    if OUT != ROOT / "outputs":
        lidar.to_csv(OUT / "lidar_boundaries.csv", index=False)
    prods, meta = load_products()
    have_nisar = "NISAR_HH" in prods
    print("products:", list(prods), "| NISAR available:", have_nisar)

    edges, thr_tables = {}, []
    for p, da in prods.items():
        if p.startswith("S2_"):
            e, ch = cv_water_edges(da, lidar, "B1_wetdry", F)
            thr_tables.append(ch.assign(product=p))
        else:
            e = radar_edges(da)
        edges[p] = e

    # ---- EXPERIMENTAL tide-aware S2 waterline (uses lidar beach slope from training rows)
    s2m = pd.read_csv(PROC / "s2_meta.csv")
    lm = pd.read_csv(PROC / "lidar_scan_meta.csv")
    wl_s2 = tide_at(dict(zip(s2m.date_key, s2m.acquisition_utc)))
    wl_li = tide_at(dict(zip(lm.date_key, lm.scan_utc)))
    slope = foreshore_slope().merge(F, on="y")
    tb_by_fold = {k: slope[slope.fold != k].groupby("date").tanb.median().to_dict() for k in F.fold.unique()}

    def tide_correct(df, k):
        tb = df.date.map(tb_by_fold[k])
        dwl = df.date.map(lambda d: wl_s2[d] - wl_li[d])
        return df.x_edge + dwl / tb

    e, ch = cv_water_edges(prods["S2_NDWI"], lidar, "B1_wetdry", F, correct=tide_correct)
    edges["EXP_tideaware_S2"] = e
    thr_tables.append(ch.assign(product="EXP_tideaware_S2"))
    meta["EXP_tideaware_S2"] = meta["S2_NDWI"]
    pd.DataFrame({"date": list(wl_s2), "wl_at_S2_m": list(wl_s2.values()),
                  "wl_at_lidar_m": [wl_li[k] for k in wl_s2],
                  "median_tanb_all_rows": [slope[slope.date == k].tanb.median() for k in wl_s2]}
                 ).to_csv(OUT / "tide_correction_inputs.csv", index=False)

    # ---- EXPERIMENTAL radar combination and NISAR ablation (only with NISAR)
    if have_nisar:
        a = edges["S1_VV"].merge(edges["NISAR_HH"], on=["date", "y"], suffixes=("_s1", "_n"))
        a["x_edge"] = a[["x_edge_s1", "x_edge_n"]].mean(axis=1, skipna=False)
        edges["EXP_radar_S1VV+NISARHH"] = a[["date", "y", "x_edge"]]
        meta["EXP_radar_S1VV+NISARHH"] = meta["S1_VV"]
        edges["ABL_radar_S1VV_only"] = edges["S1_VV"]  # same S1 edges, scored on the SAME rows as the combination
        meta["ABL_radar_S1VV_only"] = meta["S1_VV"]

    # ---- sensor_boundaries.csv
    sb = []
    for p, e in edges.items():
        for r in e.itertuples():
            m = meta[p].get(r.date, {})
            sb.append(dict(date=r.date, y=r.y, sensor=p.split("_")[0], product=p, boundary_x=r.x_edge,
                           threshold=getattr(r, "threshold", np.nan), pixel_spacing_m=m.get("pixel_m"),
                           acquisition_utc=m.get("acquisition_utc"), granule_id=m.get("product_id")))
    sb = pd.DataFrame(sb)
    if have_nisar:  # ablation scored only where the combination exists
        comb_rows = sb[(sb["product"] == "EXP_radar_S1VV+NISARHH") & sb.boundary_x.notna()][["date", "y"]]
        abl = sb["product"] == "ABL_radar_S1VV_only"
        keep = sb[abl].merge(comb_rows, on=["date", "y"], how="left", indicator=True)["_merge"].eq("both").to_numpy()
        sb.loc[sb[abl].index[~keep], "boundary_x"] = np.nan
    sb.to_csv(OUT / "sensor_boundaries.csv", index=False, float_format="%.2f")
    pd.concat(thr_tables).to_csv(OUT / "s2_thresholds_by_fold.csv", index=False)

    # ---- metrics: full matrix (all rows available for each pair)
    rows = []
    for p in edges:
        for tgt in BOUNDS:
            df = sb[sb["product"] == p].merge(lidar[["date", "y", tgt]], on=["date", "y"]).merge(F, on="y")
            df["err"] = df.boundary_x - df[tgt]
            pix = float(df.pixel_spacing_m.max())
            for d in DATES + ["pooled"]:
                sub = df if d == "pooled" else df[df.date == d]
                rows.append(dict(product=p, lidar_boundary=tgt, date=d, pixel_m=pix,
                                 **metrics(sub.err.to_numpy(), pix, sub.boot_block.to_numpy())))
    M = pd.DataFrame(rows)
    M.to_csv(OUT / "metrics.csv", index=False, float_format="%.3f")

    # ---- same-row matrix: which lidar boundary does each sensor match? (fair comparison)
    srows = []
    for p in edges:
        df = sb[sb["product"] == p].merge(lidar[["date", "y"] + BOUNDS], on=["date", "y"]).merge(F, on="y")
        df = df[df[["boundary_x"] + BOUNDS].notna().all(axis=1)]
        pix = float(sb[sb["product"] == p].pixel_spacing_m.max())
        for d in DATES + ["pooled"]:
            sub = df if d == "pooled" else df[df.date == d]
            for tgt in BOUNDS:
                m = metrics((sub.boundary_x - sub[tgt]).to_numpy(), pix, sub.boot_block.to_numpy())
                srows.append(dict(product=p, date=d, lidar_boundary=tgt, pixel_m=pix, **m))
    pd.DataFrame(srows).to_csv(OUT / "matrix_same_rows.csv", index=False, float_format="%.3f")

    # ---- change (Jun -> Oct) error, sensor and lidar on the SAME rows
    crow = []
    for p in edges:
        s = sb[sb["product"] == p].pivot(index="y", columns="date", values="boundary_x")
        if not {"2026-06", "2026-10"} <= set(s.columns):
            continue
        ds_ = (s["2026-10"] - s["2026-06"]).rename("sensor_shift")
        pix = float(sb[sb["product"] == p].pixel_spacing_m.max())
        for tgt in BOUNDS:
            l = lidar.pivot(index="y", columns="date", values=tgt)
            dl = (l["2026-10"] - l["2026-06"]).rename("lidar_shift")
            j = pd.concat([ds_, dl], axis=1).reset_index().merge(F, on="y")
            j = j[j[["sensor_shift", "lidar_shift"]].notna().all(axis=1)]
            j["err"] = j.sensor_shift - j.lidar_shift
            crow.append(dict(product=p, lidar_boundary=tgt, pixel_m=pix,
                             median_sensor_shift_m=j.sensor_shift.median() if len(j) else np.nan,
                             median_lidar_shift_m=j.lidar_shift.median() if len(j) else np.nan,
                             **metrics(j.err.to_numpy(), pix, j.boot_block.to_numpy())))
    C = pd.DataFrame(crow)
    C.to_csv(OUT / "change_metrics.csv", index=False, float_format="%.3f")

    P = M[M.date == "pooled"]
    print("\nPooled RMSE (m):\n", P.pivot(index="product", columns="lidar_boundary", values="RMSE_m").round(1).to_string())
    print("\nThresholds by fold:\n", pd.concat(thr_tables).round(2).to_string())
    json.dump({"have_nisar": have_nisar}, open(OUT / "run_flags.json", "w"))


if __name__ == "__main__":
    main()
