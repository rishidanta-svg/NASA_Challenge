"""FRF coordinate transform and profile tools shared by all sensors.

The transform UTM18N (EPSG:32618) <-> FRF (x cross-shore, y alongshore) is fitted
by least squares to the latitude/longitude arrays shipped in the FRF lidar file,
so it is derived from FRF's own data rather than typed in.
"""
from functools import lru_cache
from pathlib import Path
import numpy as np
import pandas as pd
import xarray as xr
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
ROWS10 = np.arange(700, 1191, 10)
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32618", always_xy=True)
TO_LL = Transformer.from_crs("EPSG:32618", "EPSG:4326", always_xy=True)


@lru_cache(maxsize=1)
def fit_transform():
    ds = xr.open_dataset(PROC / "lidar_scans.nc")
    X, Y = np.meshgrid(ds.xFRF.values, ds.yFRF.values)
    lat, lon = ds.latitude.values, ds.longitude.values
    if np.nanmean(lon) > 0:  # file notes longitude may be stored positive-west
        lon = -lon
    E, N = TO_UTM.transform(lon.ravel(), lat.ravel())
    A = np.column_stack([X.ravel(), Y.ravel(), np.ones(X.size)])
    coefE, *_ = np.linalg.lstsq(A, E, rcond=None)
    coefN, *_ = np.linalg.lstsq(A, N, rcond=None)
    resid = np.hypot(A @ coefE - E, A @ coefN - N)
    # rotation of the FRF x-axis from UTM east, degrees (counter-clockwise)
    rot = np.degrees(np.arctan2(coefN[0], coefE[0]))
    M = np.array([[coefE[0], coefE[1]], [coefN[0], coefN[1]]])
    off = np.array([coefE[2], coefN[2]])
    return M, off, float(resid.max()), float(rot)


def frf_to_utm(x, y):
    M, off, *_ = fit_transform()
    xy = np.stack([np.asarray(x, float).ravel(), np.asarray(y, float).ravel()])
    en = M @ xy + off[:, None]
    return en[0].reshape(np.shape(x)), en[1].reshape(np.shape(x))


ROW_OFFSETS = np.arange(-5, 5)  # 10 one-metre lines per 10 m row, same band as the lidar


def sample_rows(da, x_grid, rows=ROWS10, method="linear", epsg=32618):
    """Sample a 2-D projected raster (xarray with x/y in metres of `epsg`) along
    FRF rows. Each 10 m row is the median of the 10 one-metre lines y-5..y+4,
    matching how the lidar rows are built. Returns (len(rows), len(x_grid))."""
    out = []
    for dy in ROW_OFFSETS:
        X, Y = np.meshgrid(x_grid, rows + dy)
        E, N = frf_to_utm(X, Y)
        if epsg != 32618:
            E, N = Transformer.from_crs("EPSG:32618", f"EPSG:{epsg}", always_xy=True).transform(E, N)
        pts = da.interp(x=xr.DataArray(E.ravel(), dims="p"),
                        y=xr.DataArray(N.ravel(), dims="p"), method=method)
        out.append(pts.values.reshape(X.shape))
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return np.nanmedian(np.stack(out), axis=0)


def edge_crossing(x, v, thr, rising=True):
    """First crossing of threshold thr moving seaward (increasing x).
    rising=True: v goes from < thr (land) to >= thr (water)."""
    s = v - thr if rising else thr - v
    ok = np.isfinite(s)
    x, s = x[ok], s[ok]
    for i in range(1, len(x)):
        if s[i - 1] < 0 <= s[i]:
            return x[i - 1] + (0 - s[i - 1]) / (s[i] - s[i - 1]) * (x[i] - x[i - 1])
    return np.nan


RADAR_SMOOTH_M = 11  # documented smoothing: running mean over 11 m along x (about one 10 m pixel)


def max_gradient_edge(x, v, xmin, xmax, sign=-1, smooth_m=RADAR_SMOOTH_M):
    """x of the strongest seaward drop (sign=-1) or rise (+1) in v within [xmin, xmax].
    v is first smoothed with a running mean of `smooth_m` metres (x is on a 1 m grid).
    Bilinear sampling of coarse pixels gives flat gradient plateaus, so the edge is the
    MIDPOINT of the contiguous run of samples within 2% of the peak gradient."""
    ok = np.isfinite(v)
    vs = pd.Series(np.where(ok, v, np.nan)).rolling(smooth_m, center=True, min_periods=smooth_m // 2 + 1).mean().to_numpy()
    sel = np.isfinite(vs) & (x >= xmin) & (x <= xmax)
    if sel.sum() < 5:
        return np.nan
    xs, vv = x[sel], vs[sel]
    g = np.gradient(vv, xs) * sign
    k = int(np.argmax(g))
    if g[k] <= 0:
        return np.nan
    lo = hi = k
    while lo > 0 and g[lo - 1] >= 0.98 * g[k]:
        lo -= 1
    while hi < len(g) - 1 and g[hi + 1] >= 0.98 * g[k]:
        hi += 1
    return float((xs[lo] + xs[hi]) / 2)


if __name__ == "__main__":
    M, off, r, rot = fit_transform()
    print("FRF->UTM fit max residual (m):", round(r, 3))
    print("FRF x-axis direction, degrees CCW from UTM east:", round(rot, 2))
    print("scale x, y:", round(np.hypot(*M[:, 0]), 5), round(np.hypot(*M[:, 1]), 5))
