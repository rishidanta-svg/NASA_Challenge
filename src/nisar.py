"""NISAR L2 GCOV (ASF, needs NASA Earthdata Login via ~/.netrc).
Reads only the site window from the HDF5 over HTTPS (no full download),
converts HH and HV backscatter to dB and samples along FRF rows."""
import os
import numpy as np
import pandas as pd
import xarray as xr
import h5py
import earthaccess
from pyproj import Transformer

from frf import sample_rows, ROWS10, PROC
from s2 import utm_window, XGRID

# June/October: from the team's site-selection document (descending track 069, frame 070).
# September: found by searching CMR (NISAR_L2_GCOV_PROVISIONAL_V1) for 2026-09-28..10-01 over the
# site; it is an ASCENDING pass (track 162, frame 020), i.e. a different viewing geometry.
GRANULES = {"2026-06": "G4250721321-ASF", "2026-09": "G4331248374-ASF", "2026-10": "G4376256706-ASF"}


def parse_ur(ur):
    """NISAR_L2_PR_GCOV_<cycle>_<track>_<A|D>_<frame>_... -> track, direction, frame"""
    p = ur.split("_")
    return dict(track=int(p[5]), direction={"A": "ascending", "D": "descending"}[p[6]], frame=int(p[7]))


def read_window(f, bounds_utm18):
    grid = "science/LSAR/GCOV/grids/frequencyA"
    g = f[grid]
    xs, ys = g["xCoordinates"][:], g["yCoordinates"][:]
    proj = g["projection"]
    epsg = int(proj[()]) if proj.shape == () else int(proj.attrs.get("epsg_code", 0))
    if not epsg:
        raise ValueError("could not read the GCOV projection EPSG code")
    # convert the UTM-18N site window into the file's own projection
    t = Transformer.from_crs("EPSG:32618", f"EPSG:{epsg}", always_xy=True)
    cx, cy = t.transform([bounds_utm18[0], bounds_utm18[2], bounds_utm18[0], bounds_utm18[2]],
                         [bounds_utm18[1], bounds_utm18[1], bounds_utm18[3], bounds_utm18[3]])
    bounds = (min(cx), min(cy), max(cx), max(cy))
    ix = np.where((xs >= bounds[0]) & (xs <= bounds[2]))[0]
    iy = np.where((ys >= bounds[1]) & (ys <= bounds[3]))[0]
    if len(ix) < 3 or len(iy) < 3:
        raise ValueError("site window is outside this GCOV frame")
    sl = (slice(iy.min(), iy.max() + 1), slice(ix.min(), ix.max() + 1))
    out = {}
    for pol, ds in [("HH", "HHHH"), ("HV", "HVHV")]:
        a = g[ds][sl].astype("float64")
        a[a <= 0] = np.nan
        out[pol] = xr.DataArray(10 * np.log10(a), coords={"y": ys[sl[0]], "x": xs[sl[1]]}, dims=("y", "x"))
    spacing = float(abs(xs[1] - xs[0])), float(abs(ys[1] - ys[0]))
    return out, spacing, epsg


def main():
    auth = earthaccess.login(strategy="environment") if os.environ.get("EARTHDATA_TOKEN") or os.environ.get("EARTHDATA_USERNAME") \
        else earthaccess.login(strategy="netrc")
    if not auth or not auth.authenticated:
        raise SystemExit("Earthdata login failed: run src/earthdata_login.py first")
    bounds = utm_window()
    profs, meta = [], []
    for key, cid in GRANULES.items():
        res = earthaccess.search_data(concept_id=cid)
        assert len(res) == 1, f"{cid}: {len(res)} results"
        gr = res[0]
        links = [u for u in gr.data_links(access="external")
                 if u.startswith("https://") and u.endswith(".h5") and "QA_STATS" not in u and "PRIVATE" not in u]
        assert len(links) == 1, f"{cid}: expected one science .h5 link, got {links}"
        url = links[0]
        fobj = earthaccess.open([url])[0]
        with h5py.File(fobj, "r") as f:
            bands, spacing, epsg = read_window(f, bounds)
        profs.append(xr.Dataset({p: (("y", "x"), sample_rows(da, XGRID, epsg=epsg)) for p, da in bands.items()},
                                coords={"y": ROWS10, "x": XGRID}).expand_dims(date=[key]))
        t = gr["umm"]["TemporalExtent"]["RangeDateTime"]
        meta.append({"date_key": key, "concept_id": cid, "granule_ur": gr["umm"]["GranuleUR"],
                     **parse_ur(gr["umm"]["GranuleUR"]),
                     "begin_utc": t["BeginningDateTime"], "end_utc": t["EndingDateTime"],
                     "pixel_m_x": spacing[0], "pixel_m_y": spacing[1], "epsg": epsg, "url": url})
    xr.concat(profs, dim="date").to_netcdf(PROC / "nisar_profiles.nc")
    m = pd.DataFrame(meta)
    m.to_csv(PROC / "nisar_meta.csv", index=False)
    print(m.drop(columns="url").to_string())


if __name__ == "__main__":
    main()
