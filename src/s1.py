"""Sentinel-1 RTC (Microsoft Planetary Computer, anonymous signing, no login).
Same relative orbit (106, ascending) on all dates so geometry is constant.
Samples VV and VH backscatter (dB) along FRF rows."""
import numpy as np
import pandas as pd
import rasterio
import xarray as xr
from rasterio.windows import from_bounds
from pystac_client import Client
import planetary_computer as pc

from frf import sample_rows, ROWS10, PROC
from s2 import utm_window, XGRID

SCENES = {  # date_key -> STAC item id (relative orbit 106, nearest to lidar date)
    "2026-06": "S1A_IW_GRDH_1SDV_20260623T225806_20260623T225835_065103_0834CA_rtc",
    "2026-09": "S1D_IW_GRDH_1SDV_20261004T225729_20261004T225759_004872_009297_rtc",
    "2026-10": "S1D_IW_GRDH_1SDV_20261016T225729_20261016T225759_005047_0098AC_rtc",
}


def read(href, bounds):
    with rasterio.open(href) as src:
        if src.crs.to_epsg() != 32618:
            raise ValueError(f"unexpected CRS {src.crs}")
        w = from_bounds(*bounds, transform=src.transform).round_offsets().round_lengths()
        a = src.read(1, window=w).astype("float64")
        t = src.window_transform(w)
        nod = src.nodata
    if nod is not None:
        a[a == nod] = np.nan
    a[a <= 0] = np.nan
    ny, nx = a.shape
    xs = t.c + t.a * (np.arange(nx) + 0.5)
    ys = t.f + t.e * (np.arange(ny) + 0.5)
    return xr.DataArray(10 * np.log10(a), coords={"y": ys, "x": xs}, dims=("y", "x")), abs(t.a)


def main():
    cat = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=pc.sign_inplace)
    bounds = utm_window()
    profs, meta = [], []
    for key, iid in SCENES.items():
        it = cat.get_collection("sentinel-1-rtc").get_item(iid)
        it = pc.sign(it)
        vv, res = read(it.assets["vv"].href, bounds)
        vh, _ = read(it.assets["vh"].href, bounds)
        profs.append(xr.Dataset({"VV": (("y", "x"), sample_rows(vv, XGRID)),
                                 "VH": (("y", "x"), sample_rows(vh, XGRID))},
                                coords={"y": ROWS10, "x": XGRID}).expand_dims(date=[key]))
        p = it.properties
        meta.append({"date_key": key, "item_id": iid, "acquisition_utc": p["datetime"],
                     "orbit_state": p.get("sat:orbit_state"),
                     "relative_orbit": p.get("sat:relative_orbit"), "pixel_m": res,
                     "url": f"https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-1-rtc/items/{iid}"})
    xr.concat(profs, dim="date").to_netcdf(PROC / "s1_profiles.nc")
    m = pd.DataFrame(meta)
    m.to_csv(PROC / "s1_meta.csv", index=False)
    print(m.drop(columns="url").to_string())
    pr = xr.concat(profs, dim="date")
    for d in pr.date.values:
        for v in ["VV", "VH"]:
            med = pr[v].sel(date=d).median("y")
            print(d, v, " ".join(f"{x:.0f}:{val:.1f}" for x, val in zip(XGRID[::15], med.values[::15])))


if __name__ == "__main__":
    main()
