
"""Process locally downloaded NISAR GCOV data for the FRF study area."""

import os
import argparse
from pyproj import Transformer
import numpy as np
import pandas as pd
import xarray as xr
import h5py
from pathlib import Path

from frf import sample_rows, ROWS10, PROC
from s2 import utm_window, XGRID

GRANULE = (
    "NISAR_L2_PR_GCOV_024_069_D_070_4005_DHDH_A_"
    "20260630T235334_20260630T235409_P05023_N_F_J_001"
)

RAW = Path(os.getenv("NISAR_RAW_DIR", Path(__file__).resolve().parents[1] / "data" / "raw" / "nisar"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', default=os.getenv('NISAR_INPUT'), help='Path to the June30 GCOV HDF5 input')
    parser.add_argument('--raw-dir', type=Path, default=RAW, help='Directory searched when --input is omitted')
    parser.add_argument('--output-dir', type=Path, default=PROC, help='Destination for profiles and metadata')
    args = parser.parse_args()
    selected = args.input
    granule = os.getenv("NISAR_GRANULE", GRANULE)
    files = [Path(selected)] if selected else list(args.raw_dir.glob("*.h5"))

    if not files:
        raise FileNotFoundError(f"No NISAR HDF5 file found in {RAW}")

    file = next((f for f in files if granule in f.name), None)

    if file is None:
        raise FileNotFoundError(f"Expected granule not found in {RAW}")

    if granule != GRANULE:
        raise ValueError("This single-epoch reader currently supports only the documented June30 granule; use the geospatial pipeline for June18/October16.")
    print("Reading:", file.name)

    bounds = utm_window()
    print("Study area UTM bounds:", bounds)

    grid = "science/LSAR/GCOV/grids/frequencyA"

    with h5py.File(file, "r") as f:

        g = f[grid]

        epsg = int(g["projection"][()])
        if epsg != 32618:
            bounds = Transformer.from_crs(32618, epsg, always_xy=True).transform_bounds(*bounds, densify_pts=21)
        xs = g["xCoordinates"][:]
        ys = g["yCoordinates"][:]

        # Identify only the pixels covering our study area.
        ix = np.where(
            (xs >= bounds[0]) & (xs <= bounds[2])
        )[0]

        iy = np.where(
            (ys >= bounds[1]) & (ys <= bounds[3])
        )[0]

        if len(ix) == 0 or len(iy) == 0:
            raise ValueError("NISAR raster does not overlap the study area")

        x_slice = slice(ix.min(), ix.max() + 1)
        y_slice = slice(iy.min(), iy.max() + 1)

        print("Extracted raster shape:",
              len(iy), "x", len(ix))

        profiles = {}

        for pol, dataset in [
            ("HH", "HHHH"),
            ("HV", "HVHV")
        ]:

            print("Extracting", pol)

            # Read only the site window, not the entire raster.
            values = g[dataset][y_slice, x_slice].astype("float64")

            values[~np.isfinite(values)] = np.nan
            values[values <= 0] = np.nan

            db = 10 * np.log10(values)

            da = xr.DataArray(
                db,
                coords={
                    "y": ys[y_slice],
                    "x": xs[x_slice]
                },
                dims=("y", "x")
            )

            profiles[pol] = da

            print(
                pol,
                "valid pixel fraction:",
                round(float(np.isfinite(db).mean()), 4)
            )

        spacing = (
            abs(float(xs[1] - xs[0])),
            abs(float(ys[1] - ys[0]))
        )

        epsg = int(g["projection"][()])

    print("Pixel spacing:", spacing)
    print("Projection:", epsg)

    print("Sampling FRF transects...")

    result = xr.Dataset(
        {
            pol: (
                ("y", "x"),
                sample_rows(da, XGRID, epsg=epsg)
            )
            for pol, da in profiles.items()
        },
        coords={
            "y": ROWS10,
            "x": XGRID
        }
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)

    output = args.output_dir / "nisar_profiles.nc"

    result.expand_dims(date=["2026-06"]).to_netcdf(output)

    metadata = pd.DataFrame([{
    "date_key": "2026-06",
    "granule": GRANULE,
    "begin_utc": "2026-06-30T23:53:34Z",
    "track": 69,
    "direction": "descending",
    "frame": 70,
    "pixel_m_x": spacing[0],
    "pixel_m_y": spacing[1],
    "epsg": epsg
    }])

    metadata.to_csv(args.output_dir / "nisar_meta.csv", index=False)

    print("\nSUCCESS")
    print("Saved:", output)
    print("Profile dimensions:", dict(result.sizes))


if __name__ == "__main__":
    main()
