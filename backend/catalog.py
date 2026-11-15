"""Adapt the verified pipeline and unified 28-acquisition bundles to the frontend data contract."""

from datetime import datetime
import json
import math
from math import cos, radians, sin
from pathlib import Path

from rasterio.warp import transform

from .coastal_observations import CoastalObservations, VERSION
from .reconstruction import CoastalReconstructionStore

BBOX = [-75.753384, 36.183704, -75.750335, 36.188260]
VERTICAL = "NAVD88 (geoid12b)"
EPOCHS = {"june": "June 2026", "october": "October 2026"}
LIDAR = "USACE FRF dune LiDAR DEM"
RADAR = "NASA NISAR L-band GCOV"
S1_SOURCE = "ESA Sentinel-1 C-band IW GRDH RTC"
S2_SOURCE = "ESA Sentinel-2 L2A MSI"
CHANGE = ("diverging", [(-2.5, "#b23b22"), (0, "#f1e9d7"), (2.5, "#096980")])
RADAR_CHANGE = ("diverging", [(-12, "#aa4b1a"), (0, "#f6ecdb"), (12, "#2747a0")])
NDWI = ("diverging", [(-0.8, "#c29b61"), (0.0, "#f5efe0"), (0.8, "#0b648f")])
NDWI_CHANGE = ("diverging", [(-0.7, "#b23b22"), (0.0, "#f5efe0"), (0.7, "#0b648f")])
POWER = ("sequential", [(-34, "#171433"), (-18, "#497584"), (1, "#fbf4c1")])
HEIGHT = ("sequential", [(0, "#18375c"), (3, "#43a098"), (8, "#f5df9c")])
FRACTION = ("sequential", [(0, "#34374c"), (1, "#77ddd0")])
VALID = ("categorical", [(0, "#b35235"), (1, "#5bd3a5")])

SENSOR_NORM = {
    "NISAR": "NISAR",
    "Sentinel-1": "SENTINEL-1",
    "Sentinel-2": "SENTINEL-2",
    "USACE LiDAR": "LIDAR",
}
PRODUCT_NORM = {
    "NISAR": "L2_GCOV",
    "Sentinel-1": "IW_GRDH_1SDV_RTC",
    "Sentinel-2": "L2A_MSI",
    "USACE LiDAR": "duneLidarDEM",
}
MONTH_NAMES = {
    "06": "June",
    "07": "July",
    "08": "August",
    "09": "September",
    "10": "October",
}


def read_json(path):
    return json.loads(path.read_text(encoding="utf8")) if path.is_file() else {}


def _clean_val(val):
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
        return val
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return val


def _read_parquet_rows(path: Path):
    if not path.is_file():
        return []
    try:
        import pyarrow.parquet as pq
        rows = pq.read_table(path).to_pylist()
        return [{k: _clean_val(v) for k, v in r.items()} for r in rows]
    except Exception:
        return []


def _format_date_label(date_str: str) -> str:
    parts = date_str.split("-")
    if len(parts) != 3:
        return date_str
    month = MONTH_NAMES.get(parts[1], parts[1])
    return f"{month} {int(parts[2])}, {parts[0]}"


class Catalog:
    def __init__(self, root: Path, unified_root: Path = None):
        self.root = root
        self.unified_root = unified_root if unified_root is not None else (root / "unified")
        lidar = read_json(root / "lidar/manifest.json")
        comparison = read_json(root / "comparison/manifest.json")
        self.lidar = lidar
        self.bounds = lidar.get("study_wsen_epsg4326", comparison.get("study_wsen_epsg4326", BBOX))
        self.range = lidar.get("frf_y_range_m", comparison.get("frf_y_range_m", [700, 1190]))
        self.layers = {}
        self.layer_bands = {}
        self.acquisitions = []
        self.transects = {}
        self.epochs = []

        # Unified 28-acquisition dataset metadata & environmental joins
        self.unified_manifest = read_json(self.unified_root / "acquisition_manifest.json")
        self.observation_groups = read_json(self.unified_root / "observation_groups.json")
        self.cross_date_pairs = read_json(self.unified_root / "cross_date_pairs.json")
        self.geospatial_qa = read_json(self.unified_root / "geospatial_qa.json")
        self.verification = read_json(self.unified_root / "verification.json")
        self.environment_qa = read_json(self.unified_root / "environment/environment_qa.json")
        self.acq_environment = {}
        self.cross_date_environment = []

        self.reconstruction = CoastalReconstructionStore(root)
        self._load_unified_environment()
        self.create_layers(lidar, comparison)
        self.create_boundary_layers(comparison)
        if self.unified_manifest.get("observations"):
            self._load_unified_acquisitions()
            self.create_unified_layers()
        else:
            self.acquisitions.extend(self.reconstruction.extra_acquisitions)
        self.coastal = CoastalObservations(
            self.root, self.unified_root, self.unified_manifest, self.cross_date_pairs,
            self.acq_environment, self.lidar, self.reconstruction.lidar_refs,
        )
        self.create_physics_layers()
        self.create_transects()

    def _load_unified_environment(self):
        env_dir = self.unified_root / "environment"
        if not env_dir.is_dir():
            return
        nearest_rows = _read_parquet_rows(env_dir / "nearest.parquet")
        tide_rows = _read_parquet_rows(env_dir / "tide_stage.parquet")
        ant_rows = _read_parquet_rows(env_dir / "antecedent.parquet")
        self.cross_date_environment = _read_parquet_rows(env_dir / "cross_date.parquet")

        nearest_by_id = {}
        for r in nearest_rows:
            nearest_by_id.setdefault(r["id"], []).append(r)

        tide_by_id = {r["id"]: r for r in tide_rows}

        ant_by_id = {}
        for r in ant_rows:
            ant_by_id.setdefault(r["id"], []).append(r)

        all_ids = set(nearest_by_id) | set(tide_by_id) | set(ant_by_id)
        for oid in all_ids:
            nrows = nearest_by_id.get(oid, [])
            trow = tide_by_id.get(oid, {})
            arows = ant_by_id.get(oid, [])

            lookup = {(r["station_id"], r["variable"]): r for r in nrows}
            ant_lookup = {(r["station_id"], r["variable"], r["window_hours"]): r for r in arows}

            def _val(station, var):
                item = lookup.get((station, var))
                return round(float(item["value"]), 3) if item and item.get("value") is not None else None

            def _off(station, var):
                item = lookup.get((station, var))
                return round(float(item["offset_seconds"]), 1) if item and item.get("offset_seconds") is not None else None

            def _ts(station, var):
                item = lookup.get((station, var))
                return item.get("timestamp_utc") if item else None

            rain24 = ant_lookup.get(("USACE FRF rain gauge", "rain_10min", 24), {}).get("rain_sum_mm")
            rain72 = ant_lookup.get(("USACE FRF rain gauge", "rain_10min", 72), {}).get("rain_sum_mm")
            hs24_max = ant_lookup.get(("USACE FRF Waverider 17m", "wave_significant_height", 24), {}).get("max")

            qualifying = sum(1 for r in nrows if r.get("value") is not None)
            summary = {
                "water_level_m_mllw": _val("NOAA CO-OPS 8651370", "water_level"),
                "water_level_timestamp_utc": _ts("NOAA CO-OPS 8651370", "water_level"),
                "water_level_offset_s": _off("NOAA CO-OPS 8651370", "water_level"),
                "tide_prediction_m_mllw": _val("NOAA CO-OPS 8651370", "tide_prediction"),
                "predicted_tide_stage": trow.get("predicted_tide_stage"),
                "predicted_tide_slope_m_per_h": (
                    round(float(trow["predicted_tide_slope_m_per_h"]), 3)
                    if trow.get("predicted_tide_slope_m_per_h") is not None
                    else None
                ),
                "observed_minus_predicted_m": (
                    round(float(trow["observed_minus_predicted_m_at_obs_time"]), 3)
                    if trow.get("observed_minus_predicted_m_at_obs_time") is not None
                    else None
                ),
                "wave_hs_m_17m": _val("USACE FRF Waverider 17m", "wave_significant_height"),
                "wave_tp_s_17m": _val("USACE FRF Waverider 17m", "wave_peak_period"),
                "wave_dir_deg_17m": _val("USACE FRF Waverider 17m", "wave_peak_direction"),
                "wave_17m_timestamp_utc": _ts("USACE FRF Waverider 17m", "wave_significant_height"),
                "wave_17m_offset_s": _off("USACE FRF Waverider 17m", "wave_significant_height"),
                "wave_hs_m_26m": _val("USACE FRF Waverider 26m", "wave_significant_height"),
                "wave_tp_s_26m": _val("USACE FRF Waverider 26m", "wave_peak_period"),
                "wind_speed_ms": (
                    _val("NOAA CO-OPS 8651370", "wind_speed")
                    if _val("NOAA CO-OPS 8651370", "wind_speed") is not None
                    else _val("NDBC DUKN7", "wind_speed")
                ),
                "wind_dir_deg": (
                    _val("NOAA CO-OPS 8651370", "wind_direction")
                    if _val("NOAA CO-OPS 8651370", "wind_direction") is not None
                    else _val("NDBC DUKN7", "wind_direction")
                ),
                "wind_gust_ms": _val("NOAA CO-OPS 8651370", "wind_gust"),
                "rain_10min_mm": _val("USACE FRF rain gauge", "rain_10min"),
                "rain_24h_mm": round(float(rain24), 2) if rain24 is not None else None,
                "rain_72h_mm": round(float(rain72), 2) if rain72 is not None else None,
                "wave_hs_24h_max_m_17m": round(float(hs24_max), 3) if hs24_max is not None else None,
                "total_water_level_2pct_navd88_m": _val("USACE FRF lidar wave runup", "total_water_level_2pct"),
                "qualifying_station_matches": qualifying,
            }
            self.acq_environment[oid] = {
                "id": oid,
                "acquisition_utc": trow.get("acquisition_utc"),
                "group": trow.get("group"),
                "summary": summary,
                "tide_stage": trow,
                "nearest": nrows,
                "antecedent": arows,
            }

    def _load_unified_acquisitions(self):
        """Replace self.acquisitions with all 28 verified acquisitions from acquisition_manifest.json."""
        self.acquisitions = []
        valid_by_id = self.geospatial_qa.get("raster_valid_counts_by_acquisition", {})
        study_cells = self.geospatial_qa.get("study_cells", 1450)

        for obs in self.unified_manifest.get("observations", []):
            raw_sensor = obs["sensor"]
            sensor = SENSOR_NORM.get(raw_sensor, "OTHER")
            product = PRODUCT_NORM.get(raw_sensor, raw_sensor)
            oid = obs["id"]
            t = obs["timestamp_utc"]
            up = obs.get("upstream_source", {})
            stac = obs.get("planetary_computer_item", {})
            props = stac.get("properties", {})

            acquired_end = None
            polarizations = None
            orbit_direction = None
            cloud_cover_pct = None
            source_url = None

            if sensor == "NISAR":
                acquired_end = up.get("acquisition_end_utc")
                polarizations = ["HH", "HV"]
                orbit_direction = "descending"
                source_url = up.get("cmr_url")
            elif sensor == "LIDAR":
                source_url = up.get("file_server_url")
            elif sensor == "SENTINEL-1":
                polarizations = ["VV", "VH"]
                orbit_state = props.get("sat:orbit_state", "ascending")
                orbit_direction = orbit_state.lower() if orbit_state else "ascending"
                for link in stac.get("links", []):
                    if link.get("rel") == "self":
                        source_url = link.get("href")
                        break
            elif sensor == "SENTINEL-2":
                aoi_qa = obs.get("aoi_optical_qa", {})
                if aoi_qa and aoi_qa.get("study_cells"):
                    clear = aoi_qa.get("clear_cells", 0)
                    cloud_cover_pct = round(max(0.0, (1.0 - clear / float(aoi_qa["study_cells"])) * 100.0), 2)
                elif obs.get("tile_cloud_percent") is not None:
                    cloud_cover_pct = round(float(obs["tile_cloud_percent"]), 2)
                for link in stac.get("links", []):
                    if link.get("rel") == "self":
                        source_url = link.get("href")
                        break

            vcounts = valid_by_id.get(oid, {})
            qa_info = {
                "study_cells": study_cells,
                "valid_counts": vcounts,
                "observation_group": obs.get("group"),
                "observation_index": obs.get("observation_index"),
                "offset_from_reference_seconds": obs.get("offset_from_reference_seconds"),
            }
            if sensor == "SENTINEL-1":
                qa_info["relative_orbit"] = props.get("sat:relative_orbit")
                qa_info["platform"] = props.get("platform")
                qa_info["incidence_angle_deg_near_far"] = obs.get("incidence_angle_deg_near_far")
                qa_info["valid_study_cells"] = vcounts.get("s1_VV_gamma0_db_valid", 1450)
            elif sensor == "SENTINEL-2":
                qa_info["relative_orbit"] = props.get("sat:relative_orbit")
                qa_info["tile_cloud_percent"] = obs.get("tile_cloud_percent")
                qa_info["aoi_optical_qa"] = obs.get("aoi_optical_qa")
                qa_info["valid_study_cells"] = vcounts.get("s2_ndwi_valid", 0)
            elif sensor == "NISAR":
                qa_info["rtc_applied"] = True
                qa_info["track"] = 69
                qa_info["frame"] = 70
                qa_info["valid_study_cells"] = vcounts.get("nisar_HHHH_valid", 1310)
            elif sensor == "LIDAR":
                qa_info["quality"] = up.get("quality")
                qa_info["valid_study_cells"] = vcounts.get("lidar_valid", 0)

            env_summary = self.acq_environment.get(oid, {}).get("summary")
            self.acquisitions.append({
                "id": oid,
                "sensor": sensor,
                "product": product,
                "acquired_at": t,
                "acquired_end": acquired_end,
                "group": obs.get("group"),
                "observation_index": obs.get("observation_index"),
                "reference_id": obs.get("reference_id"),
                "reference_utc": obs.get("reference_utc"),
                "offset_from_reference_seconds": obs.get("offset_from_reference_seconds"),
                "aligned_geotiff": obs.get("aligned_geotiff"),
                "polarizations": polarizations,
                "orbit_direction": orbit_direction,
                "cloud_cover_pct": cloud_cover_pct,
                "source_url": source_url,
                "qa": qa_info,
                "environment": env_summary,
            })

    def register(self, id, bundle, filename, slot, title, sensor, units, quantity,
                 provenance, palette=None, when=None, epoch_label="October − June 2026", dem=False,
                 path_override: Path = None, band: int = 1, group_override: str = None, qa: dict = None):
        terrain = sensor == "LIDAR"
        path = path_override if path_override is not None else (self.root / bundle / (filename + ".tif"))
        if not path.is_file():
            return
        descriptor = {
            "id": id, "slot": slot, "title": title,
            "sensor": sensor,
            "group": group_override or ("measured" if terrain else "sensor"),
            "kind": "raster_dem" if dem else "raster_xyz",
            "tiles": [f"/api/tiles/{id}/{{z}}/{{x}}/{{y}}.png"], "tile_size": 256,
            "bounds": None if dem else self.bounds, "units": units, "quantity": quantity,
            "acquired_at": when, "reference_date": when[:10] if when else None,
            "epoch_label": epoch_label, "native_crs": "EPSG:32618",
            "native_resolution_m": 1 if bundle == "lidar" and units == "m" else 10,
            "minzoom": 0 if dem else 12, "maxzoom": 18 if bundle == "lidar" else 16,
            "vertical_datum": VERTICAL if terrain and units == "m" else None,
            "inferred": False, "status": "available", "provenance": provenance,
        }
        if qa:
            descriptor["qa"] = qa
        if dem:
            descriptor["encoding"] = "terrarium"
        if palette:
            kind, stops = palette
            descriptor["colormap"] = {"type": kind, "min": stops[0][0], "max": stops[-1][0], "stops": stops}
        self.layers[id] = (path, descriptor)
        self.layer_bands[id] = int(band)

    def create_layers(self, lidar, comparison):
        lidar_records = lidar.get("source", {})
        radar_records = comparison.get("source", {}).get("nisar", {})
        ls = {"source": LIDAR, "processing": "Bare-earth DEM in NAVD88 (geoid12b)"}
        ns = {"source": RADAR, "processing": "Radiometrically terrain-corrected gamma-zero power"}
        for epoch, label in EPOCHS.items():
            if epoch in lidar_records:
                item = lidar_records[epoch]
                t = item["timestamp_utc"]
                provenance = dict(ls, product_id=item["source_filename"], url=item["file_server_url"])
                self.acquisitions.append({
                    "id": item["source_filename"] + ":" + t, "sensor": "LIDAR", "product": "duneLidarDEM",
                    "acquired_at": t, "source_url": item["file_server_url"], "qa": item["quality"],
                })
                self.epochs.append({"label": label, "survey_start": t, "product_id": item["source_filename"]})
                self.register(f"lidar-elevation-{epoch}", "lidar", f"lidar_{epoch}_utm_1m",
                              "lidar-elevation", f"LiDAR elevation · {label}", "LIDAR", "m",
                              "Bare-earth elevation", provenance, HEIGHT, t, label)
                self.register(f"lidar-dem-{epoch}", "lidar", f"lidar_{epoch}_utm_1m",
                              "lidar-dem", f"USACE LiDAR terrain · {label}", "LIDAR", "m",
                              "Bare-earth elevation, with AWS terrain in gaps",
                              dict(provenance, source=LIDAR + " / AWS Terrarium fallback"), when=t,
                              epoch_label=label, dem=True)
            if epoch in radar_records:
                item = radar_records[epoch]
                hdf = item.get("source_hdf_metadata", {}).get("identification", {})
                t = item["acquisition_start_utc"]
                stop = hdf.get("zeroDopplerEndTime")
                provenance = dict(ns, product_id=item["granule"], url=item["cmr_url"])
                self.acquisitions.append({
                    "id": item["granule"], "sensor": "NISAR", "product": "L2_GCOV",
                    "acquired_at": t, "acquired_end": stop + "Z" if stop else item["acquisition_end_utc"],
                    "polarizations": ["HH", "HV"], "orbit_direction": "descending",
                    "source_url": item["cmr_url"], "qa": {"rtc_applied": True, "track": 69, "frame": 70},
                })
                for pol in ("hh", "hv"):
                    self.register(f"nisar-{pol}-{epoch}", "comparison", f"nisar_{epoch}_{pol.upper() * 2}_db",
                                  f"nisar-{pol}", f"NISAR {pol.upper()} · {label}", "NISAR", "dB",
                                  f"{pol.upper()} backscatter", provenance, POWER, t, label,
                                  qa={"valid_study_cells": 1310, "study_cells": 1450})
                self.register(f"nisar-quality-{epoch}", "comparison", f"nisar_{epoch}_HHHH_valid",
                              "nisar-quality", f"NISAR valid-data mask · {label}", "NISAR", "flag",
                              "GCOV usable HH pixels (1 valid; 0 excluded)", provenance, VALID, t, label,
                              qa={"valid_study_cells": 1310, "study_cells": 1450})
        self.register("lidar-dz-2026-oct-jun", "lidar", "lidar_delta_z_utm_1m", "lidar-dz",
                      "LiDAR elevation change", "LIDAR", "m", "Measured elevation difference", ls, CHANGE,
                      qa={"native_1m_paired_cells": 17466, "aligned_10m_valid_cells": 168})
        for pol in ("hh", "hv"):
            self.register(f"nisar-{pol}-change", "comparison", f"nisar_{pol.upper() * 2}_change_db",
                          f"nisar-{pol}-change", f"NISAR {pol.upper()} backscatter change", "NISAR", "dB",
                          "Radar scattering change", ns, RADAR_CHANGE,
                          qa={"valid_study_cells": 1310, "study_cells": 1450})
        self.register("lidar-paired-coverage", "lidar", "lidar_dz_coverage", "lidar-coverage",
                      "Paired LiDAR coverage", "LIDAR", "fraction", "Valid paired area per 10 m cell",
                      ls, FRACTION, qa={"valid_study_cells": 168, "study_cells": 1450})

    def create_unified_layers(self):
        """Register Sentinel-1, Sentinel-2, and cross-date comparison layers from unified GeoTIFFs."""
        valid_by_id = self.geospatial_qa.get("raster_valid_counts_by_acquisition", {})
        study_cells = self.geospatial_qa.get("study_cells", 1450)

        for obs in self.unified_manifest.get("observations", []):
            raw_sensor = obs["sensor"]
            oid = obs["id"]
            when = obs["timestamp_utc"]
            date_str = when[:10]
            date_label = _format_date_label(date_str)
            tif_rel = obs.get("aligned_geotiff")
            if not tif_rel:
                continue
            tif_path = self.unified_root / tif_rel
            if not tif_path.is_file():
                continue
            stac = obs.get("planetary_computer_item", {})
            props = stac.get("properties", {})
            source_url = None
            for link in stac.get("links", []):
                if link.get("rel") == "self":
                    source_url = link.get("href")
                    break
            vcounts = valid_by_id.get(oid, {})

            if raw_sensor == "Sentinel-1":
                rel_orbit = props.get("sat:relative_orbit", 106)
                if date_str == "2026-06-16":
                    ep_label = f"{date_label} (Track {rel_orbit} · June group)"
                elif date_str == "2026-06-30":
                    ep_label = f"{date_label} (Track {rel_orbit} · June repeat-pass)"
                elif date_str == "2026-10-16":
                    ep_label = f"{date_label} (Track {rel_orbit} · October group)"
                else:
                    ep_label = f"{date_label} (Track {rel_orbit})"
                prov = {
                    "source": S1_SOURCE,
                    "product_id": oid,
                    "processing": "Planetary Computer RTC gamma-naught converted to dB on 10 m EPSG:32618 grid",
                    "url": source_url,
                }
                qa_meta = {
                    "valid_study_cells": vcounts.get("s1_VV_gamma0_db_valid", 1450),
                    "study_cells": study_cells,
                    "relative_orbit": rel_orbit,
                    "orbit_direction": "ascending",
                    "observation_group": obs.get("group"),
                    "offset_from_reference_seconds": obs.get("offset_from_reference_seconds"),
                }
                self.register(
                    f"s1-vv-{date_str}", "unified", tif_path.stem, "s1-vv",
                    f"Sentinel-1 VV · {date_label}", "SENTINEL-1", "dB",
                    "C-band RTC VV gamma-zero backscatter", prov, POWER, when, ep_label,
                    path_override=tif_path, band=2, qa=qa_meta,
                )
                self.register(
                    f"s1-vh-{date_str}", "unified", tif_path.stem, "s1-vh",
                    f"Sentinel-1 VH · {date_label}", "SENTINEL-1", "dB",
                    "C-band RTC VH gamma-zero backscatter", prov, POWER, when, ep_label,
                    path_override=tif_path, band=6, qa=qa_meta,
                )

            elif raw_sensor == "Sentinel-2":
                valid_ndwi = vcounts.get("s2_ndwi_valid", 0)
                if valid_ndwi < 100:
                    # Skip 100% cloud/shadow masked scenes in the active tile slot so timeline scrubbing
                    # resolves to clear optical scenes; all 18 scenes remain in /api/acquisitions.
                    continue
                if date_str == "2026-06-18":
                    ep_label = f"{date_label} (June group · {valid_ndwi}/{study_cells} clear)"
                elif date_str == "2026-10-16":
                    ep_label = f"{date_label} (October group · {valid_ndwi}/{study_cells} clear)"
                else:
                    ep_label = f"{date_label} ({valid_ndwi}/{study_cells} clear)"
                prov = {
                    "source": S2_SOURCE,
                    "product_id": oid,
                    "processing": "SCL cloud/shadow-screened surface reflectance NDWI ((B03−B08)/(B03+B08)) on 10 m grid",
                    "url": source_url,
                }
                qa_meta = {
                    "valid_study_cells": valid_ndwi,
                    "study_cells": study_cells,
                    "aoi_optical_qa": obs.get("aoi_optical_qa"),
                    "observation_group": obs.get("group"),
                    "offset_from_reference_seconds": obs.get("offset_from_reference_seconds"),
                }
                self.register(
                    f"s2-ndwi-{date_str}", "unified", tif_path.stem, "s2-index",
                    f"Sentinel-2 NDWI · {date_label}", "SENTINEL-2", "index",
                    "Normalized Difference Water Index (NDWI)", prov, NDWI, when, ep_label,
                    path_override=tif_path, band=14, qa=qa_meta,
                )

        # Register cross-date comparison layers from cross_date.tif
        cross_tif = self.unified_root / "cross_date.tif"
        if cross_tif.is_file():
            s1_pair = self.cross_date_pairs.get("Sentinel-1", {})
            s2_pair = self.cross_date_pairs.get("Sentinel-2", {})
            s1_prov = {
                "source": S1_SOURCE,
                "product_id": f"{s1_pair.get('october_id', '')} - {s1_pair.get('june_id', '')}",
                "processing": "Repeat-pass Track 106 RTC dB difference (Oct 16, 2026 minus Jun 30, 2026)",
            }
            s1_qa = {
                "valid_study_cells": 1450,
                "study_cells": study_cells,
                "june_id": s1_pair.get("june_id"),
                "october_id": s1_pair.get("october_id"),
                "june_utc": s1_pair.get("june_utc"),
                "october_utc": s1_pair.get("october_utc"),
            }
            self.register(
                "s1-vv-change", "unified", "cross_date", "s1-vv-change",
                "Sentinel-1 VV backscatter change", "SENTINEL-1", "dB",
                "C-band VV backscatter difference (Oct 16 − Jun 30, 2026 · Track 106)",
                s1_prov, RADAR_CHANGE, None, "Oct 16 − Jun 30, 2026 (Track 106)",
                path_override=cross_tif, band=10, qa=s1_qa,
            )
            self.register(
                "s1-vh-change", "unified", "cross_date", "s1-vh-change",
                "Sentinel-1 VH backscatter change", "SENTINEL-1", "dB",
                "C-band VH backscatter difference (Oct 16 − Jun 30, 2026 · Track 106)",
                s1_prov, RADAR_CHANGE, None, "Oct 16 − Jun 30, 2026 (Track 106)",
                path_override=cross_tif, band=12, qa=s1_qa,
            )
            s2_prov = {
                "source": S2_SOURCE,
                "product_id": f"{s2_pair.get('october_id', '')} - {s2_pair.get('june_id', '')}",
                "processing": "Clear-sky NDWI difference (Oct 16, 2026 minus Jun 18, 2026)",
            }
            s2_qa = {
                "valid_study_cells": 1442,
                "study_cells": study_cells,
                "june_id": s2_pair.get("june_id"),
                "october_id": s2_pair.get("october_id"),
                "june_utc": s2_pair.get("june_utc"),
                "october_utc": s2_pair.get("october_utc"),
            }
            self.register(
                "s2-ndwi-change", "unified", "cross_date", "s2-ndwi-change",
                "Sentinel-2 NDWI change", "SENTINEL-2", "index",
                "Optical NDWI difference (Oct 16 − Jun 18, 2026)",
                s2_prov, NDWI_CHANGE, None, "Oct 16 − Jun 18, 2026 (1,442 clear cells)",
                path_override=cross_tif, band=28, qa=s2_qa,
            )
            overlap_prov = {
                "source": "POLTERGEIST Unified 4-Sensor Comparison Grid",
                "product_id": "cross_date.tif:all_sensor_valid_overlap",
                "processing": "Logical AND of NISAR, USACE LiDAR, Sentinel-1, and Sentinel-2 cross-date validity masks",
            }
            self.register(
                "all-sensor-overlap", "unified", "cross_date", "all-sensor-overlap",
                "4-sensor joint valid overlap mask", "OTHER", "flag",
                "Cells where NISAR, LiDAR, Sentinel-1 & Sentinel-2 all have valid change (168 / 1,450 cells)",
                overlap_prov, VALID, None, "June vs. October 2026 (168 joint cells)",
                path_override=cross_tif, band=32, group_override="measured",
                qa={"valid_study_cells": 168, "study_cells": study_cells},
            )

    def create_boundary_layers(self, comparison):
        radar_records = comparison.get("source", {}).get("nisar", {})
        for epoch, label in EPOCHS.items():
            nisar_id = f"nisar-boundary-{epoch}"
            if nisar_id in self.reconstruction.boundary_geojson:
                item = radar_records.get(epoch, {})
                when = item.get("acquisition_start_utc")
                self.layers[nisar_id] = (None, {
                    "id": nisar_id,
                    "slot": "nisar-boundary",
                    "title": f"NISAR radar transition · {label}",
                    "sensor": "NISAR",
                    "group": "sensor",
                    "kind": "geojson",
                    "url": f"/api/boundaries/{nisar_id}.geojson",
                    "bounds": self.bounds,
                    "units": "m",
                    "quantity": "L-band HH/HV max-gradient backscatter transition (FRF x)",
                    "acquired_at": when,
                    "reference_date": when[:10] if when else None,
                    "epoch_label": label,
                    "native_crs": "EPSG:32618",
                    "native_resolution_m": 10,
                    "vertical_datum": None,
                    "inferred": False,
                    "status": "available",
                    "provenance": {
                        "source": RADAR,
                        "product_id": item.get("granule"),
                        "processing": "11 m running-mean cross-shore max-gradient edge (x = 20..150 m)",
                        "url": item.get("cmr_url"),
                    },
                })
            s2_id = f"s2-boundary-{epoch}"
            if s2_id in self.reconstruction.boundary_geojson:
                feats = self.reconstruction.boundary_geojson[s2_id]["features"]
                props = feats[0]["properties"] if feats else {}
                when = props.get("acquired_at")
                self.layers[s2_id] = (None, {
                    "id": s2_id,
                    "slot": "s2-boundary",
                    "title": f"Sentinel-2 NDWI waterline · {label}",
                    "sensor": "SENTINEL-2",
                    "group": "sensor",
                    "kind": "geojson",
                    "url": f"/api/boundaries/{s2_id}.geojson",
                    "bounds": self.bounds,
                    "units": "m",
                    "quantity": "Instantaneous optical waterline (NDWI = 0.0 crossing)",
                    "acquired_at": when,
                    "reference_date": when[:10] if when else None,
                    "epoch_label": label,
                    "native_crs": "EPSG:32618",
                    "native_resolution_m": 10,
                    "vertical_datum": None,
                    "inferred": False,
                    "status": "available",
                    "provenance": {
                        "source": S2_SOURCE,
                        "product_id": props.get("granule_id"),
                        "processing": "Cross-shore NDWI = 0.0 crossing along 10 m FRF rows",
                    },
                })

    def create_physics_layers(self):
        if self.coastal.lidar["status"] != "supported":
            for id in ("lidar-dz-2026-oct-jun", "lidar-paired-coverage"):
                self.layers.pop(id, None)
                self.layer_bands.pop(id, None)
        else:
            for id in ("lidar-dz-2026-oct-jun", "lidar-paired-coverage"):
                if id in self.layers:
                    desc = self.layers[id][1]
                    desc["provenance"] = {**desc["provenance"], "processing": self.coastal.lidar["method"],
                                          "processing_version": self.coastal.lidar["processing_version"]}
                    desc.setdefault("qa", {})["acquisitions"] = self.coastal.lidar["acquisitions"]

        for id, layer in self.coastal.layers.items():
            radar = id == "radar-disagreement"
            props = layer["features"][0]["properties"]
            kind = props.get("kind")
            when = props.get("acquired_at")
            title, slot, quantity = {
                "ndwi": ("Raw Sentinel-2 waterline (NDWI)", "physics-s2-ndwi", "Cloud-masked NDWI waterline at acquisition"),
                "mndwi": ("Raw Sentinel-2 waterline (MNDWI)", "physics-s2-mndwi", "Cloud-masked MNDWI waterline at acquisition"),
                "tide": ("Tide-corrected waterline", "physics-s2-tide", "Optical waterline normalized to Duck mean high water"),
                "setup": ("Wave setup sensitivity", "physics-s2-setup", "Experimental normalization including mean wave setup"),
                None: ("Radar directional disagreement", "radar-disagreement", "Opposite signs of NISAR HH and Sentinel-1 VV changes"),
            }[kind]
            qa = {**self.coastal.radar, "reliability": "conditional"} if radar else {
                "acquisition_id": props["acquisition_id"], "target": props["target"],
                "reliability": "conditional",
            }
            self.layers[id] = (None, {
                "id": id, "slot": slot, "title": title, "sensor": "OTHER" if radar else "SENTINEL-2",
                "group": "sensor", "kind": "geojson", "url": f"/api/boundaries/{id}.geojson",
                "bounds": self.bounds, "units": "flag" if radar else "m", "quantity": quantity,
                "acquired_at": when, "reference_date": when[:10] if when else None,
                "epoch_label": when[:10] if when else "June to October 2026",
                "native_crs": "EPSG:32618", "native_resolution_m": 20 if kind == "mndwi" else 10,
                "vertical_datum": "NAVD88" if kind in ("tide", "setup") else None,
                "inferred": kind in ("tide", "setup"), "status": "available", "qa": qa,
                "provenance": {"source": "NASA NISAR and ESA Sentinel-1" if radar else S2_SOURCE,
                               "processing": quantity, "processing_version": VERSION,
                               "product_id": props.get("acquisition_id")},
            })

    def create_transects(self):
        # Exact FRF transform used by the pipeline. The line starts at the first
        # paired observation and spans the profile; samples retain the source gaps.
        angle = radians(69.9747)
        profiles = read_json(self.root / "lidar/profiles.json").get("profiles", [])
        for source in profiles:
            id, y = source["id"], source["y_frf_m"]
            x = [source["june"][i]["x"] for i in (0, -1)]
            e = [901951.6805 + value * sin(angle) - y * cos(angle) for value in x]
            n = [274093.1562 + value * cos(angle) + y * sin(angle) for value in x]
            lon, lat = transform("EPSG:6542", "EPSG:4326", e, n)
            feature = {
                "type": "Feature", "geometry": {"type": "LineString", "coordinates": list(zip(lon, lat))},
                "properties": {"id": id, "label": source["label"], "frf_y_m": y,
                               "x_origin_frf_m": float(x[0]),
                               "x_reference": f"FRF x = {x[0]:g} m at the line start"},
            }
            points = [{
                "epoch_label": label, "acquired_at": source[epoch + "_utc"], "source": source["source"],
                "vertical_datum": source["verticalDatum"], "units": "m",
                "points": [{"x_m": p["x"] - x[0], "z_m": p["z"]} for p in source[epoch]],
            } for epoch, label in EPOCHS.items()]
            boundaries = self.reconstruction.transect_boundaries(
                y_frf_m=y,
                x_origin_frf_m=float(x[0]),
                lidar_epoch_utc={"june": source.get("june_utc"), "october": source.get("october_utc")},
            )
            analysis = self.reconstruction.transect_analysis(
                transect_id=id,
                y_frf_m=y,
                x_origin_frf_m=float(x[0]),
            )
            if self.coastal.lidar["status"] == "supported":
                june = {p["x_m"]: p["z_m"] for p in points[0]["points"]}
                measured = [
                    {"x_m": p["x_m"], "dz_m": round(p["z_m"] - june[p["x_m"]], 6)}
                    for p in points[1]["points"] if p["x_m"] in june
                ]
            else:
                measured = []
            analysis["coastal_observations"] = {
                "processing_version": VERSION,
                "waterlines": self.coastal.transect(y, float(x[0])),
                "terrain": {**self.coastal.lidar, "change_profile": measured},
            }
            self.transects[id] = (feature, points, boundaries, analysis)

    def study(self):
        w, s, e, n = self.bounds
        return {"type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [[(w,s),(e,s),(e,n),(w,n),(w,s)]]},
                "properties": {"name": "Duck FRF study area", "analysis_crs": "EPSG:32618",
                               "frf_y_range_m": self.range, "transect_ids": list(self.transects)}}

    def terrain(self):
        dz = self.layers.get("lidar-dz-2026-oct-jun")
        if not dz or len(self.epochs) != 2:
            return {"status": "unavailable", "reason": "Verified paired LiDAR elevations are unavailable"}
        stats = self.lidar["native"]["delta_z"]
        overlap = self.geospatial_qa.get("change_valid_overlap_counts", {})
        return {
            "layer": dz[1],
            "epochs": self.epochs,
            "dems": [d for _, d in self.layers.values() if d["kind"] == "raster_dem"],
            "vertical_datum": VERTICAL,
            "units": "m",
            "stats": {f"{k}_m": stats[k] for k in ("mean", "min", "max")},
            "cross_date_overlap": {
                "study_cells_10m": self.geospatial_qa.get("study_cells", 1450),
                "native_1m_paired_cells": stats.get("valid_pixels", 17466),
                "aligned_10m_lidar_change_cells": overlap.get("lidar_change_m_valid", 168),
                "all_sensor_valid_overlap_cells": overlap.get("all_sensor_valid_overlap", 168),
            },
        }

    def comparisons(self):
        if not self.cross_date_pairs:
            return {"status": "unavailable", "reason": "Unified cross-date comparison bundle is unavailable"}
        return {
            "study_cells": self.geospatial_qa.get("study_cells", 1450),
            "reference_grid": self.geospatial_qa.get("reference_grid"),
            "pairs": self.cross_date_pairs,
            "change_valid_overlap_counts": self.geospatial_qa.get("change_valid_overlap_counts", {}),
            "environment_contrasts": self.cross_date_environment,
        }
