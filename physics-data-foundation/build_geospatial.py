"""Verify the upstream handoff and build the asynchronous, aligned Duck raster collection."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import CRS, Transformer
import rasterio
from rasterio.warp import reproject, Resampling
import xarray as xr

from acquire_satellite import BANDS

MASK = ("scl", "cloud", "shadow", "water", "invalid_scl", "clear")
INDEX = {"ndvi": ("B08", "B04"), "ndwi": ("B03", "B08"), "mndwi": ("B03", "B11")}
PERIODS = ("june", "october")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, values):
    path.write_text(json.dumps(values, indent=2, allow_nan=False) + "\n")


def read_image(path):
    with rasterio.open(path) as src:
        return (src.read(1, masked=True).astype("float32").filled(np.nan),
                src.transform, src.crs)


def warp(image, target, method=Resampling.nearest):
    src, src_transform, src_crs = image
    dst_transform, dst_crs, dst_shape = target
    result = np.full(dst_shape, np.nan, dtype="float32")
    reproject(src, result, src_transform=src_transform, src_crs=src_crs, src_nodata=np.nan,
              dst_transform=dst_transform, dst_crs=dst_crs, dst_nodata=np.nan, resampling=method)
    return result


def validate_source(folder, status):
    manifest = json.loads((folder / "manifest.json").read_text())
    if manifest.get("status") != status or manifest.get("schema_version") != 1:
        raise ValueError(f"Unsupported handoff: {folder}")
    for row in manifest["files"]:
        file = folder / row["filename"]
        if file.stat().st_size != row["bytes"] or digest(file) != row["sha256"]:
            raise ValueError(f"Handoff checksum failed: {file}")
    return manifest


def metadata(units, meaning, posting=None):
    row = {"units": units, "long_name": meaning}
    if posting is not None:
        row["source_posting_m"] = posting
    return row


def ratio(a, b):
    ok = np.isfinite(a) & np.isfinite(b) & (a >= 0) & (b >= 0) & (a + b > 1e-6)
    value = np.full(a.shape, np.nan, np.float32)
    np.divide(a - b, a + b, out=value, where=ok)
    return value


def optical(source, folder, target):
    paths = folder / source["id"]
    scl = read_image(paths / "SCL.tif")
    scl_values, scl_affine, scl_crs = scl
    classes = warp(scl, target)
    # In-source no-data is class 0. The padded native window covers all grid cells.
    classes = np.nan_to_num(classes, nan=0)
    output = {
        "s2_scl": classes, "s2_cloud": np.isin(classes, [8, 9, 10]),
        "s2_shadow": classes == 3, "s2_water": classes == 6,
        "s2_invalid_scl": np.isin(classes, [0, 1, 2, 7, 11]),
        "s2_clear": np.isin(classes, [4, 5, 6]),
    }
    descriptions = [
        "Scene classification class", "Cloud including cirrus", "Cloud shadow",
        "Sen2Cor water classification", "No-data, defective, dark/topographic shadow, unclassified, or snow/ice",
        "Clear vegetation, bare surface or water",
    ]
    attrs = {f"s2_{name}": metadata("1", desc, 20) for name, desc in zip(MASK, descriptions)}
    inputs = {}
    for key, (_, m, _) in BANDS.items():
        dn, tr, crs = read_image(paths / f"{key}_dn.tif")
        reflectance = (dn + source["offset_dn"][key]) / source["quantification"]
        inputs[key] = (reflectance, tr, crs)
        var = f"s2_{key}_reflectance"
        output[var] = np.where(output["s2_clear"], warp(inputs[key], target), np.nan)
        attrs[var] = metadata("1", f"Cloud-screened BOA surface reflectance {key}", m)
    for name in ("ndvi", "ndwi"):
        a, b = (output[f"s2_{key}_reflectance"] for key in INDEX[name])
        output[f"s2_{name}"] = ratio(a, b)
        attrs[f"s2_{name}"] = metadata("1", name.upper(), 10)
    green, ltr, lcrs = inputs["B03"]
    native20 = (scl_affine, scl_crs, scl_values.shape)
    green20 = warp(inputs["B03"], native20, Resampling.average)
    coverage20 = warp((np.isfinite(green).astype("float32"), ltr, lcrs), native20, Resampling.average)
    swir, tr, crs = inputs["B11"]
    if (tr, crs, swir.shape) != native20:
        raise ValueError(f"SCL/B11 grid mismatch: {source['id']}")
    mndwi20 = np.where((coverage20 >= 0.999999) & np.isin(scl_values, [4, 5, 6]),
                       ratio(green20, swir), np.nan)
    output["s2_mndwi"] = warp((mndwi20, scl_affine, scl_crs), target)
    attrs["s2_mndwi"] = metadata("1", "MNDWI computed on the native 20 m SWIR grid", 20)
    initial = tuple(output)
    for key in initial:
        if key.endswith("_reflectance") or key in {"s2_ndvi", "s2_ndwi", "s2_mndwi"}:
            output[key + "_valid"] = np.isfinite(output[key])
            attrs[key + "_valid"] = metadata("1", f"Valid data for {key}", attrs[key]["source_posting_m"])
    return output, attrs


def sentinel_radar(source, folder, target):
    output, attrs = {}, {}
    for pol in ("VV", "VH"):
        image = read_image(folder / source["id"] / f"{pol.lower()}_gamma0.tif")
        source_arr, source_transform, source_crs = image
        target_transform, target_crs, _ = target
        offset = ~source_transform * (target_transform.c, target_transform.f)
        identical_lattice = (source_crs == target_crs and
                             np.allclose(offset, np.round(offset), atol=1e-9, rtol=0) and
                             np.allclose((source_transform.a, source_transform.b, source_transform.d, source_transform.e),
                                         (target_transform.a, target_transform.b, target_transform.d, target_transform.e)))
        nonnegative = np.where(source_arr >= 0, source_arr, np.nan)
        method = Resampling.nearest if identical_lattice else Resampling.average
        values = warp((nonnegative, source_transform, source_crs), target, method)
        if not identical_lattice:
            valid_fraction = warp((np.isfinite(nonnegative).astype("float32"), source_transform, source_crs),
                                  target, Resampling.average)
            values[valid_fraction < 0.999999] = np.nan
        base = f"s1_{pol}_gamma0"
        db = np.full(values.shape, np.nan, np.float32)
        np.log10(values, out=db, where=values > 0)
        output.update({base: values, base + "_db": db * 10, base + "_valid": np.isfinite(values),
                       base + "_db_valid": values > 0})
        attrs.update({base: metadata("1", f"{pol} linear RTC gamma0 power", 10),
                      base + "_db": metadata("dB", f"{pol} RTC gamma0, 10 log10(power)", 10),
                      base + "_valid": metadata("1", f"{pol} finite, nonnegative source-supported power mask", 10),
                      base + "_db_valid": metadata("1", f"{pol} strictly positive power mask", 10)})
        source.setdefault("alignment_method", {})[pol] = (
            "identity on common 10 m lattice" if identical_lattice else "area-average linear power, full valid support")
    return output, attrs


def same_grid(path, target):
    data, tr, crs = read_image(path)
    if (tr, crs, data.shape) != target:
        raise ValueError(f"Aligned handoff grid mismatch: {path}")
    return data


def upstream_layers(folder, period, sensor, target):
    output, attrs = {}, {}
    if sensor == "NISAR":
        for name, desc, units in [
            ("HHHH", "HH linear frequency A gamma0 power", "1"),
            ("HHHH_db", "HH frequency A gamma0", "dB"), ("HHHH_valid", "HH valid power mask", "1"),
            ("HVHV", "HV linear frequency A gamma0 power", "1"),
            ("HVHV_db", "HV frequency A gamma0", "dB"), ("HVHV_valid", "HV valid power mask", "1"),
            ("mask", "Original subswath support code", "1"), ("numberOfLooks", "Number of looks", "1"),
            ("inputDataExceptionMask", "Original input data exception code", "1"),
            ("rtcGammaToSigmaFactor", "RTC gamma-to-sigma factor", "1"),
        ]:
            var = f"nisar_{name}"
            output[var] = same_grid(folder / f"nisar_{period}_{name}.tif", target)
            attrs[var] = metadata(units, desc, 10)
    else:
        for name, desc, units in [
            ("m", "LiDAR measured elevation", "m"), ("std_m", "Area-weighted within-cell elevation dispersion", "m"),
            ("sample_count", "Contributing native terrain samples", "1"),
            ("coverage", "Valid observed area divided by full pixel area", "1"), ("valid", "Coverage at least 50%", "1"),
        ]:
            var = f"lidar_{name}"
            output[var] = same_grid(folder / f"lidar_{period}_{name}.tif", target)
            attrs[var] = metadata(units, desc, 1)
            if name == "m":
                attrs[var]["vertical_datum"] = "NAVD88 (geoid12b)"
    return output, attrs


def epoch(source):
    sensor, t = source["sensor"], pd.Timestamp(source["timestamp_utc"])
    if sensor in {"NISAR", "USACE LiDAR"}:
        return source["upstream_group"]
    if (sensor == "Sentinel-2" and t.date().isoformat() == "2026-06-18") or (
        sensor == "Sentinel-1" and t.date().isoformat() in ("2026-06-16", "2026-06-30")
    ):
        return "june"
    return "october" if t.date().isoformat() == "2026-10-16" else "additional"


def tiff(path, layers, attrs, target, tags):
    tr, crs, (height, width) = target
    with rasterio.open(path, "w", driver="GTiff", crs=crs, transform=tr, height=height, width=width,
                       count=len(layers), dtype="float32", nodata=np.nan, compress="deflate") as out:
        out.update_tags(**tags)
        for k, (name, values) in enumerate(layers.items(), 1):
            out.write(np.asarray(values, dtype="float32"), k)
            out.set_band_description(k, name)
            out.set_band_unit(k, attrs[name]["units"])
            out.update_tags(k, **attrs[name])


def write_nc(dataset, output):
    encoding = {key: {"zlib": True, "complevel": 4, "_FillValue": np.float32(np.nan)}
                for key, value in dataset.data_vars.items()
                if "x" in value.dims and value.dtype.kind == "f"}
    dataset.to_netcdf(output, engine="netcdf4", encoding=encoding)


def grid_dataset(target, fraction):
    crs = CRS.from_epsg(32618)
    tr, _, (h, w) = target
    x = tr.c + (np.arange(w) + 0.5) * tr.a
    y = tr.f + (np.arange(h) + 0.5) * tr.e
    dataset = xr.Dataset(coords={
        "x": ("x", x, {"units": "m", "standard_name": "projection_x_coordinate", "axis": "X"}),
        "y": ("y", y, {"units": "m", "standard_name": "projection_y_coordinate", "axis": "Y"}),
    })
    cf_crs = crs.to_cf()
    cf_crs["GeoTransform"] = " ".join(map(str, tr.to_gdal()))
    dataset["spatial_ref"] = xr.DataArray(0, attrs=cf_crs)
    dataset["study_area_fraction"] = (("y", "x"), fraction,
                                     {"units": "1", "grid_mapping": "spatial_ref",
                                      "long_name": "Intersection fraction with the verified study footprint"})
    xx, yy = np.meshgrid(x, y)
    lon, lat = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform(xx, yy)
    dataset["longitude"] = (("y", "x"), lon, {"units": "degrees_east", "standard_name": "longitude"})
    dataset["latitude"] = (("y", "x"), lat, {"units": "degrees_north", "standard_name": "latitude"})
    return dataset.set_coords(["longitude", "latitude"])


def cross_date(output, records, maps, descriptions, comparison, target, fraction):
    ds = grid_dataset(target, fraction)
    all_deltas = {}
    attrs = {}
    pairs = {}
    within = fraction > 0
    for sensor in ("NISAR", "USACE LiDAR", "Sentinel-1", "Sentinel-2"):
        ids = []
        for period in PERIODS:
            candidates = [r for r in records if r["sensor"] == sensor and r["group"] == period]
            if sensor == "Sentinel-1":
                candidates = [r for r in candidates if r["planetary_computer_item"]["properties"]["sat:relative_orbit"] == 106]
            if len(candidates) != 1:
                break
            ids.append(candidates[0]["id"])
        if len(ids) != 2:
            pairs[sensor] = {"status": "missing_or_ambiguous_pair"}
            continue
        left, right = ids
        ra, rb = (next(r for r in records if r["id"] == key) for key in ids)
        pair = {"status": "paired", "june_id": left, "october_id": right, "june_utc": ra["timestamp_utc"],
                "october_utc": rb["timestamp_utc"],
                "elapsed_seconds": (pd.Timestamp(rb["timestamp_utc"]) - pd.Timestamp(ra["timestamp_utc"])).total_seconds(),
                "valid_counts": {}}
        if sensor == "USACE LiDAR":
            values = [("lidar_m", same_grid(comparison / "lidar_dz_m.tif", target))]
            for name in ("coverage", "std_m", "sample_count"):
                key = f"lidar_change_{name}"
                all_deltas[key] = same_grid(comparison / f"lidar_dz_{name}.tif", target)
                attrs[key] = descriptions[f"lidar_{name}"]
        elif sensor == "NISAR":
            values = [(key, same_grid(comparison / f"nisar_{key.split('_')[1]}_change_db.tif", target))
                      for key in ("nisar_HHHH_db", "nisar_HVHV_db")]
        else:
            keys = (["s1_VV_gamma0_db", "s1_VH_gamma0_db"] if sensor == "Sentinel-1" else
                    [f"s2_{b}_reflectance" for b in BANDS] + [f"s2_{k}" for k in INDEX])
            values = [(k, maps[right][k] - maps[left][k]) for k in keys]
        for key, delta in values:
            name = ("lidar_change_m" if key == "lidar_m" else f"{key}_change")
            mask = np.isfinite(delta) & within
            all_deltas[name] = delta
            attrs[name] = {**descriptions[key], "long_name": "October minus June: " + descriptions[key]["long_name"]}
            all_deltas[name + "_valid"] = np.where(within, mask, np.nan)
            attrs[name + "_valid"] = metadata("1", f"Both epochs valid for {name}")
            pair["valid_counts"][name] = int(mask.sum())
        pairs[sensor] = pair
    all_four = ["lidar_change_m_valid", "nisar_HHHH_db_change_valid", "nisar_HVHV_db_change_valid",
                "s1_VV_gamma0_db_change_valid", "s1_VH_gamma0_db_change_valid"] + [
                    f"s2_{key}_reflectance_change_valid" for key in BANDS]
    if all(key in all_deltas for key in all_four):
        mask = np.logical_and.reduce([all_deltas[key] == 1 for key in all_four])
        all_deltas["all_sensor_valid_overlap"] = np.where(within, mask, np.nan)
        attrs["all_sensor_valid_overlap"] = metadata("1", "Joint validity of both dates for LiDAR, NISAR, RTC and all six optical bands")
    for name, values in all_deltas.items():
        ds[name] = (("y", "x"), np.asarray(values, dtype="float32"), {**attrs[name], "grid_mapping": "spatial_ref"})
    write_nc(ds, output / "cross_date.nc")
    if all_deltas:
        tiff(output / "cross_date.tif", all_deltas, attrs, target, {"direction": "October minus June"})
    ds.drop_vars("spatial_ref").to_dataframe().reset_index().query("study_area_fraction > 0").to_parquet(
        output / "cross_date_pixels.parquet", index=False
    )
    write_json(output / "cross_date_pairs.json", pairs)
    return pairs, {k: int(np.count_nonzero(v == 1)) for k, v in all_deltas.items()
                   if k.endswith("_valid") or k == "all_sensor_valid_overlap"}


def build(output, comparison, lidar, native):
    compare = validate_source(comparison, "verified_lidar_and_radar")
    lidar_manifest = validate_source(lidar, "verified_lidar_only")
    if compare["source"]["lidar"] != lidar_manifest["source"]:
        raise ValueError("LiDAR sources differ between upstream bundles")
    grid = compare["comparison"]["grid"]
    if grid["epsg"] != 32618:
        raise ValueError("Handoff CRS must be EPSG:32618")
    tr = rasterio.Affine(*grid["affine"])
    target = (tr, rasterio.crs.CRS.from_epsg(grid["epsg"]), (grid["height"], grid["width"]))
    fraction = same_grid(comparison / "study_area_fraction.tif", target)
    within = fraction > 0
    if int(within.sum()) != compare["comparison"]["study_intersecting_pixels"]:
        raise ValueError("Handoff footprint and statistics disagree")
    manifest = json.loads((native / "acquisition.json").read_text())
    records = manifest["observations"]
    refs = {}
    for period in PERIODS:
        radar = compare["source"]["nisar"][period]
        terrain = compare["source"]["lidar"][period]
        start, end = (pd.Timestamp(radar[k]) for k in ("acquisition_start_utc", "acquisition_end_utc"))
        midpoint = start + (end - start) / 2
        refs[period] = (radar["granule"], midpoint)
        records.extend([
            {"id": radar["granule"], "sensor": "NISAR", "timestamp_utc": midpoint.isoformat(),
             "upstream_group": period, "upstream_source": radar},
            {"id": f"{terrain['source_filename']}#time_index={terrain['source_time_index']}",
             "sensor": "USACE LiDAR", "timestamp_utc": terrain["decoded_netcdf_time_utc"],
             "upstream_group": period, "upstream_source": terrain},
        ])
    records.sort(key=lambda row: pd.Timestamp(row["timestamp_utc"]))
    output.mkdir(parents=True, exist_ok=True)
    ds = grid_dataset(target, fraction)
    descriptions = {}
    maps = {}
    qa = {}
    for i, source in enumerate(records):
        sensor, ident = source["sensor"], source["id"]
        group = epoch(source)
        timestamp = pd.Timestamp(source["timestamp_utc"])
        reference = group if group in PERIODS else min(PERIODS, key=lambda k: abs(timestamp - refs[k][1]))
        source.update(group=group, observation_index=i, reference_id=refs[reference][0],
                      reference_utc=refs[reference][1].isoformat(),
                      offset_from_reference_seconds=(timestamp - refs[reference][1]).total_seconds())
        if sensor == "Sentinel-2":
            layers, desc = optical(source, native, target)
            valid_scl = within & (layers["s2_scl"] != 0)
            source["aoi_optical_qa"] = {
                "study_cells": int(within.sum()), "cells_with_scl": int(valid_scl.sum()),
                "cloud_cells": int((within & layers["s2_cloud"]).sum()),
                "shadow_cells": int((within & layers["s2_shadow"]).sum()),
                "clear_cells": int((within & layers["s2_clear"]).sum()),
                "cloud_fraction_of_scl_cells": float((within & layers["s2_cloud"]).sum() / valid_scl.sum())
                if valid_scl.any() else None,
            }
        elif sensor == "Sentinel-1":
            layers, desc = sentinel_radar(source, native, target)
        else:
            layers, desc = upstream_layers(comparison, group, sensor, target)
        layers = {k: np.where(within, v, np.nan).astype("float32") for k, v in layers.items()}
        relpath = Path(group) / f"{i:02d}_{sensor.replace(' ', '_')}.tif"
        path = output / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        tiff(path, layers, desc, target, {"source_id": ident, "acquisition_utc": source["timestamp_utc"],
                                        "sensor": sensor, "reference_id": source["reference_id"]})
        source["aligned_geotiff"] = str(relpath)
        if sensor in {"Sentinel-1", "Sentinel-2"}:
            source["native_directory_relative_to_satellite_cache"] = ident
        source["variables"] = list(layers)
        maps[ident] = layers
        descriptions.update(desc)
        qa[ident] = {k: int(np.isfinite(v).sum()) if not k.endswith("_valid") else int((v == 1).sum())
                     for k, v in layers.items()}

    ds = ds.assign_coords(observation=np.arange(len(records), dtype="int32"))
    ds["time"] = ("observation", pd.to_datetime([r["timestamp_utc"] for r in records], utc=True, format="mixed")
                  .tz_localize(None).to_numpy(dtype="datetime64[ns]"), {"standard_name": "time"})
    for key in ("id", "sensor", "group", "reference_id", "reference_utc", "offset_from_reference_seconds"):
        ds[key] = ("observation", [r[key] for r in records])
    ds = ds.set_coords("time")
    ds["offset_from_reference_seconds"].attrs["units"] = "s"
    empty = np.full(fraction.shape, np.nan, dtype="float32")
    for key, desc in descriptions.items():
        data = np.stack([maps[r["id"]].get(key, empty) for r in records])
        ds[key] = (("observation", "y", "x"), data, {**desc, "grid_mapping": "spatial_ref"})
    ds.attrs.update(Conventions="CF-1.10", title="POLTERGEIST Duck FRF asynchronous observations")
    write_nc(ds, output / "duck_observations.nc")
    pix = ds.drop_vars("spatial_ref").to_dataframe().reset_index().query("study_area_fraction > 0").copy()
    pix["row"] = ((tr.f - pix["y"]) / -tr.e).astype("int32")
    pix["column"] = ((pix["x"] - tr.c) / tr.a).astype("int32")
    pix.to_parquet(output / "duck_pixels.parquet", index=False)
    groups = {name: [r["observation_index"] for r in records if r["group"] == name]
              for name in ("june", "october", "additional")}
    write_json(output / "observation_groups.json", groups)
    write_json(output / "variable_dictionary.json", descriptions)
    pairs, overlap = cross_date(output, records, maps, descriptions, comparison, target, fraction)
    write_json(output / "acquisition_manifest.json", {
        "schema_version": 1, "grid": grid, "geographic_bbox_wsen": compare["study_wsen_epsg4326"],
        "frf_y_range_m": compare["frf_y_range_m"], "study_pixels_intersecting": int(within.sum()),
        "observations": records, "satellite_retrieval_failures": manifest["failures"],
        "upstream": {"comparison_manifest_sha256": digest(comparison / "manifest.json"),
                     "lidar_manifest_sha256": digest(lidar / "manifest.json"), "alignment": compare["alignment"]},
        "unavailable_direct_measurements": ["beach surface moisture", "surface roughness", "vegetation structure"],
    })
    write_json(output / "geospatial_qa.json", {
        "study_cells": int(within.sum()), "raster_valid_counts_by_acquisition": qa, "pairs": pairs,
        "change_valid_overlap_counts": overlap, "reference_grid": grid,
        "upstream_checksummed_files": len(compare["files"]) + len(lidar_manifest["files"]),
    })


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--comparison", type=Path, required=True)
    p.add_argument("--lidar", type=Path, required=True)
    p.add_argument("--native", type=Path, default=Path("data/raw/sentinel_native"))
    p.add_argument("--output", type=Path, default=Path("data/unified"))
    a = p.parse_args()
    build(a.output, a.comparison, a.lidar, a.native)


if __name__ == "__main__":
    main()
