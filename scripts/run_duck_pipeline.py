#!/usr/bin/env python3
"""Run the exact June/October 2026 Duck pipeline on real source observations."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import csv
import fcntl
from datetime import datetime
import logging
from netrc import netrc, NetrcParseError
import os
from pathlib import Path
import re
from shutil import copyfile
import sys
from tempfile import TemporaryDirectory

import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling
import shapely

from duck_common import (
    ALONGSHORE, AOI, EPOCHS, ROOT, TO_WGS84, VERTICAL_DATUM, file_record, now,
    reference_grid, stats, write_json, write_raster,
)
from duck_lidar import MIN_COVERAGE, acquire_slice, comparison_lidar, footprint, load_slice, native_products
from duck_radar import (
    catalog, comparison_figure, comparison_grid, radar_products, source_layers, supplement_radar,
)


@contextmanager
def staging_directory(root):
    with TemporaryDirectory(dir=root / "interim", prefix="run-") as stage:
        yield Path(stage)


def publish(bundle, root, category):
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    target = root / "processed" / f"{category}-{stamp}"
    bundle.replace(target)
    write_json(root / "processed" / f"latest_{category}.json",
               {"directory": target.name, "manifest": f"{target.name}/manifest.json"})
    return target


def output_records(path):
    return [file_record(entry, path) for entry in sorted(path.iterdir()) if entry.is_file()]


def pixel_table(path, grid, columns, lidar):
    east, north = grid.centers()
    lon, lat = TO_WGS84.transform(east, north)
    qc = [lidar[epoch][-1]["quality"]["coregQCFlag"] for epoch in EPOCHS]
    keys = list(columns)
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["row", "column", "easting_m", "northing_m", "longitude", "latitude",
                         "lidar_june_coreg_qc", "lidar_october_coreg_qc", *keys])
        for row, col in np.argwhere(columns["study_area_fraction"] > 0):
            vals = [columns[key][row, col] for key in keys]
            writer.writerow([row, col, east[row, col], north[row, col],
                             lon[row, col], lat[row, col], *qc,
                             *(value if np.isfinite(value) else "" for value in vals)])


def map_dem(out, clip, metadata):
    grid = reference_grid(1)
    e, n = grid.centers()
    inside = shapely.intersects_xy(clip, e, n)
    for key in ("june", "october", "delta_z"):
        projected = np.full((grid.height, grid.width), np.nan, dtype="float32")
        with rasterio.open(out / metadata[key]["file"]) as source:
            reproject(source.read(1), projected, src_transform=source.transform, src_crs=source.crs,
                      src_nodata=np.nan, dst_transform=grid.affine, dst_crs=f"EPSG:{grid.epsg}",
                      dst_nodata=np.nan, resampling=Resampling.nearest)
            tags = {k: v for k, v in source.tags().items() if k != "AREA_OR_POINT"}
        projected[~inside] = np.nan
        name = f"lidar_{key}_utm_1m.tif"
        write_raster(out / name, grid, projected, "m",
                     {**tags, "RESAMPLING": "nearest", "ROLE": "map derivative"})
        metadata[key]["map_derivative"] = {"file": name, **stats(projected)}
    metadata["map_grid"] = grid.metadata()


def unit_for(key):
    for suffix, unit in (("_m", "m"), ("_db", "dB"), ("_mask", "code"), ("ExceptionMask", "code"), ("_valid", "flag"),
                         ("_sample_count", "count")):
        if key.endswith(suffix):
            return unit
    return "1"


def write_comparison(out, grid, layers, views, radar_sources=None):
    for key, values in layers.items():
        tags = {}
        if key.startswith("lidar_"):
            tags["VERTICAL_DATUM"] = VERTICAL_DATUM
        if key.startswith("nisar_") and any(f"_{p}" in key for p in ("HHHH", "HVHV")):
            tags["BACKSCATTER"] = "gamma0"
        for epoch, (_, timestamp, _) in EPOCHS.items():
            if key.startswith(f"lidar_{epoch}_"):
                tags["ACQUISITION_TIME_UTC"] = timestamp
            if radar_sources is not None and key.startswith(f"nisar_{epoch}_"):
                identity = radar_sources[epoch][-1]["source_hdf_metadata"]["identification"]
                tags["ACQUISITION_START_UTC"] = identity["zeroDopplerStartTime"] + "Z"
                tags["ACQUISITION_END_UTC"] = identity["zeroDopplerEndTime"] + "Z"
                tags["PRODUCT_VERSION"] = identity["productVersion"]
        write_raster(out / f"{key}.tif", grid, values.astype("float32"), unit_for(key), tags)
    pixel_table(out / "comparison_pixels.csv", grid, layers, views)
    count = int(np.count_nonzero(layers["study_area_fraction"] > 0))
    lidar_overlap = int(np.isfinite(layers["lidar_dz_m"]).sum())
    results = {"grid": grid.metadata(), "study_intersecting_pixels": count,
               "paired_lidar_pixels_at_threshold": lidar_overlap,
               "paired_lidar_fraction_of_study_intersecting_pixels": lidar_overlap / count,
               "bands": {key: stats(values) for key, values in layers.items()}}
    if not lidar_overlap:
        raise ValueError("No paired LiDAR cells meet the comparison-grid coverage threshold")
    if "nisar_HHHH_change_db" in layers:
        joint = np.isfinite(layers["lidar_dz_m"]) & np.isfinite(layers["nisar_HHHH_change_db"])
        joint &= np.isfinite(layers["nisar_HVHV_change_db"])
        results["fully_joined_pixels"] = int(joint.sum())
        if not joint.any():
            raise ValueError("No four-observation pixel survived quality screening")
    return results


def get_token():
    token = os.environ.get("EARTHDATA_TOKEN")
    if token:
        return token
    env_login = {"EARTHDATA_USERNAME", "EARTHDATA_PASSWORD"}.issubset(os.environ)
    netrc_login = False
    if not env_login and (Path.home() / ".netrc").is_file():
        try:
            entry = netrc().authenticators("urs.earthdata.nasa.gov")
            netrc_login = bool(entry and entry[0] and entry[2])
        except (OSError, NetrcParseError):
            raise ValueError("Could not read a secure local .netrc; check format and permissions") from None
    if not (env_login or netrc_login):
        return None

    import earthaccess
    logging.getLogger("earthaccess.auth").setLevel(logging.WARNING)
    auth = earthaccess.login(strategy="environment" if env_login else "netrc")
    if auth.authenticated and auth.token:
        return auth.token["access_token"]
    raise ValueError("Earthdata rejected the local login or could not issue an access token")

def lidar_stage(root, clip):
    views = {}
    for epoch in EPOCHS:
        path = root / "raw" / f"frf_{epoch}_slice.nc"
        acquire_slice(epoch, path)
        views[epoch] = load_slice(epoch, path, root)
        logging.info("Verified %s LiDAR time index %s and datum %s", epoch,
                     views[epoch][-1]["source_time_index"], VERTICAL_DATUM)
    with staging_directory(root) as stage:
        out = stage / "lidar"
        out.mkdir()
        native = native_products(out, out, views, clip)
        map_dem(out, clip, native)
        grid = reference_grid(10)
        layers = comparison_lidar(grid, views, clip)
        summary = write_comparison(out, grid, layers, views)
        write_json(out / "manifest.json", {
            "schema_version": 1, "status": "verified_lidar_only",
            "created_utc": now(), "study_wsen_epsg4326": AOI, "frf_y_range_m": ALONGSHORE,
            "source": {epoch: view[-1] for epoch, view in views.items()},
            "native": native, "map_1m": "Nearest native sample on an EPSG:32618 display lattice",
            "lidar_reference_grid": summary, "min_valid_area_fraction": MIN_COVERAGE,
            "dispersion": "area-weighted population standard deviation",
            "files": output_records(out),
        })
        target = publish(out, root, "lidar")
    return views, target


def can_replay_radar(root, epoch, meta):
    raw = root / "raw"
    return ((raw / meta["filename"]).exists() or
            ((raw / f"{epoch}_nisar_geometry.json").exists() and
             ((raw / f"{epoch}_harmony" / "assets.json").exists() or
              (raw / f"{epoch}_nisar_hyperslab.json").exists())))


def full_stage(root, clip, views, records, permit_download):
    token = None if all(can_replay_radar(root, k, v) for k, v in records.items()) else get_token()
    def load(epoch):
        meta = records[epoch]
        radar = source_layers(token, meta, root, epoch, permit_download)
        result = supplement_radar(token, meta, root, epoch, radar)
        logging.info("Verified %s GCOV pixels, native grid, exception mask and geometric metadata", epoch)
        return result

    with ThreadPoolExecutor(max_workers=2) as workers:
        loaded = dict(zip(records, workers.map(load, records)))
    grid, alignment = comparison_grid(loaded)
    with staging_directory(root) as stage:
        out = stage / "comparison"
        out.mkdir()
        for epoch, (_, _, provenance) in loaded.items():
            geom = provenance["source_hdf_metadata"]["geometry_asset"]
            copyfile(root / geom["filename"], out / f"nisar_{epoch}_radar_geometry.npz")
        lidar = comparison_lidar(grid, views, clip)
        radar = radar_products(out, loaded, grid, clip)
        summary = write_comparison(out, grid, {**lidar, **radar}, views, loaded)
        comparison_figure(out, grid, {**lidar, **radar}, loaded)
        write_json(out / "manifest.json", {
            "schema_version": 1, "status": "verified_lidar_and_radar",
            "created_utc": now(), "study_wsen_epsg4326": AOI, "frf_y_range_m": ALONGSHORE,
            "source": {"lidar": {key: view[-1] for key, view in views.items()},
                       "nisar": {key: {**records[key], **data[-1]} for key, data in loaded.items()}},
            "alignment": alignment, "comparison": summary,
            "min_valid_area_fraction": MIN_COVERAGE,
            "calibration": "GCOV linear gamma0 power. dB = 10 log10(power) for positive samples.",
            "radar_resampling": "Nearest neighbor; preserves measured intensity and categorical flags.",
            "files": output_records(out),
        })
        return publish(out, root, "comparison")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("catalog", "lidar", "all"), nargs="?", default="all")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--refresh-catalog", action="store_true")
    parser.add_argument("--allow-full-hdf5", action="store_true",
                        help="Allow ~9.9 GB of full archive download if Harmony fails.")
    args = parser.parse_args()
    root = args.data_dir.resolve()
    for name in ("raw", "interim", "processed"):
        (root / name).mkdir(parents=True, exist_ok=True)
    with (root / "interim" / "duck.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("A pipeline run is already writing to this data directory.", file=sys.stderr)
            return 1
        return run(args, root)


def run(args, root):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(root / "interim" / "duck_processing.log")])
    logging.getLogger("fsspec").setLevel(logging.WARNING)
    state = {"started_utc": now(), "requested_stage": args.stage}
    try:
        if args.stage in ("lidar", "all"):
            clip = footprint()
            views, target = lidar_stage(root, clip)
            state["lidar_bundle"] = str(target.relative_to(root))
            logging.info("Published verified LiDAR: %s", target)
        if args.stage in ("catalog", "all"):
            records = {key: catalog(key, root, args.refresh_catalog) for key in EPOCHS}
            write_json(root / "interim" / "nisar_catalog.json", records)
            state["nisar_catalog"] = "interim/nisar_catalog.json"
            logging.info("Verified both pinned NISAR granules in ASF and CMR")
        if args.stage == "all":
            target = full_stage(root, clip, views, records, args.allow_full_hdf5)
            state["comparison_bundle"] = str(target.relative_to(root))
            logging.info("Published verified radar–LiDAR comparison: %s", target)
        state["status"] = "completed"
    except Exception as exc:
        # Request errors can hold authenticated URLs. Do not persist URL query parameters.
        message = re.sub(r"https?://[^\s'\"]+", "[remote URL]", str(exc))
        state.update(status="failed", error_type=type(exc).__name__, error=message)
        logging.error("%s: %s", type(exc).__name__, message)
        return 1
    finally:
        state["ended_utc"] = now()
        write_json(root / "interim" / "run_status.json", state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
