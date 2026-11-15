import os
"""Sanity checks on the lidar: June->Oct elevation change and profile plots."""
from pathlib import Path
import numpy as np
import pandas as pd
import xarray as xr
import plotly.graph_objects as go
from plotly.subplots import make_subplots

ROOT = Path(__file__).resolve().parents[1]
PROC, OUT = ROOT / "data" / "processed", ROOT / "outputs"
FIG = OUT / "figures"
FIG.mkdir(parents=True, exist_ok=True)

ds = xr.open_dataset(PROC / "lidar_scans.nc")
meta = pd.read_csv(PROC / "lidar_scan_meta.csv")
assert (meta.coregQCFlag == 1).all(), "a scan is not QC flag 1"

dz = (ds.elevation.sel(date="2026-10") - ds.elevation.sel(date="2026-06")).values
common = np.isfinite(dz)
# QC flag 1 bounds RMS reflector error and plane offsets at < 0.1 m, so changes
# within +-0.1 m are treated as not detectable.
thr = 0.1
rows = {
    "common_cells_1m2": int(common.sum()),
    "median_dz_m": float(np.nanmedian(dz)),
    "mean_dz_m": float(np.nanmean(dz)),
    "p10_dz_m": float(np.nanpercentile(dz, 10)),
    "p90_dz_m": float(np.nanpercentile(dz, 90)),
    "detect_threshold_m": thr,
    "area_lowering_gt_thr_m2": int(np.sum(dz < -thr)),
    "area_raising_gt_thr_m2": int(np.sum(dz > thr)),
    "max_rmsReflectorError_m": float(meta.rmsReflectorError_m.max()),
}
pd.Series(rows).to_csv(OUT / "lidar_sanity.csv", header=["value"])
print(pd.Series(rows).round(3).to_string())

# Profile plots with extracted boundaries for visual QA
b = pd.read_csv(OUT / "lidar_boundaries.csv")
x = ds.xFRF.values
ys = [750, 900, 1000, 1150]
fig = make_subplots(rows=2, cols=2, subplot_titles=[f"y = {y} m" for y in ys])
colors = {"2026-06": "#2563eb", "2026-09": "#9ca3af", "2026-10": "#dc2626"}
for i, yy in enumerate(ys):
    r, c = i // 2 + 1, i % 2 + 1
    for d, col in colors.items():
        z = ds.elevation.sel(date=d, yFRF=yy).values
        fig.add_scatter(x=x, y=z, mode="lines", line=dict(color=col), name=d,
                        showlegend=(i == 0), row=r, col=c)
        bb = b[(b.date == d) & (b.y == yy)].iloc[0]
        for key, sym in [("B1_wetdry", "triangle-down"), ("B2_dunetoe", "circle"), ("B3_contour", "square")]:
            if np.isfinite(bb[key]):
                zz = np.interp(bb[key], x[np.isfinite(z)], z[np.isfinite(z)])
                fig.add_scatter(x=[bb[key]], y=[zz], mode="markers",
                                marker=dict(color=col, symbol=sym, size=9),
                                name=key, showlegend=(i == 0 and d == "2026-06"), row=r, col=c)
fig.update_layout(height=700, width=1100, title="Lidar profiles with extracted boundaries (QA)")
fig.update_xaxes(title="xFRF cross-shore (m)", range=[40, 110])
fig.update_yaxes(title="elevation (m NAVD88)")
for attempt in range(0 if os.getenv("SARS_SKIP_PNG") == "1" else 3):  # kaleido sometimes fails on its first render in a new process
    try:
        fig.write_image(FIG / "qa_lidar_profiles.png", scale=1)
        break
    except Exception:
        if attempt == 2:
            raise
print("PNG skipped" if os.getenv("SARS_SKIP_PNG") == "1" else "saved", FIG / "qa_lidar_profiles.png")
