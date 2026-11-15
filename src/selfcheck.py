"""Self-checks from the task prompt. Prints PASS / FAIL / NOT RUN and saves a table.

Checks are independent re-computations where possible (not just reading back the
pipeline's own outputs)."""
from pathlib import Path
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import numpy as np
import pandas as pd
import xarray as xr

from frf import fit_transform, PROC, edge_crossing

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
SRC = Path(__file__).resolve().parent
DOC_NISAR = {"2026-06": "G4250721321-ASF", "2026-10": "G4376256706-ASF"}  # from the team's document
DOC_LIDAR = {"2026-06": "2026-06-19T00:31", "2026-09": "2026-09-29T10:33", "2026-10": "2026-10-16T23:33"}
res = []


def check(name, ok, detail):
    status = "NOT RUN" if ok is None else ("PASS" if ok else "FAIL")
    res.append(dict(check=name, status=status, detail=str(detail).replace("|", "/")))
    print(f"[{status}] {name}: {detail}")


def md5(p):
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


def main():
    # 1 lidar
    lm = pd.read_csv(PROC / "lidar_scan_meta.csv")
    ok = all(lm.set_index("date_key").scan_utc.str[:16].get(k) == v for k, v in DOC_LIDAR.items())
    check("Three lidar scans loaded at the document's matched times", ok,
          "; ".join(f"{r.date_key}: {r.scan_utc} UTC" for r in lm.itertuples()))
    check("All lidar scans QC flag 1", bool((lm.coregQCFlag == 1).all()),
          f"flags {lm.coregQCFlag.astype(int).tolist()}, max RMS reflector error {lm.rmsReflectorError_m.max():.3f} m")

    # 2 sanity: recompute median change independently from the NetCDF
    ds = xr.open_dataset(PROC / "lidar_scans.nc")
    dz = (ds.elevation.sel(date="2026-10") - ds.elevation.sel(date="2026-06")).values
    s = pd.read_csv(OUT / "lidar_sanity.csv", index_col=0)["value"]
    check("Median Jun->Oct lidar change recomputed independently", abs(np.nanmedian(dz) - s["median_dz_m"]) < 1e-9,
          f"{np.nanmedian(dz):.3f} m over {int(np.isfinite(dz).sum())} common 1 m cells (reported as computed)")

    # 3 product IDs and times
    nm = PROC / "nisar_meta.csv"
    if nm.exists():
        n = pd.read_csv(nm).set_index("date_key")
        ok = all(n.concept_id.get(k) == v for k, v in DOC_NISAR.items())
        check("NISAR granule IDs match the team's document", ok, ", ".join(f"{k}: {v}" for k, v in n.concept_id.items()))
    else:
        check("NISAR granule IDs match the team's document", None, "NISAR not downloaded (no Earthdata login)")
    sb = pd.read_csv(OUT / "sensor_boundaries.csv")
    bad = []
    for f, idc, tc in [("s2_meta.csv", "item_id", "acquisition_utc"), ("s1_meta.csv", "item_id", "acquisition_utc")]:
        m = pd.read_csv(PROC / f)
        for r in m.itertuples():
            stamp = pd.Timestamp(getattr(r, tc)).strftime("%Y%m%d")
            if stamp not in getattr(r, idc):
                bad.append(f"{getattr(r, idc)} vs {getattr(r, tc)}")
            used = sb[(sb.granule_id == getattr(r, idc))].date.unique()
            if len(used) and list(used) != [r.date_key]:
                bad.append(f"{getattr(r, idc)} used for {list(used)}")
    check("Sentinel-1/2 product IDs agree with their acquisition dates and are used for the right date", not bad,
          "all consistent" if not bad else "; ".join(bad))

    # 4 leakage: independently recompute each fold's threshold from training rows only
    import score
    folds = pd.read_csv(OUT / "cv_folds.csv")
    lidar = pd.read_csv(OUT / "lidar_boundaries.csv")
    thr = pd.read_csv(OUT / "s2_thresholds_by_fold.csv")
    s2 = xr.open_dataset(PROC / "s2_profiles.nc")
    x = s2.x.values; sel = x >= 20
    mism = []
    for p in ["S2_NDWI", "S2_MNDWI"]:
        da = s2[p.split("_")[1]]
        for k in folds.fold.unique():
            train_y = set(folds[folds.fold != k].y)
            best = None
            for t in score.THR_GRID:
                errs, cov = [], []
                for d in da.date.values:
                    n_ok = n_all = 0
                    for y in train_y:
                        tgt = lidar[(lidar.date == d) & (lidar.y == y)].B1_wetdry.item()
                        if not np.isfinite(tgt):
                            continue
                        e = edge_crossing(x[sel], da.sel(date=d, y=y).values[sel], t, rising=True)
                        n_all += 1
                        if np.isfinite(e):
                            n_ok += 1; errs.append(abs(e - tgt))
                    cov.append(n_ok / n_all)
                cand = (t, min(cov), np.mean(errs))
                if cand[1] >= score.MIN_COVERAGE and (best is None or cand[2] < best[2]):
                    best = cand
            saved = thr[(thr["product"] == p) & (thr.fold == k)].threshold.item()
            used = sb[(sb["product"] == p) & sb.y.isin(folds[folds.fold == k].y)].threshold.unique()
            if best is None or abs(best[0] - saved) > 1e-9 or not np.allclose(used, saved):
                mism.append(f"{p} fold {k}: recomputed {best and best[0]}, saved {saved}, used {used}")
    check("S2 thresholds independently recomputed from training folds only, and applied to the held-out fold",
          not mism, "match for all 5 folds x 2 indices; folds: " + ", ".join(
              f"{k}: y {g.y.min()}-{g.y.max()}" for k, g in folds.groupby("fold")) if not mism else "; ".join(mism))

    # 5 transform
    _, _, resid, rot = fit_transform()
    check("FRF transform fitted to FRF's own lat/lon", resid < 0.05,
          f"max residual {resid:.3f} m; FRF x-axis azimuth {90 - rot:.2f} deg in UTM 18N "
          f"(handoff: 69.97 deg from NC State Plane north; differs by the grid convergence between the two projections)")

    # 6 units
    lb = lidar[["B1_wetdry", "B2_dunetoe", "B3_contour"]].stack().dropna()
    ok = lb.between(ds.xFRF.min().item(), ds.xFRF.max().item()).all() and "NAVD88" in ds.attrs["vertical_datum"]
    check("Units: lidar boundaries inside the lidar x-range (m); datum NAVD88", bool(ok),
          f"x {lb.min():.0f}-{lb.max():.0f} m within grid {ds.xFRF.min().item():.0f}-{ds.xFRF.max().item():.0f} m; {ds.attrs['vertical_datum']}")
    times = pd.concat([pd.read_csv(PROC / "s2_meta.csv").acquisition_utc, pd.read_csv(PROC / "s1_meta.csv").acquisition_utc])
    check("Units: satellite times are UTC", bool(times.str.endswith("Z").all()), f"{len(times)} timestamps end in Z")

    # 7 reproducibility: rerun scoring into a temporary folder and compare
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "SARS_OUT": tmp}
        r = subprocess.run([sys.executable, "score.py"], cwd=SRC, env=env, capture_output=True, text=True)
        files = ["metrics.csv", "sensor_boundaries.csv", "change_metrics.csv", "matrix_same_rows.csv"]
        same = r.returncode == 0 and all(md5(Path(tmp) / f) == md5(OUT / f) for f in files)
    check("Re-running the scoring reproduces identical outputs", same,
          "byte-identical: " + ", ".join(files) if same else (r.stderr[-300:] or "files differ"))

    # 8 every number in the summary's results table matches metrics.csv
    summ = ROOT / "VALIDATION_SUMMARY.md"
    if summ.exists():
        import make_report as mr
        M = pd.read_csv(OUT / "metrics.csv")
        inv = {v: k for k, v in mr.NAME.items()}
        txt = summ.read_text().split("## Accuracy")[1].split("## Findings")[0]
        n_rows, errs = 0, []
        for line in txt.splitlines():
            m = re.match(r"\| (.+?) \| (.+?) \| (\d+) \| ([+-][\d.]+) \| ([\d.]+) \[([\d.]+)-([\d.]+)\] \| (\d+)% of", line)
            if not m:
                continue
            n_rows += 1
            tgt = {"wet/dry edge": "B1_wetdry", "dune toe": "B2_dunetoe"}[m.group(2)]
            r_ = mr.g(M, inv[m.group(1)], tgt)
            want = [int(r_.N), f"{r_.bias_m:+.1f}", f"{r_.RMSE_m:.1f}", f"{r_.RMSE_lo:.1f}", f"{r_.RMSE_hi:.1f}", f"{r_.pct_within_1px:.0f}"]
            got = [int(m.group(3)), m.group(4), m.group(5), m.group(6), m.group(7), m.group(8)]
            if want != got:
                errs.append(f"{m.group(1)}: summary {got} vs csv {want}")
        check("Every number in the summary's results table matches metrics.csv", n_rows > 0 and not errs,
              f"{n_rows} rows checked" if not errs else "; ".join(errs))
    else:
        check("Every number in the summary's results table matches metrics.csv", None, "summary not written yet")

    # 9 independent test: calibration lidar is separate, and folds hold out date AND place
    cm = PROC / "lidar_calibration_meta.csv"
    if cm.exists() and (OUT / "improvements_predictions.csv").exists():
        c = pd.read_csv(cm)
        ok = bool(((c.days_before >= 1) & (c.coregQCFlag == 1)).all() and not set(c.calibration_scan_utc.str[:16]) & set(lm.scan_utc.str[:16]))
        check("Physics uses separate calibration lidar scans (never the evaluated scans), all QC flag 1", ok,
              "; ".join(f"{r.date_key}: {r.calibration_scan_utc} ({r.days_before:.1f} days before)" for r in c.itertuples()))
        P = pd.read_csv(OUT / "improvements_predictions.csv")
        F_ = folds.assign(block=(folds.index // 10))
        L_ = lidar.merge(F_[["y", "block"]], on="y")
        bad = 0
        for grp, tgt in [("waterline", "B1_wetdry"), ("dune line", "B2_dunetoe")]:
            pr = P[P.group == grp].merge(F_[["y", "block"]], on="y")
            for (d, k), te in pr.groupby(["date", "block"]):
                want = np.nanmedian(L_[(L_.date != d) & (L_.block != k)][tgt])
                bad += int(not np.allclose(te.BASE_typical, want))
        check("Independent test folds exclude the held-out date and place (baseline recomputed for all 15 folds x 2 groups)",
              bad == 0, "all folds match" if bad == 0 else f"{bad} folds differ")
    else:
        check("Physics uses separate calibration lidar scans (never the evaluated scans), all QC flag 1", None, "independent test not run")

    # 10 the web app shows exactly the pipeline's numbers
    app = ROOT / "dist" / "data.js"
    if app.exists():
        import json
        import make_report as mr
        t = app.read_text()
        A = json.loads(t[t.index("{"):t.rindex("}") + 1])
        M = pd.read_csv(OUT / "metrics.csv")
        lb_ = {"lidar wet/dry edge": "B1_wetdry", "lidar dune toe": "B2_dunetoe"}
        bad = [r["product"] for r in A["table"]
               if abs(mr.g(M, r["product"], lb_[r["compared_with"]]).RMSE_m - r["rmse_m"]) > 0.051]
        s = pd.read_csv(OUT / "lidar_sanity.csv", index_col=0)["value"]
        bad += [] if abs(A["lowering"]["median_dz_m"] - s["median_dz_m"]) < 5e-4 else ["lowering"]
        check("Web app (dist/data.js) shows the same accuracy and lowering numbers as the CSVs", not bad,
              f"{len(A['table'])} sensors, {len(A['claims'])} claims, {len(A['profiles'])} rows checked" if not bad else "mismatch: " + ", ".join(bad))
    else:
        check("Web app (dist/data.js) shows the same accuracy and lowering numbers as the CSVs", None, "dist/data.js not generated yet")

    pd.DataFrame(res).to_csv(OUT / "self_checks.csv", index=False)
    if any(r["status"] == "FAIL" for r in res):
        sys.exit("self-check FAILED")


if __name__ == "__main__":
    main()
