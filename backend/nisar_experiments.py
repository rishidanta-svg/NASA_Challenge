"""FastAPI data products for the isolated NISAR experiments."""

import json
import logging

import numpy as np
import rasterio

from .nisar_ablation import TARGET, ablate, feature_maps
from .nisar_shoreline import VERSION, POSTING_M, frf_centers, load_nisar_scene, shoreline_experiment

EPOCHS = ("june", "october")
LOG = logging.getLogger(__name__)
ERRORS = (OSError, KeyError, ValueError, TypeError, np.linalg.LinAlgError, rasterio.errors.RasterioError)


def unavailable(reason):
    return {"status": "withheld", "reason": reason, "n": 0, "units": "m"}


class NisarExperiments:
    def __init__(self, catalog):
        self.scenes = {}
        self.layers = {}
        self.descriptors = {}
        self.input_qa = {"status": "withheld", "reason": "Verified NISAR pair unavailable"}
        self.terrain = {**unavailable("Verified NISAR or paired LiDAR inputs unavailable"),
                        "scientific_target": TARGET}
        self.shoreline = unavailable("Verified NISAR pair unavailable")
        observations = {o["id"]: o for o in catalog.unified_manifest.get("observations", [])}
        pairs = catalog.cross_date_pairs
        if not pairs.get("NISAR"):
            return

        grid, by_epoch, qa, shared = self._load_pairs(catalog, observations, pairs["NISAR"])
        if grid is None:
            return
        try:
            path = catalog.root / "physics/duck_foreshore_slopes.json"
            slopes = json.loads(path.read_text()) if path.is_file() else {}
        except (OSError, ValueError):
            LOG.warning("NISAR experiment could not read the independent slope artifact", exc_info=True)
            slopes = {}
        cross_shore, _ = frf_centers(grid)
        for epoch in EPOCHS:
            try:
                scene, layer = shoreline_experiment(epoch, by_epoch[epoch], shared, grid, cross_shore, qa[epoch],
                                                    catalog.coastal, slopes, catalog.acq_environment)
                self.scenes[epoch] = scene
                if layer["features"]:
                    self._register(epoch, scene, layer, catalog.bounds)
            except ERRORS as exc:
                LOG.warning("NISAR HH segmentation failed for %s: %s", epoch, exc)
                self.scenes[epoch] = {**qa[epoch], **unavailable("HH segmentation inputs failed the quality checks")}

        self.shoreline = {
            "status": "exploratory" if self.layers else "withheld",
            "scientific_target": "Connected HH brightness transition; independently screen for instantaneous waterline",
            "method": "HH RTC gamma-zero, one masked 3×3 median pass, per-scene Otsu, offshore-connected dark components, FRF transects",
            "units": "m", "frf_x_positive": "seaward", "posting_m": POSTING_M,
            "validation_protocol": "Freeze HH extraction before optical/tide comparability or LiDAR scoring",
        }
        if catalog.coastal.lidar["status"] != "supported":
            return
        try:
            count = catalog.geospatial_qa["change_valid_overlap_counts"]["all_sensor_valid_overlap"]
            self.terrain = ablate(catalog.unified_root / "cross_date.tif", grid, feature_maps(by_epoch), count)
            self.terrain["acquisition_pairs"] = {sensor: pairs[sensor] for sensor in (
                "NISAR", "Sentinel-1", "Sentinel-2", "USACE LiDAR")}
            self.terrain["timing"] = catalog.coastal.radar.get("s1_minus_nisar_seconds")
        except ERRORS as exc:
            LOG.warning("NISAR ablation inputs unavailable: %s", exc)
            self.terrain["reason"] = "The alignment, data completeness or nested spatial-validation check failed"

    def _load_pairs(self, catalog, observations, pair):
        try:
            rasters = {epoch: load_nisar_scene(catalog.unified_root, observations[pair[f"{epoch}_id"]],
                                               pair[f"{epoch}_utc"]) for epoch in EPOCHS}
            grid = rasters["june"][0]
            by_epoch = {epoch: raster[1] for epoch, raster in rasters.items()}
            qa = {epoch: raster[2] for epoch, raster in rasters.items()}
            repeat_keys = ("track", "frame", "orbit_direction", "look_direction", "crid", "producer_version")
            if (grid != rasters["october"][0] or any(qa["june"][k] != qa["october"][k] for k in repeat_keys)
                    or (qa["june"]["track"], qa["june"]["frame"], qa["june"]["orbit_direction"]) != (69, 70, "Descending")):
                raise ValueError("NISAR acquisitions do not share the verified Duck repeat geometry, grid and processing release")
            shared = {}
            for pol in ("hh", "hv"):
                shared[pol] = np.isfinite(by_epoch["june"][pol]) & np.isfinite(by_epoch["october"][pol])
                if not shared[pol].any() or int(shared[pol].sum()) != pair["valid_counts"][f"nisar_{pol.upper() * 2}_db_change"]:
                    raise ValueError(f"Unexpected NISAR {pol.upper()} repeat-pass coverage")
            geometry = catalog.coastal.radar.get("acquisitions", {}).get("NISAR", {})
            for epoch in EPOCHS:
                qa[epoch]["incidence_grid_range_deg"] = geometry.get(epoch, {}).get("incidence_grid_range_deg")
        except ERRORS as exc:
            LOG.warning("NISAR pair failed input validation: %s", exc)
            self.input_qa["reason"] = "Verified NISAR calibration, source identity, quality or grid check failed"
            return None, None, None, None

        maps = feature_maps(by_epoch)
        shared_polarizations = shared["hh"] & shared["hv"]
        self.input_qa = {
            "status": "supported", "meaning": "Source, grid, calibration and local mask integrity checks",
            "source_acquisitions": qa,
            "shared_valid_cells": {k: int(mask.sum()) for k, mask in shared.items()},
            "shared_dual_polarization_cells": int(shared_polarizations.sum()),
            "unlabeled_features": {
                name: {"unit": "dB", "n": int(shared_polarizations.sum()),
                       "range": [float(values[shared_polarizations].min()), float(values[shared_polarizations].max())]}
                for name, values in maps.items()
            },
            "provisional_limitations": [
                "Retained HH/HV cells have valid subswath support, positive looks and no input-data exception flags.",
                ("Both scenes are flagged as joint L+S; the published joint 40 MHz banding caveat may apply."
                 if any(v["joint_l_s"] for v in qa.values()) else
                 "The documented joint L+S 40 MHz issue is inapplicable to these L-only acquisitions."),
                "The provisional diagnostic-mode track/frame exceptions do not match this pair.",
                "Local flags and grid checks cannot clear upstream incomplete L0B, subtle calibration/geolocation artifacts or quantify the noise floor.",
            ],
        }
        return grid, by_epoch, qa, shared["hh"]

    def _register(self, epoch, scene, layer, bounds):
        slot = "nisar-hh-land-water-candidate"
        identifier = f"{slot}-{epoch}"
        when = scene["acquired_at"]
        self.layers[identifier] = layer
        self.descriptors[identifier] = (None, {
            "id": identifier, "slot": slot, "sensor": "NISAR", "group": "sensor", "kind": "geojson",
            "title": "NISAR HH land/water candidate · " + when[:10],
            "url": f"/api/boundaries/{identifier}.geojson", "bounds": bounds, "units": "m",
            "quantity": "Exploratory connected HH brightness transition", "acquired_at": when,
            "reference_date": when[:10], "epoch_label": when[:10], "native_crs": "EPSG:32618",
            "native_resolution_m": POSTING_M, "vertical_datum": None, "inferred": True, "status": "available",
            "provenance": {"source": "NASA NISAR L-band GCOV", "product_id": scene["id"], "url": scene["source_url"],
                           "processing": VERSION, "processing_version": VERSION},
            "qa": {"product_status": scene["status"], "waterline_status": scene["comparability"]["status"],
                   "candidate_rows": scene["candidate_rows"], "rejected_rows": scene["rejected_rows"]},
        })

    def summary(self, include_samples=False):
        scenes = {}
        for epoch, result in self.scenes.items():
            scene = {k: v for k, v in result.items() if include_samples or k != "rows"}
            if "validation" in scene and not include_samples:
                scene["validation"] = {target: {k: v for k, v in entry.items() if k != "samples"}
                                       for target, entry in scene["validation"].items()}
            scenes[epoch] = scene
        return {
            "processing_version": VERSION,
            "input_qa": self.input_qa, "shoreline": {**self.shoreline, "epochs": scenes, "layer_ids": list(self.layers)},
            "terrain_ablation": {k: v for k, v in self.terrain.items() if include_samples or k != "samples"},
        }
