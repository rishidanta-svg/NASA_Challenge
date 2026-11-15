"""Read committed boundary products without inventing elevations or acquisition times."""
import json
import csv
import math
from pathlib import Path
from datetime import datetime, timezone


def rows(path):
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


class Science:
    def __init__(self, root: Path):
        self.root = root
        self.states = rows(root / "outputs/reconstructed_state.csv")
        self.observations = rows(root / "outputs/sensor_boundaries.csv")
        self.metrics = rows(root / "outputs/reconstruction_metrics.csv")
        self.lidar = {r["date_key"]: r["scan_utc"] for r in rows(root / "data/processed/lidar_scan_meta.csv")}

    def acquisitions(self):
        result = []
        for filename, sensor, key, time in [
            ("s1_meta.csv", "SENTINEL-1", "item_id", "acquisition_utc"),
            ("s2_meta.csv", "SENTINEL-2", "item_id", "acquisition_utc"),
            ("nisar_meta.csv", "NISAR", "granule", "begin_utc"),
        ]:
            for row in rows(self.root / "data/processed" / filename):
                identity = row.get(key) or row.get("granule_ur") or row.get("concept_id")
                stamp = row.get(time)
                if identity and stamp:
                    result.append({"id": identity, "sensor": sensor, "product": filename.removesuffix("_meta.csv"),
                                   "acquired_at": stamp, "qa": {"analysis_epoch": row["date_key"],
                                   "source": "main validation pipeline; not necessarily a map raster"}})
        return result

    def analysis(self, feature):
        y = feature["properties"].get("frf_y_m")
        selected = [r for r in self.states if number(r.get("y")) == y]
        if not selected:
            return {"status": "unavailable", "reason": "No committed boundary estimates at this exact FRF row"}
        records = []
        for row in selected:
            observations = []
            lidar_time = self.lidar.get(row["date"])
            for obs in self.observations:
                if obs["date"] != row["date"] or number(obs.get("y")) != y:
                    continue
                stamp = obs.get("acquisition_utc")
                delta = None
                if stamp and lidar_time:
                    delta = (datetime.fromisoformat(stamp.replace("Z", "+00:00")) -
                             datetime.fromisoformat(lidar_time.replace("Z", "+00:00")).replace(tzinfo=timezone.utc)).total_seconds() / 3600
                observations.append({"sensor": obs["sensor"], "product": obs["product"],
                    "acquisition_id": obs["granule_id"], "acquired_at": stamp or None,
                    "x_frf_m": number(obs.get("boundary_x")), "lidar_offset_hours": delta})
            for name in ("waterline", "dunetoe"):
                estimate = number(row.get(name + "_x_m"))
                interval = [number(row.get("dunetoe_bayes_ci90_low_m")), number(row.get("dunetoe_bayes_ci90_high_m"))]
                records.append({"epoch": row["date"], "feature": name, "x_frf_m": estimate,
                    "status": row.get(name + "_status", "unavailable"), "source": row.get(name + "_source", ""),
                    "cv_rmse_m": number(row.get("waterline_cv_rmse_m" if name == "waterline" else "dunetoe_cv_rmse_conservative_m")),
                    "interval90_frf_m": interval if name == "dunetoe" and estimate is not None and all(v is not None for v in interval) else None})
            records[-1]["observations"] = observations
        return {"transect_id": feature["properties"]["id"], "quantity": "cross-shore boundary position",
                "coordinate_reference": "FRF cross-shore x (absolute), metres; not distance from transect start",
                "inferred": True, "records": records,
                "quality_checks": rows(self.root / "outputs/self_checks.csv"),
                "validation": [{"method": r["method"], "N": int(r["N"]), "RMSE_m": number(r["RMSE_m"])} for r in self.metrics],
                "limitations": ["Boundary estimates are not elevation or bathymetry.",
                    "CV RMSE is a validation error scale, not vertical sigma or an independently calibrated confidence interval.",
                    "The approximate Bayesian interval depends on LiDAR-based error scales; ambiguous point estimates are withheld.",
                    "Committed matched-row RMSE does not demonstrate an improvement over the baseline."]}
