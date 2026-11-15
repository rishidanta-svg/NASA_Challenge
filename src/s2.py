"""Sentinel-2 L2A (Earth Search on AWS, no login): pick clear scenes over the
site, compute NDWI (10 m green/NIR) and MNDWI (green 10 m / SWIR16 20 m),
sample along FRF rows. Output profiles are saved; edges are picked at scoring
time so the threshold can be tuned on training rows only."""
from pathlib import Path
import numpy as np
import pandas as pd
import rasterio
import xarray as xr
from rasterio.windows import from_bounds
from pystac_client import Client

from frf import frf_to_utm, sample_rows, ROWS10, PROC

STAC = "https://earth-search.aws.element84.com/v1"
BBOX = [-75.7534, 36.1837, -75.7503, 36.1883]
TARGET = {"2026-06": "2026-06-18", "2026-09": "2026-09-29", "2026-10": "2026-10-16"}
XGRID = np.arange(-50, 301, 1.0)
CLEAR = {4, 5, 6, 7, 11}  # vegetation, bare, water, unclassified, snow/ice (sand)


def utm_window():
    X, Y = np.meshgrid([-100, 350], [650, 1240])
    E, N = frf_to_utm(X, Y)
    return E.min() - 30, N.min() - 30, E.max() + 30, N.max() + 30


def read_band(href, bounds):
    with rasterio.Env(AWS_NO_SIGN_REQUEST="YES"):
        with rasterio.open(href) as src:
            assert src.crs.to_epsg() == 32618, src.crs
            w = from_bounds(*bounds, transform=src.transform).round_offsets().round_lengths()
            a = src.read(1, window=w).astype("float64")
            t = src.window_transform(w)
            nod = src.nodata
    if nod is not None:
        a[a == nod] = np.nan
    ny, nx = a.shape
    xs = t.c + t.a * (np.arange(nx) + 0.5)
    ys = t.f + t.e * (np.arange(ny) + 0.5)
    return xr.DataArray(a, coords={"y": ys, "x": xs}, dims=("y", "x")), abs(t.a)


def site_clear_fraction(item, bounds):
    scl, _ = read_band(item.assets["scl"].href, bounds)
    X, Y = np.meshgrid(np.arange(0, 251, 10), ROWS10)
    E, N = frf_to_utm(X, Y)
    v = scl.sel(x=xr.DataArray(E.ravel(), dims="p"), y=xr.DataArray(N.ravel(), dims="p"),
                method="nearest").values
    return float(np.isin(v, list(CLEAR)).mean())


def main():
    bounds = utm_window()
    cat = Client.open(STAC)
    chosen = []
    for key, day in TARGET.items():
        d0 = pd.Timestamp(day)
        items = cat.search(collections=["sentinel-2-l2a"], bbox=BBOX,
                           datetime=f"{(d0 - pd.Timedelta(days=12)).date()}/{(d0 + pd.Timedelta(days=12)).date()}").item_collection()
        cands = sorted(items, key=lambda it: abs(pd.Timestamp(it.properties["datetime"]).tz_localize(None) - d0))
        pick = None
        for it in cands:
            f = site_clear_fraction(it, bounds)
            print(f"  {key} {it.id} {it.properties['datetime']} site-clear={f:.2f}")
            if f >= 0.95:
                pick = (it, f)
                break
        if pick is None:
            print(f"!! {key}: no clear scene within 12 days")
            continue
        chosen.append((key, *pick))

    profs, meta = [], []
    for key, it, f in chosen:
        g, rg = read_band(it.assets["green"].href, bounds)
        n, rn = read_band(it.assets["nir"].href, bounds)
        s, rs = read_band(it.assets["swir16"].href, bounds)
        s = s.interp(x=g.x, y=g.y, method="linear")
        ndwi = (g - n) / (g + n)
        mndwi = (g - s) / (g + s)
        p_ndwi = sample_rows(ndwi, XGRID)
        p_mndwi = sample_rows(mndwi, XGRID)
        profs.append(xr.Dataset(
            {"NDWI": (("y", "x"), p_ndwi), "MNDWI": (("y", "x"), p_mndwi)},
            coords={"y": ROWS10, "x": XGRID}).expand_dims(date=[key]))
        # water brightness check: open-ocean NIR reflectance should be near 0;
        # a high value indicates sun glint or haze over the water
        Eo, No = frf_to_utm(np.array([400.0, 700.0]), np.array([800.0, 1100.0]))
        off, _ = read_band(it.assets["nir"].href, (Eo.min(), No.min(), Eo.max(), No.max()))
        boa = bool(it.properties.get("earthsearch:boa_offset_applied", False))
        nir_off = float(np.nanmedian(off.values)) * 1e-4 if boa else np.nan
        meta.append({"date_key": key, "item_id": it.id,
                     "acquisition_utc": it.properties["datetime"],
                     "boa_offset_applied": boa,
                     "offshore_nir_reflectance_median": nir_off,
                     "site_clear_fraction": f,
                     "pixel_m_green_nir": rg, "pixel_m_swir16": rs,
                     "self_href": it.get_self_href()})
    xr.concat(profs, dim="date").to_netcdf(PROC / "s2_profiles.nc")
    m = pd.DataFrame(meta)
    m.to_csv(PROC / "s2_meta.csv", index=False)
    print(m.drop(columns="self_href").to_string())


if __name__ == "__main__":
    main()
