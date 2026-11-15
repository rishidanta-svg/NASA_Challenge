"""Validated coastal products built from the verified Duck observations."""

import json
import logging

import numpy as np
import rasterio
from rasterio.warp import transform

from .coastal_physics import (MHW, correct_waterline, finite, setup_inputs, time_gap, timestamp,
                              water_level, wave_geometry, withheld)
from .reconstruction import ROWS10, frf_to_lonlat, frf_to_utm, _bilinear_sample

VERSION = "duck-physics-v1"
EPOCHS = ("june", "october")
OPTICAL = {"ndwi": (0.0, 10), "mndwi": (0.1, 20)}
X = np.arange(20.0, 151.0)
LOGGER = logging.getLogger(__name__)
VERTICAL = "NAVD88 (geoid12b)"


def unwrap(dataset, name):
    band = dataset.descriptions.index(name) + 1
    return dataset.read(band, masked=True).astype(float).filled(np.nan)


def crossing(values, threshold, posting_m):
    """Accept a unique land-to-water crossing with clear adjacent support."""
    wet = values >= threshold
    candidates = []
    for i in np.flatnonzero(~wet[:-1] & wet[1:]):
        left = values[i - 4:i + 1] if i >= 4 else []
        right = values[i + 1:i + posting_m + 1]
        if len(left) != 5 or len(right) != posting_m:
            continue
        if np.all(np.asarray(left) < threshold) and np.all(right >= threshold):
            candidates.append(float(X[i] + (threshold - values[i]) / (values[i + 1] - values[i])))
    return candidates[0] if len(candidates) == 1 else None


def optical_profiles(path):
    xg, yg = np.meshgrid(X, ROWS10)
    e, n = frf_to_utm(xg, yg)
    with rasterio.open(path) as ds:
        if ds.crs.to_epsg() != 32618 or ds.transform.b != 0 or ds.transform.d != 0:
            raise ValueError("Unexpected optical grid")
        clear = unwrap(ds, "s2_clear") == 1
        output = {}
        for index, (level, posting) in OPTICAL.items():
            valid = clear & (unwrap(ds, f"s2_{index}_valid") == 1)
            samples = _bilinear_sample(np.where(valid, unwrap(ds, f"s2_{index}"), np.nan), ds.transform, e, n)
            output[index] = {int(y): crossing(profile, level, posting) for y, profile in zip(ROWS10, samples)}
    return output


def error_metrics(predictions, reference):
    error = np.asarray(predictions) - reference
    return {"n": len(error), "rmse_m": float(np.sqrt(np.mean(error ** 2))),
            "mae_m": float(np.mean(np.abs(error))), "bias_m": float(np.mean(error))}


def comparison_metrics(rows):
    if not rows:
        return {"status": "withheld", "n": 0, "reason": "No common quality-screened reference samples"}
    keys = ("raw", "tide", "setup") if "setup" in rows[0] else ("raw", "tide")
    metrics = {key: error_metrics([r[key] for r in rows], [r["reference"] for r in rows]) for key in keys}
    raw = metrics["raw"]["rmse_m"]
    return {"status": "conditional", "n": len(rows), "methods": metrics,
            "rmse_reduction_percent": {key: 100 * (1 - metrics[key]["rmse_m"] / raw) if raw > 0 else None
                                       for key in keys if key != "raw"}}


def _wave(environment, acquired_at):
    measured = setup_inputs(environment, acquired_at)
    if measured:
        geometry = wave_geometry(measured["height_m"], measured["period_s"], measured["from_deg"])
        if geometry:
            return {**measured, **geometry, "station_depth_m": 17.4, "from_true_north": True}
    return None


def _coverage_payload(x, definition):
    return {
        "x_frf_m": x, "status": "conditional", "reasons": [], **definition,
    } if x is not None else {
        "x_frf_m": None, "status": "withheld",
        "reasons": ["No unique land-to-water crossing with contiguous clear pixels on both sides"], **definition,
    }


def collect_lines(rows, kind, scene):
    """Break lines across any withheld/unsampled transect."""
    features, points = [], []
    for y in (*ROWS10, int(ROWS10[-1]) + 10):
        product = rows.get(int(y), {}).get(kind, {})
        x = product.get("x_frf_m")
        if x is not None:
            points.append((x, int(y)))
        else:
            if len(points) >= 2:
                lonlat = frf_to_lonlat(*map(np.asarray, zip(*points)))
                features.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": lonlat},
                                 "properties": {"kind": kind, "processing_version": VERSION,
                                                "acquisition_id": scene["id"], "acquired_at": scene["timestamp_utc"],
                                                "target": "NOAA Duck MHW" if kind in ("tide", "setup") else None}})
            points = []
    return {"type": "FeatureCollection", "features": features}


def paired_lidar(root, metadata):
    """Verify native co-registration, common support and the published change raster."""
    values, grids, dates = [], [], []
    try:
        for epoch in (*EPOCHS, "delta_z"):
            path = root / "lidar" / f"lidar_{epoch}_native.tif"
            with rasterio.open(path) as ds:
                tags = ds.tags()
                if tags.get("VERTICAL_DATUM") != VERTICAL or ds.crs is None:
                    return withheld("Native LiDAR vertical datum or CRS is incompatible")
                grids.append((ds.crs, ds.transform, ds.shape))
                values.append(ds.read(1, masked=True).astype(float).filled(np.nan))
                if epoch in EPOCHS:
                    record = metadata["source"][epoch]
                    if (record["quality"]["coregQCFlag"] != 1 or record["vertical_datum"] != VERTICAL
                            or time_gap(record["timestamp_utc"], tags.get("ACQUISITION_TIME_UTC")) != 0):
                        return withheld("Native LiDAR coregistration QC, datum or timestamp did not pass")
                    dates.append({"epoch": epoch, "acquired_at": record["timestamp_utc"],
                                  "source_id": record["source_filename"], "quality": record["quality"]})
    except (OSError, rasterio.errors.RasterioError, KeyError):
        return withheld("Native paired LiDAR surveys or metadata are unavailable")
    if grids[0] != grids[1] or grids[1] != grids[2]:
        return withheld("Native LiDAR grids do not match")
    diff = values[1] - values[0]
    valid = np.isfinite(diff)
    if not valid.any() or not np.array_equal(valid, np.isfinite(values[2])) or not np.allclose(
            diff[valid], values[2][valid], atol=1e-6, rtol=0):
        return withheld("LiDAR difference does not match the paired native elevations and support")
    return {"status": "supported", "reasons": [], "acquisitions": dates, "datum": VERTICAL,
            "processing_version": f"verified-lidar-schema-{metadata['schema_version']}",
            "native_paired_cells": int(valid.sum()), "mean_m": float(diff[valid].mean()),
            "method": "October minus June on identical valid native 1 m cells"}


def _radar_acquisition(obs):
    if obs["sensor"] == "NISAR":
        upstream = obs.get("upstream_source", {})
        identification = upstream.get("source_hdf_metadata", {}).get("identification", {})
        return {"id": obs["id"], "acquired_at": obs["timestamp_utc"],
                "orbit_direction": identification.get("orbitPassDirection"), "track": identification.get("trackNumber"),
                "look_direction": identification.get("lookDirection"), "polarizations": ["HH", "HV"],
                "source_quality": {"collection": upstream.get("collection"), "producer_version": upstream.get("version"),
                                   "validity": "GCOV mask, input data exception mask and positive number of looks"}}
    props = obs.get("planetary_computer_item", {}).get("properties", {})
    tags = obs.get("radar_tag_checks", {})
    return {"id": obs["id"], "acquired_at": obs["timestamp_utc"], "incidence_near_far_deg": obs.get("incidence_angle_deg_near_far"),
            "local_incidence_deg": obs.get("local_incidence_angle_deg"), "orbit_direction": props.get("sat:orbit_state"),
            "track": props.get("sat:relative_orbit"), "polarizations": ["VV", "VH"],
            "look_direction": tags.get("vv", {}).get("LookDirection"), "source_quality": tags}


def radar_disagreement(root, unified, pairs, observations, environments):
    """Subtract each repeat pair in dB, checking the cross-date rasters and masks."""
    bands = {"NISAR": {"hh": "nisar_HHHH", "hv": "nisar_HVHV"},
             "Sentinel-1": {"vv": "s1_VV_gamma0", "vh": "s1_VH_gamma0"}}
    acquisitions, changes = {}, {}
    with rasterio.open(unified / "cross_date.tif") as dataset:
        grid = (dataset.crs, dataset.transform, dataset.shape)
        for sensor, variables in bands.items():
            pair = pairs.get(sensor, {})
            acquisitions[sensor] = {}
            values = {}
            for epoch in EPOCHS:
                obs = observations.get(pair.get(f"{epoch}_id"))
                if not obs or obs["sensor"] != sensor or time_gap(obs["timestamp_utc"], pair.get(f"{epoch}_utc")) != 0:
                    raise ValueError(f"Verified repeat-pass {sensor} identity unavailable")
                item = _radar_acquisition(obs)
                if sensor == "NISAR":
                    geom = root / "comparison" / f"nisar_{epoch}_radar_geometry.npz"
                    if geom.is_file():
                        with np.load(geom) as ancillary:
                            angles = ancillary["incidenceAngle"]
                            angles = angles[np.isfinite(angles) & (angles > 0) & (angles < 90)]
                            if angles.size:
                                item["incidence_grid_range_deg"] = [float(angles.min()), float(angles.max())]
                    item["source_quality"]["aligned_valid_cells"] = pair["valid_counts"].get("nisar_HHHH_db_change")
                item["environment"] = environments.get(obs["id"], {}).get("summary")
                acquisitions[sensor][epoch] = item
                with rasterio.open(unified / obs["aligned_geotiff"]) as scene:
                    if (scene.crs, scene.transform, scene.shape) != grid:
                        raise ValueError("Radar pairs must share the published comparison grid")
                    values[epoch] = {}
                    for pol, band in variables.items():
                        flag = f"{band}_valid" if sensor == "NISAR" else f"{band}_db_valid"
                        values[epoch][pol] = np.where(unwrap(scene, flag) == 1, unwrap(scene, f"{band}_db"), np.nan)
            for pol, band in variables.items():
                diff = values["october"][pol] - values["june"][pol]
                change_band = f"{band}_db_change"
                stored = np.where(unwrap(dataset, f"{change_band}_valid") == 1, unwrap(dataset, change_band), np.nan)
                if not np.allclose(diff, stored, rtol=0, atol=8e-6, equal_nan=True):
                    raise ValueError("Published calibrated radar changes do not match the signed dB difference")
                changes[pol] = diff
        strict = unwrap(dataset, "all_sensor_valid_overlap") == 1
        hh, hv, vv, vh = (changes[k] for k in ("hh", "hv", "vv", "vh"))
        matched = np.isfinite(hh) & np.isfinite(vv)
        opposite = ((hh > 0) & (vv < 0)) | ((hh < 0) & (vv > 0))
        if not matched.any() or np.any(strict & ~matched):
            return ({"status": "withheld", "reasons": ["Radar coverage does not support the declared matches"]}, None)

        cells = np.argwhere(opposite)
        cols = cells[:, 1, None] + np.array([0, 1, 1, 0, 0])
        rows = cells[:, 0, None] + np.array([0, 0, 1, 1, 0])
        xs, ys = dataset.transform @ (cols, rows)
        lng, lat = transform(dataset.crs, "EPSG:4326", xs.ravel().tolist(), ys.ravel().tolist())
        corners = np.column_stack((lng, lat)).reshape(-1, 5, 2)
        hh_hv = hh - hv
        vv_vh = vv - vh

        def value(arr, r, c):
            return float(arr[r, c]) if np.isfinite(arr[r, c]) else None
        features = [{
            "type": "Feature", "geometry": {"type": "Polygon", "coordinates": [corners[i].tolist()]},
            "properties": {"row": int(r), "column": int(c), "strict_overlap": bool(strict[r, c]),
                           "hh_change_db": value(hh, r, c), "hv_change_db": value(hv, r, c),
                           "vv_change_db": value(vv, r, c), "vh_change_db": value(vh, r, c),
                           "hh_minus_hv_change_db": value(hh_hv, r, c),
                           "vv_minus_vh_change_db": value(vv_vh, r, c),
                           "status": "conditional", "processing_version": VERSION},
        } for i, (r, c) in enumerate(cells)]
    gaps = {epoch: time_gap(acquisitions["Sentinel-1"][epoch]["acquired_at"],
                           acquisitions["NISAR"][epoch]["acquired_at"]) for epoch in EPOCHS}
    summary = {"status": "conditional",
               "reasons": ["Scene pairs have distinct acquisition times",
                           "Calibrated per-cell detection thresholds are unavailable; flags are directional only"],
               "matched_radar_cells": int(matched.sum()), "opposite_radar_cells": int(opposite.sum()),
               "strict_overlap_cells": int(strict.sum()), "opposite_strict_cells": int((opposite & strict).sum()),
               "noise_thresholds_db": None, "acquisitions": acquisitions, "s1_minus_nisar_seconds": gaps,
               "quantity": "October minus June RTC gamma-zero backscatter (dB), each sensor separately",
               "interpretation": "Opposite scattering changes indicate ambiguity in a radar-only interpretation",
               "processing_version": VERSION}
    return summary, {"type": "FeatureCollection", "features": features, "properties": summary}


class CoastalObservations:
    def __init__(self, root, unified, manifest, pairs, environment, lidar, lidar_refs):
        self.rows = {}
        self.layers = {}
        self.validation = {}
        self.lidar = paired_lidar(root, lidar)
        observations = {obs["id"]: obs for obs in manifest.get("observations", [])}
        paths = root / "physics/duck_foreshore_slopes.json"
        try:
            slopes = json.loads(paths.read_text()) if paths.is_file() else {}
        except (ValueError, OSError):
            slopes = {}
        checks = {"survey_level_wet_dry_proxy": [], "fixed_mhw_contour": []}
        for epoch in EPOCHS:
            self._build_epoch(epoch, unified, observations, pairs, environment, slopes, lidar_refs, checks)
        for target, rows in checks.items():
            wave_rows = [r for r in rows if "setup" in r]
            tide_rows = [{k: v for k, v in r.items() if k != "setup"} for r in rows]
            self.validation[target] = {
                "raw_vs_tide": comparison_metrics(tide_rows),
                "raw_vs_tide_vs_setup": comparison_metrics(wave_rows),
                "by_date": {date: comparison_metrics([r for r in tide_rows if r["date"] == date])
                            for date in sorted({r["date"] for r in rows})},
                "samples": rows,
            }
        self.radar = {"status": "withheld", "reasons": ["Unified cross-date radar data are unavailable"]}
        if (unified / "cross_date.tif").is_file():
            try:
                self.radar, layer = radar_disagreement(root, unified, pairs, observations, environment)
                if layer is not None and layer["features"]:
                    self.layers["radar-disagreement"] = layer
            except (OSError, KeyError, ValueError, rasterio.errors.RasterioError):
                LOGGER.warning("Cannot read the verified radar comparison", exc_info=True)
                self.radar = {"status": "withheld", "reasons": ["Verified radar comparison failed the data checks"]}

    def _build_epoch(self, epoch, unified, observations, pairs, environment, slopes, lidar_refs, checks):
        pair = pairs.get("Sentinel-2", {})
        scene = observations.get(pair.get(f"{epoch}_id"))
        if not scene or scene["sensor"] != "Sentinel-2" or time_gap(scene["timestamp_utc"], pair.get(f"{epoch}_utc")) != 0:
            return
        acquired_at = scene["timestamp_utc"]
        date = acquired_at[:7]
        env = environment.get(scene["id"], {})
        nearest = env.get("nearest", [])
        tide = water_level(nearest, acquired_at)
        wave = _wave(nearest, acquired_at)
        slope = slopes.get(date)

        lidar_pair = pairs.get("USACE LiDAR", {})
        survey = observations.get(lidar_pair.get(f"{epoch}_id"), {})
        survey_time = survey.get("timestamp_utc")
        survey_env = environment.get(survey.get("id"), {}).get("nearest", [])
        survey_tide = water_level(survey_env, survey_time)
        survey_wave = _wave(survey_env, survey_time)
        reference_gap = time_gap(acquired_at, survey_time)
        if slope and (survey_gap := time_gap(slope.get("evaluation_scan_utc"), survey_time)) is not None:
            # Legacy metadata round timestamps to seconds. Keep the two actual surveys distinct.
            if abs(survey_gap) > 1.1:
                slope = None
        native_survey = next((r for r in self.lidar.get("acquisitions", []) if r["epoch"] == epoch), {})
        native_gap = time_gap(survey_time, native_survey.get("acquired_at"))
        survey_matches = (survey.get("sensor") == "USACE LiDAR" and native_gap is not None and abs(native_gap) < 1
                          and survey["id"].split("#", 1)[0] == native_survey["source_id"])
        reference_supported = (survey_matches and reference_gap is not None
                               and abs(reference_gap) <= 12 * 3600 and slope is not None
                               and time_gap(slope.get("acquired_at"), survey_time) is not None
                               and time_gap(survey_time, slope.get("acquired_at")) > 0)
        try:
            opt = optical_profiles(unified / scene["aligned_geotiff"])
        except (OSError, ValueError, KeyError, rasterio.errors.RasterioError):
            LOGGER.warning("Cannot read the verified optical profiles for %s", scene["id"], exc_info=True)
            opt = {index: {} for index in OPTICAL}
        rows = self.rows[date] = {}
        for y in map(int, ROWS10):
            raw = opt["ndwi"].get(y)
            rows[y] = {
                index: _coverage_payload(opt[index].get(y), {"index": index.upper(), "threshold": level, "posting_m": posting})
                for index, (level, posting) in OPTICAL.items()
            }
            rows[y].update({
                "date": date, "acquisition_id": scene["id"], "acquired_at": acquired_at,
                "environment": env.get("summary"), "optical_qa": scene.get("aoi_optical_qa"),
                "tide": correct_waterline(raw, acquired_at, tide, MHW, slope),
                "setup": correct_waterline(raw, acquired_at, tide, MHW, slope, wave=wave) if wave
                else withheld("No time-matched wave observation supports reverse shoaling and refraction"),
            })
            for index in OPTICAL:
                if rows[y][index]["x_frf_m"] is not None:
                    rows[y][index]["reasons"] = ["Optical waterline position varies with sea state, tide and geolocation"]
            if not reference_supported or raw is None:
                continue
            refs = lidar_refs.get((date, y), {})
            targets = [
                ("survey_level_wet_dry_proxy", survey_tide, refs.get("B1_wetdry"), survey_wave),
                ("fixed_mhw_contour", MHW, refs.get("MHW") if abs(refs.get("MHW_z", -1) - MHW["value"]) <= 0.002 else None, None),
            ]
            for target, reference, reference_x, ref_wave in targets:
                if not reference or not finite(reference_x):
                    continue
                tide_only = correct_waterline(raw, acquired_at, tide, reference, slope)
                if tide_only["x_frf_m"] is None:
                    continue
                sample = {"date": date, "frf_y_m": y, "raw": raw, "tide": tide_only["x_frf_m"],
                          "reference": reference_x, "reference_acquired_at": survey_time,
                          "reference_id": survey["id"], "optical_acquired_at": acquired_at,
                          "optical_id": scene["id"], "optical_minus_reference_seconds": reference_gap}
                if wave is not None and (target == "fixed_mhw_contour" or ref_wave is not None):
                    sample["setup"] = correct_waterline(raw, acquired_at, tide, reference, slope, wave=wave,
                                                         reference_wave=ref_wave)["x_frf_m"]
                checks[target].append(sample)

        for kind in ("ndwi", "mndwi", "tide", "setup"):
            layer = collect_lines(rows, kind, scene)
            if layer["features"]:
                self.layers[f"physics-s2-{kind}-{epoch}"] = layer

    def transect(self, y, origin):
        waterlines = []
        for date, rows in self.rows.items():
            record = rows.get(int(y))
            if not record:
                continue
            converted = {}
            for kind in ("ndwi", "mndwi", "tide", "setup"):
                product = record[kind]
                position = product["x_frf_m"]
                converted[kind] = {**product, "x_m": position - origin if position is not None else None}
            waterlines.append({**record, **converted})
        return waterlines

    def summary(self, *, include_samples=False):
        return {
            "processing_version": VERSION, "status": "conditional" if self.rows else "withheld",
            "reasons": ["Duck retrospective observation workflow"] if self.rows else ["Verified optical pair is unavailable"],
            "coordinate": "FRF x increases seaward (m)",
            "target": MHW, "terrain": self.lidar, "radar_disagreement": self.radar,
            "validation": {
                "scope": "Local retrospective comparison of fixed, cloud-masked optical edges against time-separated LiDAR",
                "reference_notes": {
                    "survey_level_wet_dry_proxy": "LiDAR seaward-most returns at survey time, normalized to the observed survey-time gauge level",
                    "fixed_mhw_contour": "LiDAR contour at 0.36 m NAVD88; NOAA Duck MHW is 0.359 m NAVD88",
                },
                "targets": {k: {name: v for name, v in v.items() if include_samples or name != "samples"}
                            for k, v in self.validation.items()},
            },
        }
