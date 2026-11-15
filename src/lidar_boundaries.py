"""Extract lidar ground-truth boundaries for every alongshore row.

Boundaries (each a cross-shore position xFRF, metres):
  B1_wetdry  Seaward limit of valid lidar ground returns. FRF's automated filter
             removes water/swash, so this is the landward edge of the wet zone at
             scan time. It is NOT the still-water line (see checkpoint notes).
  B2_dunetoe Dune toe: point of maximum vertical distance BELOW the straight
             chord joining the dune crest (max elevation) and the seaward data
             edge (chord method, cf. Mull & Ruggiero 2014). Only computed where
             the dune face is inside the grid (crest >= DUNE_MIN_Z).
  B3_contour Seaward-most crossing of a fixed NAVD88 contour, chosen by rule:
             lowest 0.25 m step present in >= 90% of rows on all dates.
Also reports MHW (0.36 m NAVD88, NOAA 8651370) crossing where it exists.

Rows are analysed at 1 m (native) and summarised on the 10 m alongshore rows
y = 700, 710, ... 1190 by taking the median over y in [y-5, y+5).
"""
from pathlib import Path
import numpy as np
import pandas as pd
import xarray as xr

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)

MHW_NAVD88 = 6.69 - 6.33  # NOAA datums, station 8651370, epoch 1983-2001
MAX_GAP_M = 3.0           # do not interpolate a crossing across gaps wider than this
DUNE_MIN_Z = 4.0          # crest must be at least this high for a dune toe
ROWS10 = np.arange(700, 1191, 10)
MAX_FACE_GAP_M = 5.0      # max gap allowed on the dune face between crest and toe
REQUIRE_INTERIOR_CREST = True
MIN_1M = 5              # min valid 1 m rows per 10 m row


def clean_profile(x, z):
    ok = np.isfinite(z)
    return x[ok], z[ok]


def contour_crossing(x, z, z0):
    """Seaward-most x where the profile crosses z0 going seaward (high -> low)."""
    for i in range(len(x) - 1, 0, -1):
        a, b = z[i - 1], z[i]
        if a >= z0 > b and (x[i] - x[i - 1]) <= MAX_GAP_M:
            return x[i - 1] + (a - z0) / (a - b) * (x[i] - x[i - 1])
    return np.nan


def dune_toe(x, z):
    if len(x) < 10:
        return np.nan
    zs = pd.Series(z).rolling(3, center=True, min_periods=1).median().to_numpy()
    ic = int(np.argmax(zs))
    if zs[ic] < DUNE_MIN_Z or ic >= len(x) - 5:
        return np.nan
    # the crest must be a real peak inside the data, not the landward edge of the grid
    if REQUIRE_INTERIOR_CREST and ic < 2:
        return np.nan
    xe, ze = x[ic:], zs[ic:]
    chord = ze[0] + (ze[-1] - ze[0]) * (xe - xe[0]) / (xe[-1] - xe[0])
    below = chord - ze
    j = int(np.argmax(below))
    if below[j] <= 0.05:  # no meaningful concave break
        return np.nan
    # the dune face must actually be observed: no big data gap between crest and toe
    if j > 0 and np.max(np.diff(xe[: j + 1])) > MAX_FACE_GAP_M:
        return np.nan
    return xe[j]


def per_metre_rows(elev, x, y, contour_z):
    rows = []
    for k, yy in enumerate(y):
        xc, zc = clean_profile(x, elev[k])
        if len(xc) == 0:
            rows.append((yy, np.nan, np.nan, np.nan, np.nan))
            continue
        rows.append((yy, xc[-1], dune_toe(xc, zc),
                     contour_crossing(xc, zc, contour_z),
                     contour_crossing(xc, zc, MHW_NAVD88)))
    return pd.DataFrame(rows, columns=["y1", "B1_wetdry", "B2_dunetoe", "B3_contour", "MHW"])


def choose_contour(ds):
    x = ds.xFRF.values
    for z0 in np.arange(0.25, 3.01, 0.25):
        ok_all = True
        for d in ds.date.values:
            e = ds.elevation.sel(date=d).values
            hits = sum(np.isfinite(contour_crossing(*clean_profile(x, r), z0)) for r in e)
            if hits / len(e) < 0.9:
                ok_all = False
                break
        if ok_all:
            return float(z0)
    raise RuntimeError("no contour meets the coverage rule")


def main():
    ds = xr.open_dataset(PROC / "lidar_scans.nc")
    x, y = ds.xFRF.values, ds.yFRF.values
    z0 = choose_contour(ds)
    print(f"B3 contour chosen by rule: {z0:.2f} m NAVD88; MHW = {MHW_NAVD88:.2f} m NAVD88")
    out = []
    for d in ds.date.values:
        df = per_metre_rows(ds.elevation.sel(date=d).values, x, y, z0)
        df["row_y"] = (np.floor((df.y1 - 695) / 10) * 10 + 700).astype(int)
        g = df[df.row_y.isin(ROWS10)].groupby("row_y")
        agg = g[["B1_wetdry", "B2_dunetoe", "B3_contour", "MHW"]].median()
        n = g[["B1_wetdry", "B2_dunetoe", "B3_contour", "MHW"]].count().add_suffix("_n1m")
        # a 10 m row needs >= MIN_1M of its 10 one-metre rows to be valid
        for col in ["B1_wetdry", "B2_dunetoe", "B3_contour", "MHW"]:
            agg.loc[n[col + "_n1m"] < MIN_1M, col] = np.nan
        a = agg.join(n).reset_index().rename(columns={"row_y": "y"})
        a.insert(0, "date", d)
        out.append(a)
    res = pd.concat(out, ignore_index=True)
    res["B3_contour_z"] = z0
    res["MHW_z"] = MHW_NAVD88
    res.to_csv(OUT / "lidar_boundaries.csv", index=False, float_format="%.2f")
    summ = res.groupby("date")[["B1_wetdry", "B2_dunetoe", "B3_contour", "MHW"]].agg(["median", "count"])
    print(summ.round(1).to_string())
    return res


if __name__ == "__main__":
    main()
