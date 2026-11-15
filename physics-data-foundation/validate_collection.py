"""Validate Duck outputs against native scenes, handoff values, and time-selection rules."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import netCDF4 as nc
import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
import xarray as xr

from acquire_satellite import BANDS
from build_geospatial import write_json
from build_environment import DEG, TOLERANCE


def check(condition, label):
    if not condition:
        raise ValueError(label)


def values_at_centers(path, x, y):
    with rasterio.open(path) as src:
        tr = Transformer.from_crs(32618, src.crs, always_xy=True)
        sx, sy = tr.transform(x, y)
        return np.asarray([float(v[0]) for v in src.sample(zip(sx, sy))])


def verify_release_files(output):
    root = output.resolve()
    checksum = root / "SHA256SUMS"
    expected = set()
    for line in checksum.read_text(encoding="utf-8").splitlines():
        sha, name = line.split("  ", 1)
        path = (root / name).resolve()
        check(path.is_relative_to(root) and path not in expected, f"Invalid checksum path: {name}")
        with path.open("rb") as stream:
            check(hashlib.file_digest(stream, "sha256").hexdigest() == sha, f"Checksum mismatch: {name}")
        expected.add(path)
    actual = {p for p in root.rglob("*") if p.is_file() and p != checksum}
    check(expected == actual, "Release file inventory differs from SHA256SUMS")
    return len(expected)


def validate(package, output=None, processed_only=False):
    output = output if output is not None else package / "data/unified"
    verified_files = verify_release_files(output) if processed_only else None
    root = package / "data/raw/sentinel_native"
    env_raw = package / "data/raw/environment_native"
    upstream = package / "data/source_handoff/data/processed"
    comparison = None if processed_only else next(upstream.glob("comparison-*"))
    manifest = json.loads((output / "acquisition_manifest.json").read_text())
    pairs = json.loads((output / "cross_date_pairs.json").read_text())
    records = manifest["observations"]
    ds = xr.open_dataset(output / "duck_observations.nc")
    cross = xr.open_dataset(output / "cross_date.nc")
    check(dict(ds.sizes) == {"observation": 28, "y": 52, "x": 29}, "Unexpected acquisition or spatial dimensions")
    check(Counter(r["sensor"] for r in records) ==
          {"Sentinel-1": 6, "Sentinel-2": 18, "NISAR": 2, "USACE LiDAR": 2}, "Sensor counts")
    check(Counter(r["group"] for r in records) == {"june": 5, "october": 4, "additional": 19}, "Group counts")
    for dataset in (ds, cross):
        check(rasterio.crs.CRS.from_wkt(dataset.spatial_ref.attrs["crs_wkt"]).to_epsg() == 32618,
              "NetCDF coordinate system")
        np.testing.assert_array_equal(dataset.x.values, 432255 + 10 * np.arange(29))
        np.testing.assert_array_equal(dataset.y.values, 4005095 - 10 * np.arange(52))
    dictionary = json.loads((output / "variable_dictionary.json").read_text())
    for variable, definition in dictionary.items():
        check(ds[variable].attrs["units"] == definition["units"], f"Units differ for {variable}")
    for data in (ds, cross):
        for variable in data.data_vars:
            if variable.endswith("_valid") or variable == "all_sensor_valid_overlap":
                values = data[variable].values
                check(np.isin(values[np.isfinite(values)], [0, 1]).all(), f"Invalid mask values: {variable}")
    x, y = np.meshgrid(ds.x.values, ds.y.values)
    inside = ds.study_area_fraction.values > 0
    check(int(inside.sum()) == 1450, "Study-area intersection count")
    check((x[0, 0], y[0, 0]) == (432255., 4005095.), "First NISAR grid center")
    check((x[-1, -1], y[-1, -1]) == (432535., 4004585.), "Last NISAR grid center")
    to_geo = Transformer.from_crs(32618, 4326, always_xy=True)
    lon, lat = to_geo.transform(x, y)
    np.testing.assert_allclose(ds.latitude.values, lat, atol=1e-10, rtol=0)
    np.testing.assert_allclose(ds.longitude.values, lon, atol=1e-10, rtol=0)
    check(ds.sizes["observation"] == len(records), "Acquisition dimension vs provenance")
    check(len(set(ds.id.values)) == len(records), "Unique source IDs")
    expected_times = pd.to_datetime([r["timestamp_utc"] for r in records], utc=True, format="mixed").tz_localize(None)
    np.testing.assert_array_equal(ds.time.values, expected_times.to_numpy(dtype="datetime64[ns]"))
    native_points = 0
    for i, obs in enumerate(records):
        sample = ds.isel(observation=i)
        check(sample.id.item() == obs["id"], "Observation ID join")
        present = obs["variables"]
        with rasterio.open(output / obs["aligned_geotiff"]) as out:
            check(out.crs.to_epsg() == 32618 and list(out.transform)[:6] == manifest["grid"]["affine"],
                  "Observation GeoTIFF affine and CRS")
            check(list(out.descriptions) == present, "GeoTIFF value dictionary")
            for j, variable in enumerate(present, 1):
                np.testing.assert_array_equal(out.read(j), sample[variable].values)
                check(np.isfinite(sample[variable].values[~inside]).sum() == 0, "Outside-AOI values")
        for variable, arr in ds.data_vars.items():
            if arr.dims == ("observation", "y", "x") and variable not in present:
                check(np.isnan(sample[variable].values).all(), f"Missing variables must remain empty: {variable}")
        if obs["sensor"] == "Sentinel-2":
            for key in BANDS:
                data = sample[f"s2_{key}_reflectance"].values
                valid = np.isfinite(data)
                check(np.array_equal(sample[f"s2_{key}_reflectance_valid"].values[inside] == 1, valid[inside]),
                      f"Optical validity disagrees for {key}")
                check(np.all(sample.s2_clear.values[valid] == 1), "Optical cloud screening")
                if processed_only or not valid.any():
                    continue
                dn = values_at_centers(root / obs["id"] / f"{key}_dn.tif", x[valid], y[valid])
                physical = (dn + obs["offset_dn"][key]) / obs["quantification"]
                np.testing.assert_allclose(data[valid], physical, atol=2e-7, rtol=1e-6)
                native_points += valid.sum()
            for key in ("s2_ndvi", "s2_ndwi", "s2_mndwi"):
                data = sample[key].values
                check(np.nanmax(np.abs(data), initial=0) <= 1., f"Index outside [-1,1]: {key}")
        elif obs["sensor"] == "Sentinel-1":
            for key in ("VV", "VH"):
                var = f"s1_{key}_gamma0"
                power = sample[var].values
                if not processed_only and obs["alignment_method"][key] == "identity on common 10 m lattice":
                    valid = np.isfinite(power)
                    raw = values_at_centers(root / obs["id"] / f"{key.lower()}_gamma0.tif", x[valid], y[valid])
                    np.testing.assert_array_equal(power[valid], raw)
                    native_points += valid.sum()
                positive = power > 0
                np.testing.assert_allclose(sample[var + "_db"].values[positive], 10 * np.log10(power[positive]),
                                           atol=1.2e-5, rtol=0)
        elif obs["sensor"] == "NISAR":
            group = obs["group"]
            for key in ("HHHH", "HVHV"):
                check(int((sample[f"nisar_{key}_valid"].values == 1).sum()) == 1310, "NISAR valid cell count")
                if comparison is not None:
                    with rasterio.open(comparison / f"nisar_{group}_{key}.tif") as expected:
                        expected_value = expected.read(1)
                        np.testing.assert_array_equal(sample[f"nisar_{key}"].values[inside], expected_value[inside])
    with rasterio.open(output / "cross_date.tif") as change_raster:
        check(change_raster.crs.to_epsg() == 32618 and list(change_raster.transform)[:6] == manifest["grid"]["affine"],
              "Cross-date GeoTIFF affine and CRS")
        for number, variable in enumerate(change_raster.descriptions, 1):
            np.testing.assert_array_equal(change_raster.read(number), cross[variable].values)
    check(int(np.sum(cross.lidar_change_m_valid.values == 1)) == 168, "Paired LiDAR count")
    check(int(np.sum(cross.all_sensor_valid_overlap.values == 1)) == 168, "Shared four-sensor valid count")
    check(abs(float(cross.lidar_change_m.sel(x=432375., y=4004825.)) - (-0.215214)) < 1e-6,
          "Handoff independent LiDAR sample")
    for sensor, definition in pairs.items():
        check(definition["status"] == "paired", f"Incomplete primary pair for {sensor}")
        left, right = (ds.isel(observation=int(np.flatnonzero(ds.id.values == definition[k])[0]))
                       for k in ("june_id", "october_id"))
        for key, count in definition["valid_counts"].items():
            check(int((cross[key + "_valid"].values == 1).sum()) == count, f"Comparison valid count for {key}")
            if sensor != "USACE LiDAR":
                variable = key.removesuffix("_change")
                expected = right[variable].values - left[variable].values
                np.testing.assert_allclose(cross[key].values, expected, atol=7e-6, rtol=0, equal_nan=True)
    pixels = pd.read_parquet(output / "duck_pixels.parquet")
    check(len(pixels) == 1450 * len(records), "Pixel table count")
    check(not pixels.duplicated(["observation", "row", "column"]).any(), "Unique acquisition/pixel key")
    check(np.all(pixels["x"] == 432255 + 10 * pixels["column"]), "Pixel table easting")
    check(np.all(pixels["y"] == 4005095 - 10 * pixels["row"]), "Pixel table northing")
    env = pd.read_parquet(output / "environment/observations.parquet")
    near = pd.read_parquet(output / "environment/nearest.parquet")
    ant = pd.read_parquet(output / "environment/antecedent.parquet")
    check(len(env) == 290341 and len(ant) == 4284 and len(near) == 1064, "Environmental table sizes")
    check(set(near.id) == set(ds.id.values), "Environment key coverage")
    check(not near.duplicated(["id", "station_id", "variable"]).any(), "Duplicate environmental join key")
    tides = pd.read_parquet(output / "environment/tide_stage.parquet")
    check(len(tides) == 28 and set(tides.id) == set(ds.id.values), "Tidal-stage acquisition keys")
    actual = near.dropna(subset=["value"])
    check(len(actual) == 694, "Qualifying environmental matches")
    np.testing.assert_allclose(actual.offset_seconds, (actual.timestamp_utc - actual.acquisition_utc).dt.total_seconds(),
                               rtol=0, atol=1e-6)
    check((actual.offset_seconds.abs() <= actual.station_id.map(TOLERANCE) * 60).all(), "Nearest-observation tolerance")
    check((ant.last_observation_utc.dropna() <= ant.loc[ant.last_observation_utc.notna(),
                                                     "window_end_utc_inclusive"]).all(), "Antecedent includes future data")
    no_stat = ant.loc[~ant.coverage_threshold_met, ["mean", "min", "max", "rain_sum_mm", "circular_mean_deg"]]
    check(no_stat.isna().all(axis=None), "Insufficient-coverage stat should be absent")
    check((env.loc[env.unit == DEG, "value"].dropna().between(0, 360)).all(), "Direction validity")
    if not processed_only:
        hydro = sorted(env_raw.glob("frf_hydro_*.nc"))
        check(len(hydro) == 3, "All three months of hydrodynamic receipts")
        hydro_count = 0
        for file in hydro:
            with nc.Dataset(file) as d:
                check(d.source_hydro_xfrf_stride == 10, "Hydrodynamics must use checked DAP transfer")
                values = d["waveHs"][:].compressed()
                check(np.all((values >= 0) & (values < 50)), "Hydrodynamic source-value range")
                hydro_count += int(values.size)
        check(hydro_count > 0, "Hydrodynamics must carry actual wave measurements")
    cross_environment = pd.read_parquet(output / "environment/cross_date.parquet")
    check(set(cross_environment.pair_sensor) == set(pairs), "Environmental comparison joins")
    report = {"status": "passed", "observations": len(records), "pixel_rows": len(pixels),
              "environment_rows": len(env), "environment_nearest_matches": len(actual),
              "change_cells": int((cross.lidar_change_m_valid.values == 1).sum())}
    if processed_only:
        report["verified_files"] = verified_files
    else:
        report["native_samples_verified"] = int(native_points)
        report["checked_hydro_wave_height_values"] = hydro_count
        write_json(output / "verification.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--processed-only", action="store_true",
                        help="Verify the published SHA256SUMS and dataset without the original source cache")
    args = parser.parse_args()
    validate(args.workspace, args.output, processed_only=args.processed_only)
