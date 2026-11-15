"""Preserve source flags and match environmental records independently to every acquisition."""
import argparse
import json
from pathlib import Path

import netCDF4 as nc
import numpy as np
import pandas as pd

from build_geospatial import write_json

DEG = "degree_true_from"
COOPS = "NOAA CO-OPS 8651370"
WAVE17 = "USACE FRF Waverider 17m"
WAVE26 = "USACE FRF Waverider 26m"
RAIN = "USACE FRF rain gauge"
RUNUP = "USACE FRF lidar wave runup"
HYDRO = "USACE FRF lidar hydrodynamics"
CADENCE = {COOPS: 6, WAVE17: 30, WAVE26: 30, RAIN: 10, RUNUP: 60, HYDRO: 60,
           "NDBC 44056": 30, "NDBC DUKN7": 6}
TOLERANCE = {COOPS: 12, WAVE17: 35, WAVE26: 35, RAIN: 15, RUNUP: 30, HYDRO: 30,
             "NDBC 44056": 35, "NDBC DUKN7": 12}


def numeric(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return np.nan


def plain(value):
    if np.ma.is_masked(value):
        return None
    return value.item() if isinstance(value, np.generic) else value


def row(t, station, variable, value, unit, usable, qc, source, latitude, longitude, datum=None, priority=0):
    return (t, station, variable, value, unit, np.isfinite(value) and usable,
            json.dumps(qc, separators=(",", ":"), allow_nan=False), source,
            latitude, longitude, datum, priority)


def coops_rows(folder):
    for p in sorted(folder.glob("coops_*.json")):
        name = p.stem.removeprefix("coops_").rsplit("_", 1)[0]
        if name not in {"water_level", "predictions", "wind"}:
            continue
        d = json.loads(p.read_text())
        if "error" in d:
            raise ValueError(f"CO-OPS product unavailable: {p.name}: {d['error']}")
        meta = d.get("metadata") or json.loads((folder / "coops_station_8651370.json").read_text())["stations"][0]
        lat, lon = float(meta["lat"]), float(meta["lon"] if "lon" in meta else meta["lng"])
        if name == "water_level":
            fields = {"v": ("water_level", "m", "MLLW"), "s": ("water_level_1s_sample_sigma", "m", "MLLW")}
        elif name == "predictions":
            fields = {"v": ("tide_prediction", "m", "MLLW")}
        else:
            fields = {"s": ("wind_speed", "m s-1", None), "g": ("wind_gust", "m s-1", None),
                      "d": ("wind_direction", DEG, None)}
        for x in d.get("data", d.get("predictions", [])):
            qc = {k: x[k] for k in ("f", "q", "dr") if k in x}
            valid = "f" not in x or all(flag == "0" for flag in x["f"].split(","))
            if name == "water_level":
                valid &= x.get("q") in {"p", "v"}
            if name == "predictions":
                qc["product"] = "astronomical prediction"
            t = pd.Timestamp(x["t"], tz="UTC")
            for fld, (var, unit, datum) in fields.items():
                v = numeric(x.get(fld))
                eligible = valid and (unit != DEG or (0 <= v <= 360 and numeric(x.get("s")) > 0))
                yield row(t, COOPS, var, v, unit, eligible, qc, p.name, lat, lon, datum)


def scalar(d, key, backup):
    return float(np.asarray(d.variables[key][()])) if key in d.variables else numeric(getattr(d, backup, None))


def frf_rows(folder):
    for p in sorted(folder.glob("frf_*.nc")):
        group = p.stem.split("_")[1]
        with nc.Dataset(p) as d:
            tvar = d.variables["time"]
            if not tvar.units.startswith("seconds since 1970-01-01"):
                raise ValueError(f"Unexpected time units for {p.name}: {tvar.units}")
            times = pd.to_datetime(np.asarray(tvar[:]), unit="s", utc=True)
            source_lat = scalar(d, "latitude", "geospatial_lat_min")
            source_lon = scalar(d, "longitude", "geospatial_lon_min")
            if group in {"runup", "hydro"}:
                source_lat = scalar(d, "lidarLatitude", "geospatial_lat_min")
                source_lon = scalar(d, "lidarLongitude", "geospatial_lon_min")
            if group == "rain":
                specs = [("rain", "rain_10min", "mm", "qcFlag", {1}, None)]
                qc_keys = ("qcFlag", "sensorID")
                station = RAIN
            elif group in {"wave17", "wave26"}:
                station = WAVE17 if group == "wave17" else WAVE26
                qc_keys = tuple(key for key in ("qcFlagE", "qcFlagD", "PorAST") if key in d.variables)
                specs = [(src, name, unit, qc, {1}, None) for src, name, unit, qc in [
                    ("waveHs", "wave_significant_height", "m", "qcFlagE"),
                    ("waveTp", "wave_peak_period", "s", "qcFlagE"),
                    ("waveTm", "wave_average_period", "s", "qcFlagE"),
                    ("waveMeanDirection", "wave_mean_direction", DEG, "qcFlagD"),
                    ("wavePeakDirectionPeakFrequency", "wave_peak_direction", DEG, "qcFlagD"),
                ]]
            elif group == "runup":
                station = RUNUP
                specs = [("totalWaterLevel", "total_water_level_2pct", "m", "totalWaterLevelQCFlag", {1, 2},
                          "NAVD88 (geoid12b)"),
                         ("percentTimeSeriesMissing", "runup_timeseries_missing_percent", "%", None, set(), None)]
                qc_keys = ("totalWaterLevelQCFlag",)
            else:
                if getattr(d, "source_hydro_xfrf_stride", None) != 10:
                    raise ValueError(f"Unverified hydro transport: {p.name}")
                station = HYDRO
                qc_keys = ("hydrodynamicsFlag",)
                specs = [(src, name, units, "hydrodynamicsFlag", {1}, datum) for src, name, units, datum in [
                    ("waterLevel", "transect_water_level", "m", "NAVD88 (geoid12b)"),
                    ("waveHs", "transect_seaswell_hs", "m", None),
                    ("waveHsIG", "transect_infragravity_hs", "m", None),
                    ("waveTp", "transect_wave_peak_period", "s", None),
                ]]
            qc_data = {k: d.variables[k][:] for k in qc_keys}
            native = {spec[0]: d.variables[spec[0]][:] for spec in specs}
            if group == "hydro":
                x = np.asarray(d.variables["xFRF"][:])
                y = np.asarray(d.variables["yFRF"][:])
                positions = [(int(np.argmin(abs(x - v))), v) for v in (80, 120, 190)]
            else:
                positions = [(None, None)]
            for i, t in enumerate(times):
                qc = {k: plain(values[i]) for k, values in qc_data.items()}
                if group in {"runup", "hydro"}:
                    qc["lidar_xFRF_m"] = scalar(d, "lidarX", "")
                    qc["lidar_yFRF_m"] = scalar(d, "lidarY", "")
                for idx, nominal_x in positions:
                    flags = qc if idx is None else {**qc, "xFRF_m": float(x[idx]), "yFRF_m": float(y[idx])}
                    for src, name, unit, qc_field, accepted, datum in specs:
                        value = plain(native[src][i] if idx is None else native[src][i, idx])
                        ok = qc_field is None or qc[qc_field] in accepted
                        if idx is not None:
                            name = f"{name}_x{nominal_x}"
                        if unit == DEG:
                            ok &= value is not None and 0 <= value <= 360
                        yield row(t, station, name, numeric(value), unit, ok, flags, p.name, source_lat, source_lon, datum)


def buoy_rows(folder):
    fields = [
        ("wave_height", "WVHT", "wave_significant_height", "m", 30),
        ("dominant_wpd", "DPD", "wave_peak_period", "s", 60),
        ("average_wpd", "APD", "wave_average_period", "s", 60),
        ("mean_wave_dir", "MWD", "wave_mean_direction", DEG, 360),
        ("wind_spd", "WSPD", "wind_speed", "m s-1", 100),
        ("wind_dir", "WDIR", "wind_direction", DEG, 360),
        ("gust", "GST", "wind_gust", "m s-1", 150),
    ]
    for st in ("44056", "DUKN7"):
        station = "NDBC " + st
        nc_file = folder / f"ndbc_{st}_2026.nc"
        rt_file = folder / f"ndbc_{st}_realtime.txt"
        with nc.Dataset(nc_file) as d:
            time = pd.to_datetime(np.asarray(d.variables["time"][:]), unit="s", utc=True)
            lat, lon = (float(d.variables[k][0]) for k in ("latitude", "longitude"))
            time_mask = (time >= pd.Timestamp("2026-06-01", tz="UTC")) & (time < pd.Timestamp("2026-11-01", tz="UTC"))
            for name, _, var, unit, upper in fields:
                if st == "44056" and var.startswith("wind") or st == "DUKN7" and var.startswith("wave"):
                    continue
                values = d.variables[name][:, 0, 0][time_mask]
                for t, value in zip(time[time_mask], values):
                    v = numeric(plain(value))
                    yield row(t, station, var, v, unit, 0 <= v <= upper, {"stream": "archive"}, nc_file.name, lat, lon)
        if rt_file.exists():
            lines = rt_file.read_text().splitlines()
            headers = lines[0].removeprefix("#").split()
            for line in lines:
                if line.startswith("#") or not line.strip():
                    continue
                data = dict(zip(headers, line.split()))
                vals = line.split()[:5]
                t = pd.Timestamp(year=int(vals[0]), month=int(vals[1]), day=int(vals[2]),
                                 hour=int(vals[3]), minute=int(vals[4]), tz="UTC")
                if t.month not in (6, 9, 10):
                    continue
                for _, name, var, unit, upper in fields:
                    if st == "44056" and var.startswith("wind") or st == "DUKN7" and var.startswith("wave"):
                        continue
                    v = numeric(data.get(name))
                    yield row(t, station, var, v, unit, 0 <= v <= upper,
                              {"stream": "realtime_preliminary"}, rt_file.name, lat, lon, priority=1)


def table(discovery, frf):
    columns = ["timestamp_utc", "station_id", "variable", "value", "unit", "feature_eligible",
               "source_quality_json", "source_artifact", "station_latitude", "station_longitude",
               "vertical_datum", "source_priority"]
    # Preserve raw rows from both NDBC streams, including overlapping dates.
    records = [*coops_rows(discovery), *frf_rows(frf), *buoy_rows(discovery)]
    return pd.DataFrame.from_records(records, columns=columns).sort_values(
        ["station_id", "variable", "timestamp_utc", "source_priority"]).reset_index(drop=True)


def nearest(t, available, tolerance):
    if available.empty:
        return None
    lo = available["timestamp_utc"].searchsorted(t - tolerance)
    hi = available["timestamp_utc"].searchsorted(t + tolerance, side="right")
    options = available.iloc[lo:hi]
    if options.empty:
        return None
    # Chronological order breaks exact ties in favor of the earlier reading.
    index = (options["timestamp_utc"] - t).abs().idxmin()
    return options.loc[index]


def tide_features(t, available):
    prediction = available[(COOPS, "tide_prediction")].set_index("timestamp_utc")["value"]
    measurements = available[(COOPS, "water_level")].set_index("timestamp_utc")
    bracket = prediction.reindex([t.floor("6min"), t.floor("6min") + pd.Timedelta(minutes=6)])
    correction = None
    nearby = nearest(t, measurements.reset_index(), pd.Timedelta(minutes=12))
    if nearby is not None:
        when = nearby["timestamp_utc"]
        if when in prediction:
            correction = float(nearby["value"] - prediction.loc[when])
    slope = None
    stage = None
    if bracket.notna().all():
        slope = float((bracket.iloc[-1] - bracket.iloc[0]) * 10)
        stage = "rising" if slope > 0.01 else "falling" if slope < -0.01 else "near_slack"
    return {"predicted_tide_slope_m_per_h": slope, "predicted_tide_stage": stage,
            "predicted_tide_bracket_left_utc": bracket.index[0], "predicted_tide_bracket_right_utc": bracket.index[-1],
            "observed_minus_predicted_m_at_obs_time": correction,
            "water_level_residual_timestamp_utc": nearby["timestamp_utc"] if correction is not None else None,
            "vertical_datum": "MLLW"}


def match(env, observations):
    accepted = env[env["feature_eligible"]].drop_duplicates(["station_id", "variable", "timestamp_utc"])
    available = dict(tuple(accepted.groupby(["station_id", "variable"], sort=False)))
    matches, windows, tides = [], [], []
    for obs in observations:
        t = pd.Timestamp(obs["timestamp_utc"])
        context = {"id": obs["id"], "acquisition_utc": t, "group": obs["group"]}
        tides.append({**context, **tide_features(t, available)})
        for (station, variable), observed in env.groupby(["station_id", "variable"], sort=False):
            ready = available.get((station, variable), env.iloc[:0])
            example = observed.iloc[0]
            base = {**context, "station_id": station, "variable": variable, "unit": example["unit"],
                    "vertical_datum": example["vertical_datum"]}
            tolerance = TOLERANCE[station]
            hit = nearest(t, ready, pd.Timedelta(minutes=tolerance))
            fields = {key: hit[key] if hit is not None else None
                      for key in ("timestamp_utc", "value", "source_quality_json", "source_artifact",
                                  "station_latitude", "station_longitude")}
            matches.append({**base, **fields, "tolerance_minutes": tolerance,
                            "offset_seconds": (hit["timestamp_utc"] - t).total_seconds() if hit is not None else None})
            # The rain source does not identify which interval boundary its timestamp labels.
            # Use only complete intervals regardless of whether the label is at the start or end.
            rain = variable == "rain_10min"
            guard = pd.Timedelta(minutes=10) if rain else pd.Timedelta(0)
            stop = t - guard
            timestamps = ready["timestamp_utc"].dt.round("s") if rain else ready["timestamp_utc"]
            for hours in ((1, 6, 24, 72, 168) if rain else (1, 6, 24, 72)):
                begin = t - pd.Timedelta(hours=hours) + guard
                i = timestamps.searchsorted(begin, side="left" if rain else "right")
                j = timestamps.searchsorted(stop, side="right")
                selected = ready.iloc[i:j]
                values = selected["value"].to_numpy()
                if rain:
                    expected_labels = pd.date_range(begin.ceil("10min"), stop.floor("10min"), freq="10min")
                    expected = len(expected_labels)
                    complete = expected > 0 and np.array_equal(timestamps.iloc[i:j].array, expected_labels.array)
                else:
                    expected = int(hours * 60 / CADENCE[station])
                    complete = len(values) >= np.ceil(0.75 * expected) and len(values) > 0
                result = {**base, "window_hours": hours, "window_start_utc": begin, "window_start_inclusive": rain,
                          "window_end_utc_inclusive": stop, "expected_count": expected, "accepted_count": len(values),
                          "coverage_fraction": min(1., len(values) / expected) if expected else None, "coverage_threshold_met": bool(complete),
                          "mean": None, "min": None, "max": None, "rain_sum_mm": None,
                          "circular_mean_deg": None, "circular_resultant_length": None,
                          "first_observation_utc": selected["timestamp_utc"].iloc[0] if len(values) else None,
                          "last_observation_utc": selected["timestamp_utc"].iloc[-1] if len(values) else None}
                if complete and rain:
                    result["rain_sum_mm"] = float(values.sum())
                elif complete and example["unit"] == DEG:
                    vector = np.exp(1j * np.deg2rad(values)).mean()
                    result["circular_resultant_length"] = float(abs(vector))
                    if abs(vector) >= 0.05:
                        result["circular_mean_deg"] = float(np.angle(vector, deg=True) % 360)
                elif complete:
                    result.update(mean=float(values.mean()), min=float(values.min()), max=float(values.max()))
                windows.append(result)
    return (pd.DataFrame(matches), pd.DataFrame(windows), pd.DataFrame(tides))


def paired_environment(nearest_table, definitions):
    join_keys = ["station_id", "variable", "unit", "vertical_datum"]
    fields = join_keys + ["timestamp_utc", "value", "offset_seconds", "source_quality_json", "source_artifact"]
    rows = []
    for sensor, pair in definitions.items():
        if pair["status"] != "paired":
            continue
        left = nearest_table.loc[nearest_table["id"] == pair["june_id"], fields]
        right = nearest_table.loc[nearest_table["id"] == pair["october_id"], fields]
        joined = left.merge(right, on=join_keys, suffixes=("_june", "_october"), validate="one_to_one")
        joined["pair_sensor"] = sensor
        joined["june_id"] = pair["june_id"]
        joined["october_id"] = pair["october_id"]
        joined["change_valid"] = joined[["value_june", "value_october"]].notna().all(axis=1)
        joined["october_minus_june"] = joined["value_october"] - joined["value_june"]
        directional = joined["unit"] == DEG
        joined.loc[directional, "october_minus_june"] = (
            (joined.loc[directional, "october_minus_june"] + 180) % 360 - 180
        )
        rows.append(joined)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--discovery", type=Path, default=Path("data/raw/discovery"))
    p.add_argument("--frf", type=Path, default=Path("data/raw/environment_native"))
    p.add_argument("--output", type=Path, default=Path("data/unified"))
    a = p.parse_args()
    manifest_path = a.output / "acquisition_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    out = a.output / "environment"
    out.mkdir(exist_ok=True)
    data = table(a.discovery, a.frf)
    nearest_table, summaries, tide = match(data, manifest["observations"])
    pair_definitions = json.loads((a.output / "cross_date_pairs.json").read_text())
    paired = paired_environment(nearest_table, pair_definitions)
    for name, frame in {"observations": data, "nearest": nearest_table, "antecedent": summaries,
                        "tide_stage": tide, "cross_date": paired}.items():
        frame.to_parquet(out / f"{name}.parquet", index=False)
    for name, frame in {"nearest": nearest_table, "antecedent": summaries, "tide_stage": tide}.items():
        frame.to_csv(out / f"{name}.csv", index=False)
    stats = nearest_table.assign(matched=nearest_table["value"].notna()).groupby(
        ["station_id", "variable"]).matched.agg(["size", "sum"]).reset_index()
    report = {
        "environmental_record_count": len(data),
        "sample_match_counts": stats.rename(columns={"size": "acquisitions", "sum": "matched"}).to_dict("records"),
        "cadence_minutes": CADENCE, "maximum_nearest_offset_minutes": TOLERANCE,
        "frf_requests": json.loads((a.frf / "requests.json").read_text()),
        "original_discovery_requests": json.loads((a.discovery / "requests.json").read_text()),
    }
    write_json(out / "environment_qa.json", report)


if __name__ == "__main__":
    main()
