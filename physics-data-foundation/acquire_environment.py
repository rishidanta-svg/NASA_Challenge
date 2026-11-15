"""Retrieve source-native bulk FRF environmental measurements via OPeNDAP."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import datetime as dt
import json
import re
import struct
from pathlib import Path

import netCDF4 as nc
import numpy as np
import requests

from discover import FRF

PRODUCTS = {
    "rain": ("meteorology/metGauges/rain", "FRF-met_metGauges_rain",
             "time,sensorID,rain,qcFlag"),
    "wave17": ("oceanography/waves/waverider-17m", "FRF-ocean_waves_waverider-17m",
               "time,station_name,latitude,longitude,nominalDepth,gaugeDepth,waveHs,waveTp,waveTm,waveTm1,waveTm2,"
               "waveMeanDirection,wavePeakDirectionPeakFrequency,qcFlagE,qcFlagD,PorAST"),
    "wave26": ("oceanography/waves/waverider-26m", "FRF-ocean_waves_waverider-26m",
               "time,station_name,latitude,longitude,nominalDepth,gaugeDepth,waveHs,waveTp,waveTm,waveTm1,waveTm2,"
               "waveMeanDirection,wavePeakDirectionPeakFrequency,qcFlagE,qcFlagD,PorAST"),
    "runup": ("oceanography/waves/lidarWaveRunup", "FRF-ocean_waves_lidarWaveRunup",
              "time,station_name,lidarLatitude,lidarLongitude,lidarX,lidarY,totalWaterLevel,totalWaterLevelQCFlag,"
              "percentTimeSeriesMissing"),
    "hydro": ("oceanography/waves/lidarHydrodynamics", "FRF-ocean_waves_lidarHydrodynamics",
              "time,station_name,lidarLatitude,lidarLongitude,lidarX,lidarY,xFRF,yFRF,waterLevel,minWaterLevel,"
              "maxWaterLevel,waveHsIG,waveHs,waveTmIG,waveTp,waveHsTotal,waveSkewness,waveAsymmetry,"
              "hydrodynamicsFlag,percentTimeSeriesMissing"),
}


HYDRO_FIELDS = (
    "waterLevel", "minWaterLevel", "maxWaterLevel", "waveHsIG", "waveHs", "waveTmIG",
    "waveTp", "waveHsTotal", "waveSkewness", "waveAsymmetry", "percentTimeSeriesMissing",
)
HYDRO_STRIDE = 10


def hydro_bulk(origin, names, start, end, full_x):
    """Read and validate a bounded DAP2 XDR response of Float64 grid arrays."""
    constraint = ",".join(f"{key}.{key}[{start}:1:{end}][0:{HYDRO_STRIDE}:{full_x - 1}]" for key in names)
    ncolumns = (full_x - 1) // HYDRO_STRIDE + 1
    expected = (end - start + 1) * ncolumns
    endpoint = origin + ".dods?" + constraint
    for attempt in range(3):
        try:
            response = requests.get(endpoint, timeout=40)
            response.raise_for_status()
            header, sep, body = response.content.partition(b"Data:\n")
            ordered = re.findall(rb"Float64 (\w+)\[time = \d+\]\[xFRF = \d+\]", header)
            ordered = [name.decode("ascii") for name in ordered]
            if not sep or sorted(ordered) != sorted(names) or len(body) != len(names) * (8 + 8 * expected):
                raise ValueError("Incomplete or unexpected hydrodynamics DAP response")
            for index, field in enumerate(ordered):
                offset = index * (8 + 8 * expected)
                if struct.unpack_from(">II", body, offset) != (expected, expected):
                    raise ValueError("Hydrodynamics DAP array count mismatch")
                arr = np.frombuffer(body, dtype=">f8", count=expected, offset=offset + 8)
                finite = np.isfinite(arr)
                if np.any(np.abs(arr[finite]) > 5000):
                    raise ValueError("Hydrodynamics response contains impossible magnitudes")
                yield field, arr.reshape(end - start + 1, ncolumns)
            return
        except (requests.RequestException, ValueError):
            if attempt == 2:
                raise


def save(task):
    root, product, month = task
    directory, name, wanted = PRODUCTS[product]
    origin = f"{FRF}/dodsC/frf/{directory}/2026/{name}_2026{month}.nc"
    query = origin + "?" + (",".join(k for k in wanted.split(",") if k not in HYDRO_FIELDS)
                            if product == "hydro" else wanted)
    out = root / f"frf_{product}_2026{month}.nc"
    result = {"source_url": origin, "constraint": wanted, "filename": out.name}
    if out.is_file():
        with nc.Dataset(out) as local:
            result.update(retrieved_utc=local.retrieved_utc, samples=len(local.dimensions["time"]))
            current = product != "hydro" or getattr(local, "source_hydro_xfrf_stride", None) == HYDRO_STRIDE
        if current:
            return result
    partial = out.with_suffix(".part")
    for attempt in range(2):
        try:
            retrieved = dt.datetime.now(dt.timezone.utc).isoformat()
            with nc.Dataset(query) as remote, nc.Dataset(partial, "w") as local:
                local.setncatts({k: remote.getncattr(k) for k in remote.ncattrs()
                                  if k not in {"_NCProperties", "_IsNetcdf4", "_SuperblockVersion"}})
                local.setncatts({"source_url": origin, "source_dap_constraint": wanted, "retrieved_utc": retrieved})
                names = wanted.split(",")
                for dimension_name, dimension in remote.dimensions.items():
                    count = len(dimension)
                    if product == "hydro" and dimension_name == "xFRF":
                        count = (count - 1) // HYDRO_STRIDE + 1
                    local.createDimension(dimension_name, count)
                for var_name in names:
                    if product == "hydro" and var_name in HYDRO_FIELDS:
                        continue
                    src = remote.variables[var_name]
                    compression = src.dtype is not str and bool(src.dimensions)
                    var = local.createVariable(var_name, src.dtype, src.dimensions,
                                               zlib=compression, fill_value=getattr(src, "_FillValue", None))
                    var.setncatts({k: src.getncattr(k) for k in src.ncattrs() if k != "_FillValue"})
                    src.set_auto_maskandscale(False)
                    var.set_auto_maskandscale(False)
                    if src.dtype is str and not src.dimensions:
                        var[()] = str(np.asarray(src[()]).item())
                    elif product == "hydro" and src.dimensions == ("xFRF",):
                        var[:] = src[::HYDRO_STRIDE]
                    else:
                        var[:] = src[:]
                samples = len(local.dimensions["time"])
                if product == "hydro":
                    local.source_hydro_xfrf_stride = HYDRO_STRIDE
                    with nc.Dataset(origin + "?" + ",".join(HYDRO_FIELDS)) as metadata:
                        for key in HYDRO_FIELDS:
                            src = metadata.variables[key]
                            var = local.createVariable(key, "f8", ("time", "xFRF"), zlib=True,
                                                       fill_value=src._FillValue)
                            var.setncatts({k: src.getncattr(k) for k in src.ncattrs() if k != "_FillValue"})
                    for start in range(0, samples, 36):
                        end = min(samples - 1, start + 35)
                        for field, values in hydro_bulk(origin, HYDRO_FIELDS, start, end, len(remote.dimensions["xFRF"])):
                            local[field][start:end + 1] = values
            partial.replace(out)
            result.update(retrieved_utc=retrieved, samples=samples)
            if product == "hydro":
                result["source_hydro_xfrf_stride"] = HYDRO_STRIDE
            return result
        except (OSError, KeyError, TypeError, RuntimeError, ValueError, requests.RequestException) as exc:
            partial.unlink(missing_ok=True)
            if attempt == 1:
                result["error"] = str(exc)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=Path("data/raw/environment_native"), type=Path)
    parser.add_argument("--months", nargs="+", default=["06", "09", "10"])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(max_workers=5) as pool:
        rows = list(pool.map(save, ((args.output, p, m) for m in args.months for p in PRODUCTS)))
    (args.output / "requests.json").write_text(json.dumps(rows, indent=2) + "\n")
    for row in rows:
        print(row["filename"], row.get("samples"), row.get("error") or "")
    if any("error" in row for row in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
