"""Fetch the three matched FRF dune-lidar scans and NOAA water levels.

Outputs (small, committed):
  data/processed/lidar_scans.nc   elevation(date, yFRF, xFRF) + QC metadata
  data/processed/tide_8651370.csv 6-min water level, NAVD88, UTC
"""
from pathlib import Path
import io
import numpy as np
import pandas as pd
import requests
import xarray as xr

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)

BASE = ("https://chldata.erdc.dren.mil/thredds/dodsC/frf/geomorphology/DEMs/"
        "duneLidarDEM/2026/FRF-geomorphology_DEMs_duneLidarDEM_2026{mm}.nc")

# Lidar reference times from the team's site-selection document (UTC)
TARGETS = {
    "2026-06": "2026-06-19T00:31:04",
    "2026-09": "2026-09-29T10:33:04",
    "2026-10": "2026-10-16T23:33:04",
}
# NISAR pass mid-times (UTC), used for the tide level at the satellite pass
NISAR_PASS = {
    "2026-06": "2026-06-18T23:53:52",
    "2026-09": "2026-09-29T10:14:26",
    "2026-10": "2026-10-16T23:53:49",
}


def fetch_lidar():
    scans, meta = [], []
    for key, t in TARGETS.items():
        url = BASE.format(mm=t[5:7])
        ds = xr.open_dataset(url)
        target = np.datetime64(t)
        idx = int(np.argmin(np.abs(ds.time.values - target)))
        actual = ds.time.values[idx]
        gap_s = abs((actual - target) / np.timedelta64(1, "s"))
        one = ds.isel(time=idx)
        elev = one.elevation.load()
        meta.append({
            "date_key": key,
            "requested_utc": t,
            "scan_utc": str(actual)[:19],
            "gap_s": gap_s,
            "coregQCFlag": float(one.coregQCFlag),
            "rmsReflectorError_m": float(one.rmsReflectorError),
            "assessmentPlanesOffset_m": float(one.assessmentPlanesOffset),
            "valid_cells": int(np.isfinite(elev.values).sum()),
            "opendap_url": url,
        })
        scans.append(elev.drop_vars("time", errors="ignore").expand_dims(date=[key]))
        lat, lon = ds.latitude.load(), ds.longitude.load()
        ds.close()
    out = xr.concat(scans, dim="date").to_dataset(name="elevation")
    out["latitude"], out["longitude"] = lat, lon
    out.attrs["source"] = "USACE FRF duneLidarDEM (THREDDS OPeNDAP)"
    out.attrs["vertical_datum"] = "NAVD88 (geoid12b)"
    out.to_netcdf(OUT / "lidar_scans.nc")
    m = pd.DataFrame(meta)
    m.to_csv(OUT / "lidar_scan_meta.csv", index=False)
    print(m.to_string())


def fetch_tide():
    frames = []
    for begin, end in [("20260618", "20260619"), ("20260928", "20260929"),
                       ("20261016", "20261017")]:
        r = requests.get(
            "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter",
            params=dict(begin_date=begin, end_date=end, station="8651370",
                        product="water_level", datum="NAVD", units="metric",
                        time_zone="gmt", format="csv",
                        application="space_apps_validation"),
            timeout=60)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = [c.strip() for c in df.columns]
        frames.append(df)
    tide = pd.concat(frames, ignore_index=True)
    tide.to_csv(OUT / "tide_8651370.csv", index=False)
    t = pd.to_datetime(tide["Date Time"])
    wl = pd.to_numeric(tide["Water Level"], errors="coerce")
    rows = []
    for key in TARGETS:
        for label, when in [("nisar_pass", NISAR_PASS[key]), ("lidar_scan", TARGETS[key])]:
            w = pd.Timestamp(when)
            # compare in seconds since epoch (avoids us/ns unit mismatch)
            ts = (t - pd.Timestamp("1970-01-01")).dt.total_seconds().to_numpy()
            ws = (w - pd.Timestamp("1970-01-01")).total_seconds()
            ok = wl.notna().to_numpy()
            if ws < ts[ok].min() or ws > ts[ok].max():
                raise ValueError(f"{when} outside tide record")
            val = float(np.interp(ws, ts[ok], wl.to_numpy()[ok]))
            near = (t - w).abs().min()
            rows.append({"date_key": key, "event": label, "utc": when,
                         "water_level_navd88_m": val,
                         "nearest_obs_gap_min": near.total_seconds() / 60})
    tl = pd.DataFrame(rows)
    tl.to_csv(OUT / "tide_at_events.csv", index=False)
    print(tl.to_string())


if __name__ == "__main__":
    fetch_tide()
    fetch_lidar()
