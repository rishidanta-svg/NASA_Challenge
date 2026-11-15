"""Inputs for the independent ("strict") test, kept separate from the evaluation lidar.

1. Waves: FRF 17 m Waverider (Hs, Tp) around every image and lidar time.
   An independent instrument (not lidar), used by the runup physics.
2. Calibration lidar: ONE scan about 7 days BEFORE each evaluation scan (coregQCFlag 1),
   used only to estimate the foreshore beach slope. These scans are never scored against,
   so the physics correction no longer uses the lidar it is evaluated on.

Outputs: data/processed/waves_17m.csv, data/processed/lidar_calibration.nc,
         data/processed/lidar_calibration_meta.csv
"""
from pathlib import Path
import numpy as np
import pandas as pd
import xarray as xr

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
WAVES = ("https://chldata.erdc.dren.mil/thredds/dodsC/frf/oceanography/waves/waverider-17m/"
         "2026/FRF-ocean_waves_waverider-17m_2026{mm}.nc")
LIDAR = ("https://chldata.erdc.dren.mil/thredds/dodsC/frf/geomorphology/DEMs/duneLidarDEM/"
         "2026/FRF-geomorphology_DEMs_duneLidarDEM_2026{mm}.nc")
CAL_DAYS_BEFORE = 7


def fetch_waves():
    frames = []
    for mm in ["06", "09", "10"]:
        ds = xr.open_dataset(WAVES.format(mm=mm))
        df = pd.DataFrame({"time_utc": pd.to_datetime(ds.time.values), "Hs_m": ds.waveHs.values,
                           "Tp_s": ds.waveTp.values, "qcFlagE": ds.qcFlagE.values})
        df["gaugeDepth_m"] = float(np.nanmedian(ds.gaugeDepth.values)) if "gaugeDepth" in ds else np.nan
        df["source"] = WAVES.format(mm=mm)
        frames.append(df)
    w = pd.concat(frames, ignore_index=True)
    w = w[(w.time_utc >= "2026-06-10") & (w.time_utc <= "2026-10-20")]
    w.to_csv(PROC / "waves_17m.csv", index=False)
    print(f"waves: {len(w)} records, QC flags {sorted(w.qcFlagE.dropna().unique().tolist())}, "
          f"gauge depth {w.gaugeDepth_m.iloc[0]:.1f} m")


def fetch_calibration_lidar():
    ev = pd.read_csv(PROC / "lidar_scan_meta.csv")
    scans, meta = [], []
    for r in ev.itertuples():
        target = pd.Timestamp(r.scan_utc) - pd.Timedelta(days=CAL_DAYS_BEFORE)
        ds = xr.open_dataset(LIDAR.format(mm=f"{target.month:02d}"))
        t = pd.to_datetime(ds.time.values)
        qc = ds.coregQCFlag.values
        ok = np.where(qc == 1)[0]
        i = ok[np.argmin(np.abs((t[ok] - target).total_seconds()))]
        e = ds.elevation.isel(time=i).load()
        meta.append({"date_key": r.date_key, "evaluation_scan_utc": r.scan_utc, "calibration_scan_utc": str(t[i])[:19],
                     "days_before": round((pd.Timestamp(r.scan_utc) - t[i]).total_seconds() / 86400, 2),
                     "coregQCFlag": float(qc[i]), "opendap_url": LIDAR.format(mm=f"{target.month:02d}")})
        scans.append(e.drop_vars("time", errors="ignore").expand_dims(date=[r.date_key]))
    xr.concat(scans, dim="date").to_dataset(name="elevation").to_netcdf(PROC / "lidar_calibration.nc")
    m = pd.DataFrame(meta)
    m.to_csv(PROC / "lidar_calibration_meta.csv", index=False)
    print(m.drop(columns="opendap_url").to_string())


if __name__ == "__main__":
    fetch_waves()
    fetch_calibration_lidar()
