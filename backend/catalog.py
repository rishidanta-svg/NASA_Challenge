"""Adapt the verified pipeline bundles to the frontend data contract."""

import json
from pathlib import Path
from math import cos, radians, sin

from rasterio.warp import transform

BBOX = [-75.753384, 36.183704, -75.750335, 36.188260]
VERTICAL = "NAVD88 (geoid12b)"
EPOCHS = {"june": "June 2026", "october": "October 2026"}
LIDAR = "USACE FRF dune LiDAR DEM"
RADAR = "NASA NISAR L-band GCOV"
CHANGE = ("diverging", [(-2.5, "#b23b22"), (0, "#f1e9d7"), (2.5, "#096980")])
RADAR_CHANGE = ("diverging", [(-12, "#aa4b1a"), (0, "#f6ecdb"), (12, "#2747a0")])
POWER = ("sequential", [(-34, "#171433"), (-18, "#497584"), (1, "#fbf4c1")])
HEIGHT = ("sequential", [(0, "#18375c"), (3, "#43a098"), (8, "#f5df9c")])
FRACTION = ("sequential", [(0, "#34374c"), (1, "#77ddd0")])
VALID = ("categorical", [(0, "#b35235"), (1, "#5bd3a5")])


def read_json(path):
    return json.loads(path.read_text(encoding="utf8")) if path.is_file() else {}


class Catalog:
    def __init__(self, root: Path):
        self.root = root
        lidar = read_json(root / "lidar/manifest.json")
        comparison = read_json(root / "comparison/manifest.json")
        self.lidar = lidar
        self.bounds = lidar.get("study_wsen_epsg4326", comparison.get("study_wsen_epsg4326", BBOX))
        self.range = lidar.get("frf_y_range_m", comparison.get("frf_y_range_m", [700, 1190]))
        self.layers = {}
        self.acquisitions = []
        self.transects = {}
        self.epochs = []
        self.create_layers(lidar, comparison)
        self.create_transects()

    def register(self, id, bundle, filename, slot, title, sensor, units, quantity,
                 provenance, palette=None, when=None, epoch_label="October − June 2026", dem=False):
        terrain = sensor == "LIDAR"
        path = self.root / bundle / (filename + ".tif")
        if not path.is_file():
            return
        descriptor = {
            "id": id, "slot": slot, "title": title,
            "sensor": sensor, "group": "measured" if terrain else "sensor",
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
        if dem:
            descriptor["encoding"] = "terrarium"
        if palette:
            kind, stops = palette
            descriptor["colormap"] = {"type": kind, "min": stops[0][0], "max": stops[-1][0], "stops": stops}
        self.layers[id] = (path, descriptor)

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
                                  f"{pol.upper()} backscatter", provenance, POWER, t, label)
                self.register(f"nisar-quality-{epoch}", "comparison", f"nisar_{epoch}_HHHH_valid",
                              "nisar-quality", f"NISAR valid-data mask · {label}", "NISAR", "flag",
                              "GCOV usable HH pixels (1 valid; 0 excluded)", provenance, VALID, t, label)
        self.register("lidar-dz-2026-oct-jun", "lidar", "lidar_delta_z_utm_1m", "lidar-dz",
                      "LiDAR elevation change", "LIDAR", "m", "Measured elevation difference", ls, CHANGE)
        for pol in ("hh", "hv"):
            self.register(f"nisar-{pol}-change", "comparison", f"nisar_{pol.upper() * 2}_change_db",
                          f"nisar-{pol}-change", f"NISAR {pol.upper()} backscatter change", "NISAR", "dB",
                          "Radar scattering change", ns, RADAR_CHANGE)
        self.register("lidar-paired-coverage", "lidar", "lidar_dz_coverage", "lidar-coverage",
                      "Paired LiDAR coverage", "LIDAR", "fraction", "Valid paired area per 10 m cell",
                      ls, FRACTION)

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
                               "x_reference": f"FRF x = {x[0]:g} m at the line start"},
            }
            points = [{
                "epoch_label": label, "acquired_at": source[epoch + "_utc"], "source": source["source"],
                "vertical_datum": source["verticalDatum"], "units": "m",
                "points": [{"x_m": p["x"] - x[0], "z_m": p["z"]} for p in source[epoch]],
            } for epoch, label in EPOCHS.items()]
            self.transects[id] = (feature, points)

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
        return {"layer": dz[1], "epochs": self.epochs,
                "dems": [d for _, d in self.layers.values() if d["kind"] == "raster_dem"],
                "vertical_datum": VERTICAL, "units": "m",
                "stats": {f"{k}_m": stats[k] for k in ("mean", "min", "max")}}
