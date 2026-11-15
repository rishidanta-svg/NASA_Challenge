"""HH-only land/water segmentation and experimental boundary assessment at Duck."""

from collections import Counter, deque

import numpy as np
import rasterio
from rasterio.warp import transform

from .coastal_observations import VERTICAL, error_metrics, unwrap
from .coastal_physics import MHW, correct_waterline, time_gap, water_level
from .reconstruction import FRF_ANGLE_RAD, ROWS10, frf_to_lonlat, frf_to_utm

VERSION = "duck-nisar-hh-v1"
POSTING_M = 10
PROFILE_X = np.arange(25, 196, POSTING_M)
LAND_LIMIT_M = 55
OFFSHORE_SEED_M = 160
KNOWN_ISSUES = "https://nisar-docs.asf.alaska.edu/provisional-known-issues/"
GCOV_GUIDE = "https://nisar-docs.asf.alaska.edu/gcov/"


def frf_centers(grid):
    """Native 10 m comparison-grid cell centers in the FRF frame."""
    crs, affine, shape = grid
    rows, cols = np.indices(shape)
    east, north = affine @ (cols + 0.5, rows + 0.5)
    e, n = (np.asarray(a).reshape(shape) for a in transform(crs, "EPSG:6542", east.ravel(), north.ravel()))
    e -= 901951.6805
    n -= 274093.1562
    s, c = np.sin(FRF_ANGLE_RAD), np.cos(FRF_ANGLE_RAD)
    return s * e + c * n, -c * e + s * n


def load_nisar_scene(unified, obs, expected_utc):
    """Validate provenance, calibrated power, masks and native grid registration."""
    source = obs["upstream_source"]
    hdf = source["source_hdf_metadata"]
    identity = hdf["identification"]
    attrs = source["attributes"]
    collection = source["collection"]["ShortName"]
    if (obs["sensor"] != "NISAR" or time_gap(obs["timestamp_utc"], expected_utc) != 0
            or source["granule"] != obs["id"] or identity["productVersion"] != source["version"]
            or hdf["hdf5_hh_hv_exact_array_match"] is not True
            or hdf["maximum_center_residual_m"] > 0.01
            or not {"HH", "HV"}.issubset(attrs["FREQUENCY_A_POLARIZATION"])
            or attrs["PRODUCT_TYPE"] != ["GCOV"]
            or source["release_identifier"] not in obs["id"].split("_")
            or time_gap(identity["frame_midpoint_utc"], expected_utc) != 0):
        raise ValueError("NISAR metadata does not identify verified frequency-A GCOV HH/HV")
    with rasterio.open(unified / obs["aligned_geotiff"]) as ds:
        tags = ds.tags()
        native = source["native_subset_grid"]
        a, b, west, d, e, north = native["affine"]
        native_grid = (a, b, d, e) == (10, 0, 0, -10)
        if (ds.crs.to_epsg() != native["epsg"] or not native_grid
                or (ds.transform.a, ds.transform.b, ds.transform.d, ds.transform.e) != (a, b, d, e)
                or (ds.transform.c - west) % 10 or (ds.transform.f - north) % 10
                or tags.get("source_id") != obs["id"]
                or time_gap(tags.get("acquisition_utc"), obs["timestamp_utc"]) != 0):
            raise ValueError("NISAR raster identity, timestamp or native 10 m grid differs from the manifest")
        looks = unwrap(ds, "nisar_numberOfLooks")
        subswath = unwrap(ds, "nisar_mask")
        exception = unwrap(ds, "nisar_inputDataExceptionMask")
        valid_support = (subswath > 0) & (subswath < 255) & (exception == 0) & (looks > 0)
        channels = {}
        errors = {}
        for pol, name in (("hh", "nisar_HHHH"), ("hv", "nisar_HVHV")):
            power = unwrap(ds, name)
            db = unwrap(ds, name + "_db")
            valid = unwrap(ds, name + "_valid") == 1
            if (not valid.any() or np.any(valid & (~valid_support | ~(power > 0) | ~np.isfinite(db)))
                    or ds.tags(ds.descriptions.index(name + "_db") + 1).get("units") != "dB"):
                raise ValueError(f"Invalid calibrated support or dB metadata for {pol.upper()}")
            residual = float(np.max(np.abs(10 * np.log10(power[valid]) - db[valid])))
            if residual > 1e-5:
                raise ValueError(f"Published dB does not match linear gamma-zero for {pol.upper()}")
            errors[pol] = residual
            channels[pol] = np.where(valid, db, np.nan)
        grid = ds.crs, ds.transform, ds.shape
    qa = {
        "id": obs["id"], "acquired_at": obs["timestamp_utc"],
        "collection": collection, "producer_version": source["version"], "crid": source["release_identifier"],
        "track": identity["trackNumber"], "frame": identity["frameNumber"],
        "orbit_direction": identity["orbitPassDirection"], "look_direction": identity["lookDirection"],
        "calibrated_quantity": "RTC gamma-zero (10 log10 of linear power), frequency A",
        "polarizations": ["HH", "HV"], "grid_epsg": 32618, "posting_m": POSTING_M,
        "joint_l_s": attrs.get("JOINT_OBSERVATION") == ["TRUE"],
        "valid_cells": {pol: int(np.isfinite(values).sum()) for pol, values in channels.items()},
        "looks_range": [float(looks[valid_support].min()), float(looks[valid_support].max())],
        "max_power_to_db_residual_db": errors,
        "source_url": source["cmr_url"], "product_guide": GCOV_GUIDE, "known_issues": KNOWN_ISSUES,
    }
    return grid, channels, qa


def despeckle(values, valid):
    """One masked 3×3 median pass. Sparse edge support keeps the original pixel."""
    pad = np.pad(np.where(valid, values, np.nan), 1, constant_values=np.nan)
    windows = np.lib.stride_tricks.sliding_window_view(pad, (3, 3)).reshape(*values.shape, 9)
    eligible = valid & (np.isfinite(windows).sum(axis=-1) >= 5)
    result = np.where(valid, values, np.nan)
    result[eligible] = np.nanmedian(windows[eligible], axis=-1)
    return result


def otsu(values):
    counts, edges = np.histogram(values, bins=128)
    mid = (edges[1:] + edges[:-1]) / 2
    weight = counts.cumsum()
    delta = (mid * counts).sum() * weight - (mid * counts).cumsum() * weight[-1]
    denom = weight * (weight[-1] - weight)
    scores = np.divide(delta**2, denom, out=np.zeros_like(delta), where=denom > 0)
    return float(edges[int(np.argmax(scores)) + 1])


def connected_offshore(mask, seeds):
    connected = mask & seeds
    queue = deque(map(tuple, np.argwhere(connected)))
    height, width = mask.shape
    while queue:
        r, c = queue.popleft()
        for i, j in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
            if 0 <= i < height and 0 <= j < width and mask[i, j] and not connected[i, j]:
                connected[i, j] = True
                queue.append((i, j))
    return connected


def sample_grid(grid):
    _, affine, shape = grid
    x, y = np.meshgrid(PROFILE_X, ROWS10)
    e, n = frf_to_utm(x, y)
    cols, rows = (~affine) @ (e, n)
    cols, rows = np.floor(cols).astype(int), np.floor(rows).astype(int)
    inside = (rows >= 0) & (rows < shape[0]) & (cols >= 0) & (cols < shape[1])
    return rows.clip(0, shape[0] - 1), cols.clip(0, shape[1] - 1), inside


def shoreline_rows(values, threshold, cross_shore, sample):
    r, c, inside = sample
    dark = values < threshold
    connected = connected_offshore(dark, cross_shore >= OFFSHORE_SEED_M)
    water = connected[r, c] & inside
    land = (values >= threshold)[r, c] & inside
    result = {}
    for index, y in enumerate(ROWS10):
        valid_pairs = [
            i for i in range(1, len(PROFILE_X) - 2)
            if land[index, i - 1:i + 1].all() and water[index, i + 1:i + 3].all()
            and (r[index, i], c[index, i]) != (r[index, i + 1], c[index, i + 1])
            and PROFILE_X[i] >= LAND_LIMIT_M and PROFILE_X[i + 1] < OFFSHORE_SEED_M
        ]
        if not np.any(land[index, PROFILE_X <= LAND_LIMIT_M]):
            reason = "No valid bright landward anchor"
        elif not np.any(water[index, PROFILE_X >= OFFSHORE_SEED_M]):
            reason = "No dark offshore anchor connected to this profile"
        elif len(valid_pairs) != 1:
            reason = "No unique land-to-connected-water crossing with two clear samples per side"
        else:
            i = valid_pairs[0]
            result[int(y)] = {"frf_y_m": int(y), "candidate_x_frf_m": int(PROFILE_X[i] + POSTING_M / 2),
                              "sampling_bracket_frf_m": [int(PROFILE_X[i]), int(PROFILE_X[i + 1])],
                              "status": "exploratory", "reason": None}
            continue
        result[int(y)] = {"frf_y_m": int(y), "candidate_x_frf_m": None, "status": "withheld", "reason": reason}
    return result


def segment(hh, shared, grid, cross_shore):
    """Freeze the HH-only extraction before comparing any optical or LiDAR data."""
    filtered = despeckle(hh, shared)
    values = filtered[shared]
    if values.size == 0 or np.ptp(values) == 0:
        raise ValueError("No calibrated HH intensity contrast on shared support")
    threshold = otsu(values)
    coords = sample_grid(grid)
    nominal = shoreline_rows(filtered, threshold, cross_shore, coords)
    variants = {
        "threshold_minus_1_db": shoreline_rows(filtered, threshold - 1, cross_shore, coords),
        "threshold_plus_1_db": shoreline_rows(filtered, threshold + 1, cross_shore, coords),
        "unfiltered_otsu": shoreline_rows(np.where(shared, hh, np.nan), otsu(hh[shared]), cross_shore, coords),
    }
    sensitivity = {}
    for key, variant in variants.items():
        positions = {y: row["candidate_x_frf_m"] for y, row in variant.items() if row["candidate_x_frf_m"] is not None}
        offsets = [abs(x - nominal[y]["candidate_x_frf_m"]) for y, x in positions.items()
                   if nominal[y]["candidate_x_frf_m"] is not None]
        sensitivity[key] = {"available_rows": len(positions), "matched_rows": len(offsets),
                            "median_absolute_shift_m": float(np.median(offsets)) if offsets else None,
                            "max_absolute_shift_m": max(offsets) if offsets else None}
    for y, row in nominal.items():
        row["sensitivity_positions_frf_m"] = {k: v[y]["candidate_x_frf_m"] for k, v in variants.items()}
    return nominal, {"otsu_threshold_db": threshold, "sensitivity": sensitivity,
                     "shared_hh_cells": int(shared.sum())}


def assess_comparability(rows, scene, optical_rows, environments, slope):
    """Use independent optical and gauge observations to test the waterline interpretation."""
    residuals = []
    matched, consistent = 0, set()
    radar_tide = water_level(environments.get(scene["id"], {}).get("nearest", []), scene["acquired_at"])
    optical_id, optical_time = None, None
    for y, row in rows.items():
        position = row["candidate_x_frf_m"]
        optical = optical_rows.get(y)
        if position is None or not optical or not radar_tide:
            continue
        optical_id = optical["acquisition_id"]
        optical_time = optical["acquired_at"]
        gap = time_gap(scene["acquired_at"], optical_time)
        if gap is None or abs(gap) > 12 * 3600:
            continue
        optical_tide = water_level(environments.get(optical_id, {}).get("nearest", []), optical_time)
        expected = correct_waterline(optical["ndwi"]["x_frf_m"], optical_time, optical_tide, radar_tide, slope)
        if expected["x_frf_m"] is None:
            continue
        matched += 1
        bounds = expected["slope_sensitivity_frf_m"] or [expected["x_frf_m"]] * 2
        # One full nominal posting from each sensor, deliberately added as a
        # conservative tolerance. This is a comparability check, not error propagation.
        tolerance = POSTING_M + optical["ndwi"]["posting_m"]
        if bounds[0] - tolerance <= position <= bounds[1] + tolerance:
            consistent.add(y)
        residual = position - expected["x_frf_m"]
        residuals.append(residual)
        row["optical_waterline_expected_at_nisar_tide_frf_m"] = expected["x_frf_m"]
        row["candidate_minus_expected_m"] = residual
        row["within_optical_comparability_band"] = y in consistent
    if matched and len(consistent) > matched / 2:
        status = "exploratory"
        reason = "Candidate is broadly consistent with the independent optical and gauge check; swash and timing remain uncertain"
    elif matched:
        status = "failed"
        reason = "Most HH transitions fall outside the independently modeled optical waterline band; instantaneous waterline interpretation failed"
        consistent.clear()
    else:
        status = "withheld"
        reason = "No suitable time-matched optical waterline, observed gauge levels and independent slope for comparability"
    details = {
        "status": status, "reason": reason, "n": matched,
        "within_band_rows": sum(bool(row.get("within_optical_comparability_band")) for row in rows.values()),
        "median_candidate_minus_expected_m": float(np.median(residuals)) if residuals else None,
        "method": "Optical crossing transferred to NISAR tide using independent calibrated slope; slope P10–P90 and one posting per sensor",
        "optical_id": optical_id, "optical_acquired_at": optical_time,
        "nisar_minus_optical_seconds": time_gap(scene["acquired_at"], optical_time), "nisar_tide": radar_tide,
    }
    return details, consistent


def compare_reference(rows, consistent, optical_reference, scene, slope, tide, environment, target):
    """Evaluate only the identical, physically comparable reference rows."""
    columns = ("nisar_raw", "nisar_tide", "sentinel2_raw", "sentinel2_tide")
    examples = []
    offset = time_gap(scene["acquired_at"], optical_reference[0]["reference_acquired_at"]) if optical_reference else None
    for sample in optical_reference:
        y = sample["frf_y_m"]
        if y not in consistent or offset is None or abs(offset) > 12 * 3600:
            continue
        reference = MHW
        if target == "survey_level_wet_dry_proxy":
            env = environment.get(sample["reference_id"], {}).get("nearest", [])
            reference = water_level(env, sample["reference_acquired_at"])
            if not reference:
                continue
        position = rows[y]["candidate_x_frf_m"]
        corrected = correct_waterline(position, scene["acquired_at"], tide, reference, slope)
        if corrected["x_frf_m"] is not None:
            examples.append({
                "frf_y_m": y, "reference_x_frf_m": sample["reference"],
                "nisar_raw": position, "nisar_tide": corrected["x_frf_m"],
                "sentinel2_raw": sample["raw"], "sentinel2_tide": sample["tide"],
            })
    reference_info = {
        "reference_rows": len(optical_reference), "reference_id": optical_reference[0]["reference_id"] if optical_reference else None,
        "reference_acquired_at": optical_reference[0]["reference_acquired_at"] if optical_reference else None,
        "nisar_minus_reference_seconds": offset,
        "sentinel2_minus_reference_seconds": optical_reference[0]["optical_minus_reference_seconds"] if optical_reference else None,
        "candidate_overlap_rows": sum(rows[s["frf_y_m"]]["candidate_x_frf_m"] is not None for s in optical_reference),
    }
    if not examples:
        reason = "No physically comparable HH waterline passed the optical/tide check on the LiDAR reference rows"
        if not optical_reference:
            reason = "No matched reference for this epoch and target"
        return {"status": "withheld", "reason": reason, "n": 0, "units": "m",
                "methods": None, **reference_info, "samples": []}
    metrics = {k: error_metrics([row[k] for row in examples], [row["reference_x_frf_m"] for row in examples]) for k in columns}
    return {"status": "exploratory", "reason": "Comparison restricted to reference rows with optical consistency; no LiDAR used in extraction",
            "n": len(examples), "units": "m", "methods": metrics, **reference_info, "samples": examples}


def candidate_geojson(rows, scene):
    features, start = [], []
    properties = {
        "status": "exploratory", "scientific_target": "Connected HH brightness transition",
        "waterline_status": scene["comparability"]["status"], "processing_version": VERSION,
        "acquisition_id": scene["id"], "acquired_at": scene["acquired_at"],
        "polarization": "HH", "units": "m", "native_posting_m": POSTING_M, "frf_x_positive": "seaward",
    }
    for y in (*ROWS10, int(ROWS10[-1]) + POSTING_M):
        row = rows.get(int(y), {})
        x = row.get("candidate_x_frf_m")
        if x is not None:
            start.append((x, int(y)))
        else:
            if len(start) > 1:
                geometry = {"type": "LineString", "coordinates": frf_to_lonlat(*map(np.asarray, zip(*start)))}
                features.append({"type": "Feature", "geometry": geometry, "properties": properties})
            elif start:
                geometry = {"type": "Point", "coordinates": frf_to_lonlat(*map(np.asarray, zip(*start)))[0]}
                features.append({"type": "Feature", "geometry": geometry, "properties": properties})
            start = []
    return {"type": "FeatureCollection", "features": features, "properties": properties}


def shoreline_experiment(epoch, channels, shared, grid, cross_shore, qa, optical, slopes, environment):
    date = qa["acquired_at"][:7]
    rows, extraction = segment(channels["hh"], shared, grid, cross_shore)
    candidates = [r["candidate_x_frf_m"] for r in rows.values() if r["candidate_x_frf_m"] is not None]
    slope = slopes.get(date)
    comparability, comparable_rows = assess_comparability(rows, qa, optical.rows.get(date, {}), environment, slope)
    targets = {}
    for target in ("fixed_mhw_contour", "survey_level_wet_dry_proxy"):
        matched_reference = [r for r in optical.validation[target]["samples"] if r["date"] == date]
        targets[target] = compare_reference(rows, comparable_rows, matched_reference, qa, slope,
                                            comparability["nisar_tide"], environment, target)
    if epoch == "june" and targets["fixed_mhw_contour"]["reference_rows"] == 0:
        targets["fixed_mhw_contour"]["reason"] = "June LiDAR has no matched fixed-MHW contour"
    scene = {
        **qa, **extraction,
        "status": "exploratory" if candidates else "withheld",
        "waterline_status": comparability["status"],
        "rows_examined": len(rows), "candidate_rows": len(candidates), "rejected_rows": len(rows) - len(candidates),
        "rejection_reasons": dict(Counter(r["reason"] for r in rows.values() if r["reason"])),
        "candidate_range_frf_m": [min(candidates), max(candidates)] if candidates else None,
        "environment": environment.get(qa["id"], {}).get("summary"),
        "comparability": comparability, "validation": targets, "rows": list(rows.values()),
    }
    return scene, candidate_geojson(rows, scene)
