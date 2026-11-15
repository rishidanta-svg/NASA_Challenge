"""Acquire the two USACE slices, retain native cells and compute terrain change."""

import logging
import time
from datetime import timezone
from contextlib import contextmanager

from affine import Affine
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import netCDF4 as nc
import numpy as np
from pyproj import Transformer
import shapely
from shapely.geometry import LineString, box, mapping
from shapely.ops import transform

from duck_common import (
    ALONGSHORE, AOI_UTM, EPOCHS, Grid, TO_UTM, TO_WGS84, UTM, VERTICAL_DATUM,
    array, file_record, now, stats, utc, write_json, write_raster,
)

BASE = "https://chldata.erdc.dren.mil/thredds"
REL = "frf/geomorphology/DEMs/duneLidarDEM/2026"
FLAGS = ("coregQCFlag", "coregAlgorithmFlag", "rmsReflectorError",
         "assessmentPlanesOffset", "translationSigma", "rotationSigma")
ANGLE = np.radians(69.9747)
SIN, COS = np.sin(ANGLE), np.cos(ANGLE)
FRF_TO_SP = Affine(SIN, -COS, 901951.6805, COS, SIN, 274093.1562)
NC_STATE_PLANE = 6542
SP_TO_UTM = Transformer.from_crs(NC_STATE_PLANE, UTM, always_xy=True,
                                allow_ballpark=False)
SP_TO_GEOG = Transformer.from_crs(NC_STATE_PLANE, 4326, always_xy=True,
                                 allow_ballpark=False)
MIN_COVERAGE = 0.5


def frf_to_utm(x, y):
    return SP_TO_UTM.transform(*(FRF_TO_SP * (x, y)))


@contextmanager
def temporary_netcdf(path):
    pending = path.with_suffix(".nc.part")
    try:
        with nc.Dataset(pending, "w") as result:
            yield result
        pending.replace(path)
    finally:
        pending.unlink(missing_ok=True)


def acquire_slice(epoch, path):
    month, timestamp, hint = EPOCHS[epoch]
    filename = f"FRF-geomorphology_DEMs_duneLidarDEM_{month}.nc"
    dap = f"{BASE}/dodsC/{REL}/{filename}"
    if path.exists():
        return
    for attempt in range(3):
        try:
            with nc.Dataset(dap) as src:
                dates = src["time"]
                target = nc.date2num(utc(timestamp).replace(tzinfo=None), dates.units,
                                     calendar=dates.calendar)
                matches = np.flatnonzero(np.abs(array(dates[:]) - target) <= 0.001)
                if matches.size != 1:
                    raise ValueError(f"{epoch}: requested timestamp had {matches.size} matches")
                idx = int(matches[0])
                if idx != hint:
                    logging.warning("%s timestamp found at index %s (hint %s)", epoch, idx, hint)
                ys = array(src["yFRF"][:])
                # Keep a one-cell buffer around the alongshore cut for pixel-footprint work.
                candidate = np.flatnonzero((ys >= ALONGSHORE[0] - 1) &
                                           (ys <= ALONGSHORE[1] + 1))
                if not candidate.size:
                    raise ValueError("USACE yFRF has no study-area overlap")
                yslice = slice(int(candidate.min()), int(candidate.max()) + 1)
                select = {"time": slice(idx, idx + 1), "yFRF": yslice}
                with temporary_netcdf(path) as dst:
                    dst.setncatts({key: src.getncattr(key) for key in src.ncattrs()})
                    dst.setncatts({
                        "littoral_usace_dap_url": dap,
                        "littoral_usace_fileserver_url": f"{BASE}/fileServer/{REL}/{filename}",
                        "littoral_source_filename": filename, "littoral_time_index": idx,
                        "littoral_retrieved_at": now(),
                    })
                    for key in ("time", "xFRF", "yFRF", "latitude", "longitude",
                                "elevation", *FLAGS):
                        var = src[key]
                        slices = tuple(select.get(dim, slice(None)) for dim in var.dimensions)
                        var.set_auto_maskandscale(False)
                        values = var[slices]
                        for dim, size in zip(var.dimensions, values.shape):
                            if dim not in dst.dimensions:
                                dst.createDimension(dim, size)
                        attrs = {k: var.getncattr(k) for k in var.ncattrs() if k != "_FillValue"}
                        out = dst.createVariable(key, var.dtype, var.dimensions, zlib=True,
                                                 fill_value=getattr(var, "_FillValue", None))
                        out.setncatts(attrs)
                        out.set_auto_maskandscale(False)
                        out[:] = values
            return
        except (OSError, RuntimeError) as exc:
            if attempt == 2:
                raise
            logging.warning("Retrying %s OPeNDAP read: %s", epoch, exc)
            time.sleep(2 ** attempt)


def load_slice(epoch, path, root):
    with nc.Dataset(path) as ds:
        dates = ds["time"]
        decoded = nc.num2date(dates[0], dates.units, calendar=dates.calendar,
                             only_use_cftime_datetimes=False).replace(tzinfo=timezone.utc)
        if abs((decoded - utc(EPOCHS[epoch][1])).total_seconds()) > 0.001:
            raise ValueError(f"{epoch}: cached timestamp {decoded} differs from requested time")
        if ds.vertical_datum != VERTICAL_DATUM or ds["elevation"].units != "m":
            raise ValueError("USACE vertical reference or units changed")
        datum = ds.horizontal_datum
        if any(text not in datum for text in ("NAD83(2011)", "901951.6805", "274093.1562", "69.9747")):
            raise ValueError(f"Unexpected USACE horizontal datum: {datum}")
        for axes in ("xFRF", "yFRF"):
            if ds[axes].units != "m":
                raise ValueError(f"Unexpected units on {axes}")
        x, y = (array(ds[key][:]) for key in ("xFRF", "yFRF"))
        if not (np.allclose(np.diff(x), 1, rtol=0) and np.allclose(np.diff(y), 1, rtol=0)):
            raise ValueError("USACE grid centers are no longer ascending at 1 m spacing")
        if ds["elevation"].dimensions != ("time", "yFRF", "xFRF"):
            raise ValueError("Unexpected USACE elevation dimension order")
        z = array(ds["elevation"][0])
        z[~np.isfinite(z)] = np.nan
        lon, lat = array(ds["longitude"][:]), array(ds["latitude"][:])
        xx, yy = np.meshgrid(x, y)
        dx, dy = frf_to_utm(xx, yy)
        lon_x, lat_y = SP_TO_GEOG.transform(*(FRF_TO_SP * (xx, yy)))
        source_x, source_y = TO_UTM.transform(lon, lat)
        control = np.hypot(dx - source_x, dy - source_y)
        if not np.isfinite(control).all() or control.max() > 0.25:
            raise ValueError("FRF transform disagrees with the NetCDF geolocation by over 0.25 m")
        qc = {key: np.where(np.isfinite(v), v, None).tolist()
              for key in FLAGS for v in [array(ds[key][0])]}
        meta = {
            **file_record(path, root), "source_filename": ds.littoral_source_filename,
            "url": ds.littoral_usace_dap_url, "file_server_url": ds.littoral_usace_fileserver_url,
            "retrieved_at": ds.littoral_retrieved_at,
            "timestamp_utc": EPOCHS[epoch][1],
            "decoded_netcdf_time_utc": decoded.isoformat(),
            "netcdf_time_coordinate": float(dates[0]), "netcdf_time_units": dates.units,
            "netcdf_calendar": dates.calendar, "source_time_index": int(ds.littoral_time_index),
            "horizontal_datum": datum, "vertical_datum": ds.vertical_datum,
            "source_elevation_fill": float(ds["elevation"]._FillValue),
            "source_license": ds.license, "quality": qc,
            "source_quality_attributes": {key: ds[key].description.strip() for key in FLAGS},
            "coordinate_check_residual_m": stats(control),
            "horizontal_operation": SP_TO_UTM.description,
            "horizontal_operation_reported_accuracy_m": SP_TO_UTM.accuracy,
            "source_center_lonlat": [float(lon[0, 0]), float(lat[0, 0])],
            "pixel_center_bounds_wsen": [float(lon_x.min()), float(lat_y.min()),
                                        float(lon_x.max()), float(lat_y.max())],
            "status": "numeric_slice_verified",
        }
    if not np.isfinite(z).any():
        raise ValueError(f"{epoch}: LiDAR slice has no numerical elevations")
    return x, y, z, dx, dy, meta


def footprint():
    # The source footprint is narrower across shore than the geographic AOI.
    y_strip = box(-10000, ALONGSHORE[0], 10000, ALONGSHORE[1])
    return AOI_UTM.intersection(transform(frf_to_utm, shapely.segmentize(y_strip, 25)))


def native_products(out, reference_dir, views, clip):
    x, y, june, easting, northing, _ = views["june"]
    xo, yo, october, _, _, _ = views["october"]
    if not (np.array_equal(x, xo) and np.array_equal(y, yo)):
        raise ValueError("USACE epochs have different native FRF grids")
    visible = shapely.intersects_xy(shapely.buffer(clip, 1e-7), easting, northing)
    if not visible.any():
        raise ValueError("No native LiDAR centers intersect the study footprint")
    rr, cc = np.where(visible)
    rows, cols = slice(rr.min(), rr.max() + 1), slice(cc.min(), cc.max() + 1)
    grid = Grid(cols.stop - cols.start, rows.stop - rows.start,
                FRF_TO_SP * Affine(1, 0, x[cols.start] - 0.5, 0, -1, y[rows.stop - 1] + 0.5),
                NC_STATE_PLANE)
    native = {k: np.where(visible, vals, np.nan) for k, vals in
              (("june", june), ("october", october))}
    paired = all(meta["quality"]["coregQCFlag"] == 1 for *_, meta in views.values())
    if not paired:
        raise ValueError("USACE epochs failed the co-registration quality gate (flag 1 required)")
    native["delta_z"] = native["october"] - native["june"]
    result = {}
    for key, z in native.items():
        name = f"lidar_{key}_native.tif"
        acquisition = EPOCHS[key][1] if key in EPOCHS else None
        tags = {"VERTICAL_DATUM": VERTICAL_DATUM, "SOURCE": "USACE FRF dune lidar DEM"}
        if acquisition:
            tags["ACQUISITION_TIME_UTC"] = acquisition
        else:
            tags["CHANGE_CONVENTION"] = "October minus June on common native cells"
        write_raster(out / name, grid, z[rows, cols][::-1], "m", tags)
        result[key] = {"file": name, **stats(z), "missing_centers": int((visible & ~np.isfinite(z)).sum())}
    if not result["delta_z"]["valid_pixels"]:
        raise ValueError("No common native LiDAR elevation")
    result["study_centers"] = int(visible.sum())
    result["paired_fraction_of_study_centers"] = result["delta_z"]["valid_pixels"] / visible.sum()
    result["grid"] = grid.metadata()
    transects(out, native, x, y, views)
    figure(reference_dir / "duck_lidar_alignment.png", easting, northing, native, clip, x, y)
    return result


def transects(out, native, x, y, views):
    features, profiles = [], []
    for along in (750, 850, 950, 1050, 1150):
        row = np.flatnonzero(y == along)
        if row.size != 1:
            continue
        row = int(row[0])
        valid = np.isfinite(native["delta_z"][row])
        if np.count_nonzero(valid) < 2:
            continue
        id_ = f"FRF-{along}"
        props = {"id": id_, "label": f"FRF y = {along} m", "y_frf_m": along,
                 "verticalDatum": VERTICAL_DATUM, "units": "m",
                 "source": "USACE FRF dune lidar DEM",
                 "june_utc": views["june"][-1]["timestamp_utc"],
                 "october_utc": views["october"][-1]["timestamp_utc"]}
        # Derive lines along continuous jointly valid runs only, so holes remain holes.
        indices = np.flatnonzero(valid)
        parts = np.split(indices, np.flatnonzero(np.diff(indices) > 1) + 1)
        for part in parts:
            if part.size >= 2:
                lon, lat = TO_WGS84.transform(*frf_to_utm(x[part], np.full(part.size, along)))
                features.append({"type": "Feature", "properties": props,
                                 "geometry": mapping(LineString(np.column_stack([lon, lat])))})
        profiles.append({**props, **{
            epoch: [{"x": float(px), "z": float(pz)} for px, pz in zip(x[valid], native[epoch][row, valid])]
            for epoch in EPOCHS}})
    write_json(out / "transects.geojson", {"type": "FeatureCollection", "features": features})
    write_json(out / "profiles.json", {"label": "USACE FRF measured dune LiDAR", "profiles": profiles})


def figure(path, easting, northing, native, clip, x, y):
    fig, axes = plt.subplots(2, 3, figsize=(12, 8), constrained_layout=True)
    xx, yy = np.meshgrid(x, y)
    for col, (key, values) in enumerate(native.items()):
        if key == "delta_z":
            limit = max(np.nanpercentile(np.abs(values), 98), 0.01)
            opts = dict(cmap="RdBu_r", vmin=-limit, vmax=limit)
        else:
            opts = dict(cmap="terrain", vmin=-1, vmax=12)
        for row, (gx, gy, title) in enumerate(((xx, yy, "FRF native"), (easting, northing, "UTM 18N"))):
            ax = axes[row, col]
            plot = ax.pcolormesh(gx, gy, np.ma.masked_invalid(values), shading="nearest", **opts)
            ax.set(title=f"{title} · {key}", aspect="equal")
            ax.ticklabel_format(style="plain", useOffset=False)
            if row == 1:
                ax.plot(*clip.exterior.xy, color="black", lw=0.7)
        fig.colorbar(plot, ax=axes[:, col], label="m", shrink=0.65)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def comparison_lidar(grid, views, clip):
    """Accumulate exact quadrilateral intersection weights in UTM square metres."""
    x, y, june, _, _, _ = views["june"]
    october = views["october"][2]
    xx, yy = np.meshgrid(x, y)
    offsets = np.array([[-.5, -.5], [.5, -.5], [.5, .5], [-.5, .5], [-.5, -.5]])
    xs = xx.reshape(-1, 1) + offsets[:, 0]
    ys = yy.reshape(-1, 1) + offsets[:, 1]
    sx, sy = frf_to_utm(xs, ys)
    cells = shapely.polygons(np.stack((sx, sy), axis=-1))
    e, n = (v.ravel() for v in grid.centers())
    dx, dy = grid.affine.a / 2, -grid.affine.e / 2
    targets = shapely.box(e - dx, n - dy, e + dx, n + dy)
    clipped = shapely.intersection(targets, clip)
    target_idx, source_idx = shapely.STRtree(cells).query(clipped, predicate="intersects")
    area = shapely.area(shapely.intersection(clipped[target_idx], cells[source_idx]))
    positive = area > 1e-9
    area, target_idx, source_idx = area[positive], target_idx[positive], source_idx[positive]
    size = len(e)
    shape = grid.height, grid.width
    pixel_area = 4 * dx * dy
    inside = shapely.area(clipped) > 0
    result = {"study_area_fraction": (shapely.area(clipped) / pixel_area).reshape(shape)}
    flat = {key: data.ravel()[source_idx] for key, data in
            (("june", june), ("october", october), ("dz", october - june))}
    for label, values in flat.items():
        finite = np.isfinite(values)
        selected, weights, observed = target_idx[finite], area[finite], values[finite]
        weight = np.bincount(selected, weights=weights, minlength=size)
        fraction = np.minimum(weight / pixel_area, 1)
        enough = (fraction >= MIN_COVERAGE) & inside
        divisor = np.where(weight > 0, weight, 1)
        mean = np.bincount(selected, weights=weights * observed, minlength=size) / divisor
        var = np.bincount(selected, weights=weights * observed**2, minlength=size) / divisor - mean**2
        prefix = f"lidar_{label}"
        result[f"{prefix}_m"] = np.where(enough, mean, np.nan).reshape(shape)
        result[f"{prefix}_std_m"] = np.where(enough, np.sqrt(np.maximum(var, 0)), np.nan).reshape(shape)
        result[f"{prefix}_sample_count"] = np.where(
            inside, np.bincount(selected, minlength=size), np.nan).reshape(shape)
        result[f"{prefix}_coverage"] = np.where(inside, fraction, np.nan).reshape(shape)
        result[f"{prefix}_valid"] = np.where(inside, enough.astype(float), np.nan).reshape(shape)
    return result
