"""Verify the pinned GCOV observations and extract Frequency A science layers."""

from contextlib import contextmanager
from hashlib import md5
import json
import logging
from pathlib import Path
import re
import time
from urllib.parse import unquote, urlsplit

from affine import Affine
import h5py
import numpy as np
from pyproj import Transformer
import rasterio
from rasterio.transform import array_bounds
from rasterio.warp import Resampling, reproject, transform_bounds
import requests
from requests.adapters import HTTPAdapter
import shapely
from shapely.geometry import Polygon, box, shape
from shapely.ops import transform
from urllib3.util.retry import Retry

from duck_common import (
    AOI, EPOCHS, Grid, UTM, array, file_record, now, reference_grid, utc, write_json,
    write_raster,
)

COLLECTION = "C2854338529-ASF"
CMR = "https://cmr.earthdata.nasa.gov/search"
ASF = "https://api.daac.asf.alaska.edu/services/search/param"
HARMONY = "https://harmony.earthdata.nasa.gov"
GCOV = "/science/LSAR/GCOV"
GROUP = f"{GCOV}/grids/frequencyA"
HARMONY_LAYERS = {"HHHH": "1", "HVHV": "1", "mask": "code", "numberOfLooks": "1",
                  "rtcGammaToSigmaFactor": "1"}
EXCEPTIONS = "inputDataExceptionMask"
LAYERS = {**HARMONY_LAYERS, EXCEPTIONS: "code"}
REQUIRED = {"HHHH", "HVHV", "mask", "numberOfLooks"}
PINNED = {
    "june": ("G4250721321-ASF", "023", "20260618T235335", "20260618T235409"),
    "october": ("G4376256706-ASF", "033", "20261016T235331", "20261016T235406"),
}
BUFFER = 0.001  # About 90–111 m; sufficient for edge cells and geolocation checks.
PADDED_AOI = tuple(value + sign * BUFFER for value, sign in zip(AOI, (-1, -1, 1, 1)))


def http_session(token=None):
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=Retry(
        total=3, backoff_factor=0.75, status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "HEAD"))))
    if token:
        session.headers["Authorization"] = f"Bearer {token}"
    return session


def json_get(session, url, **kwargs):
    response = session.get(url, timeout=(10, 60), **kwargs)
    response.raise_for_status()
    return response.json()


def catalog(epoch, root, refresh=False):
    concept_id, cycle, start, end = PINNED[epoch]
    name = f"NISAR_L2_PR_GCOV_{cycle}_069_D_070_4005_DHDH_A_{start}_{end}_P05023_N_F_J_001"
    cache = root / "raw" / f"{epoch}_nisar_catalog.json"
    queried = not cache.exists() or refresh
    if queried:
        with http_session() as session:
            cmr = json_get(session, f"{CMR}/granules.umm_json", params={"concept_id": concept_id})
            west, south, east, north = AOI
            polygon = f"POLYGON(({west} {south},{east} {south},{east} {north},{west} {north},{west} {south}))"
            date = f"{start[:4]}-{start[4:6]}-{start[6:8]}"
            asf = json_get(session, ASF, params=dict(
                dataset="NISAR", processingLevel="GCOV", relativeOrbit=69, frame=70,
                flightDirection="DESCENDING", intersectsWith=polygon,
                start=f"{date}T00:00:00Z", end=f"{date}T23:59:59Z", output="geojson"))
        raw = {"cmr": cmr, "asf": asf, "queried_at_utc": now()}
    else:
        raw = json.loads(cache.read_text())

    features = [f for f in raw["asf"]["features"] if f["properties"]["fileName"] == name + ".h5"]
    items = [g for g in raw["cmr"]["items"] if g["meta"]["concept-id"] == concept_id]
    if len(features) != 1 or len(items) != 1:
        raise ValueError(f"{epoch}: pinned granule absent or ambiguous in ASF or CMR")
    item, feature = items[0], features[0]
    umm = item["umm"]
    props = feature["properties"]
    if umm["GranuleUR"] != name or item["meta"]["collection-concept-id"] != COLLECTION:
        raise ValueError("CMR granule identity differs from the pinned identity")
    attrs = {a["Name"]: a["Values"] for a in umm["AdditionalAttributes"]}
    for key, value in {"TRACK_NUMBER": ["69"], "ASCENDING_DESCENDING": ["DESCENDING"],
                       "FRAME_NUMBER": ["70"], "PRODUCT_TYPE": ["GCOV"],
                       "FREQUENCY_A_POLARIZATION": ["HH", "HV"]}.items():
        if set(attrs.get(key, [])) != set(value):
            raise ValueError(f"Unexpected CMR attribute {key}: {attrs.get(key)}")
    dates = umm["TemporalExtent"]["RangeDateTime"]
    start_time, end_time = utc(dates["BeginningDateTime"]), utc(dates["EndingDateTime"])
    if utc(props["startTime"]) != start_time or abs((utc(props["stopTime"]) - end_time).total_seconds()) >= 1:
        raise ValueError("ASF and CMR acquisition times disagree")
    cmr_points = umm["SpatialExtent"]["HorizontalSpatialDomain"]["Geometry"]["GPolygons"][0]["Boundary"]["Points"]
    cmr_shape = Polygon([(v["Longitude"], v["Latitude"]) for v in cmr_points])
    study = box(*AOI)
    if not (cmr_shape.covers(study) and shape(feature["geometry"]).covers(study)):
        raise ValueError(f"{epoch}: catalog footprints do not cover the study bounds")
    archive = next(a for a in umm["DataGranule"]["ArchiveAndDistributionInformation"]
                   if a["Name"] == name + ".h5")
    lidar_time = utc(EPOCHS[epoch][1])
    midpoint = start_time + (end_time - start_time) / 2
    if queried:
        write_json(cache, raw)
    return {
        "granule": name, "cmr_concept_id": concept_id, "cmr_url": f"{CMR}/concepts/{concept_id}",
        "asf_catalog": ASF, "collection": umm["CollectionReference"],
        "version": attrs["PRODUCT_VERSION"][0], "release_identifier": "P05023",
        "url": props["url"], "filename": archive["Name"], "archive_bytes": archive["SizeInBytes"],
        "archive_checksum": archive["Checksum"], "attributes": attrs,
        "cmr_revision": item["meta"]["revision-id"],
        "acquisition_start_utc": start_time.isoformat(), "acquisition_end_utc": end_time.isoformat(),
        "lidar_minus_radar_midpoint_seconds": (lidar_time - midpoint).total_seconds(),
        "lidar_minus_radar_start_seconds": (lidar_time - start_time).total_seconds(),
        "lidar_minus_radar_end_seconds": (lidar_time - end_time).total_seconds(),
        "timing_note": "Frame timing, not a per-pixel time; tide, swash and beach state can differ.",
        "cmr_footprint": umm["SpatialExtent"], "asf_footprint": feature["geometry"],
        "catalog_status": "both catalog footprints cover study area",
        "catalog_cache": file_record(cache, root),
    }


def response_download(session, url, path, validator, resume=False):
    if path.exists():
        validator(path)
        return
    part = path.with_suffix(path.suffix + ".part")
    for attempt in range(3):
        offset = part.stat().st_size if resume and part.exists() else 0
        headers = {"Accept-Encoding": "identity"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        try:
            with session.get(url, stream=True, headers=headers, timeout=(20, 120)) as response:
                if response.status_code == 416 and offset:
                    validator(part)
                    part.replace(path)
                    return
                if not response.ok:
                    raise ValueError(f"{urlsplit(url).hostname} download HTTP {response.status_code}")
                mode = "wb"
                if response.status_code == 206:
                    start = re.match(r"bytes (\d+)-", response.headers.get("Content-Range", ""))
                    if not start or int(start[1]) != offset:
                        raise ValueError("Server returned an unexpected byte range")
                    mode = "ab"
                with part.open(mode) as out:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        out.write(chunk)
            validator(part)
            part.replace(path)
            return
        except requests.RequestException:
            if attempt == 2:
                raise ValueError(f"Interrupted download from {urlsplit(url).hostname}") from None
            time.sleep(2 ** attempt)


def read_cog(path):
    with rasterio.open(path) as src:
        if src.driver != "GTiff" or src.count != 1 or src.crs is None:
            raise ValueError("Expected a georeferenced, single-band science GeoTIFF")
        grid = Grid(src.width, src.height, src.transform, src.crs.to_epsg())
        check_grid(grid)
        return grid, array(src.read(1, masked=True)), {
            "band_tags": src.tags(1), "dataset_tags": src.tags(), "unit": src.units[0],
            "source_nodata": str(src.nodata),
        }


def read_harmony_assets(cache, root, metadata):
    grid, layers = None, {}
    for layer, info in metadata.items():
        path = cache / f"{layer}.tif"
        record = file_record(path, root)
        if any(record[key] != info[key] for key in record):
            raise ValueError(f"Harmony cached {layer} differs from its manifest")
        layer_grid, layers[layer], _ = read_cog(path)
        if grid is not None and grid != layer_grid:
            raise ValueError("Harmony layers did not preserve a common native affine")
        grid = layer_grid
    if not REQUIRED.issubset(layers):
        raise ValueError(f"Harmony returned incomplete science layers: {REQUIRED - layers.keys()}")
    source_bounds = box(*array_bounds(grid.height, grid.width, grid.affine))
    if not source_bounds.covers(box(*transform_bounds(4326, grid.epsg, *AOI, densify_pts=21))):
        raise ValueError("Harmony subset edge does not cover the study footprint")
    return grid, layers


def harmony_layers(token, meta, root, epoch):
    cache = root / "raw" / f"{epoch}_harmony"
    cache.mkdir(exist_ok=True)
    cache_index = cache / "request.json"
    completed_cache = cache / "assets.json"
    if completed_cache.exists():
        prov = json.loads(completed_cache.read_text())
        if prov["granule_id"] != meta["cmr_concept_id"]:
            raise ValueError("Cached Harmony result does not match the pinned granule")
        grid, layers = read_harmony_assets(cache, root, prov["downloaded_assets"])
        return grid, layers, prov
    if not token:
        raise ValueError("Earthdata authorization required to download numerical NISAR layers")
    with http_session(token) as session:
        if cache_index.exists():
            job = json.loads(cache_index.read_text())["job_id"]
        else:
            west, south, east, north = PADDED_AOI
            fields = [("forceAsync", "true"), ("granuleId", meta["cmr_concept_id"]),
                      ("subset", f"lat({south}:{north})"), ("subset", f"lon({west}:{east})"),
                      ("format", "image/tiff"), ("skipPreview", "true"), ("ignoreErrors", "false")]
            fields.extend(("variable", f"{GROUP}/{key}") for key in HARMONY_LAYERS)
            route = f"{HARMONY}/{COLLECTION}/ogc-api-coverages/1.0.0/collections/parameter_vars/coverage/rangeset"
            response = session.post(route, files=[(k, (None, v)) for k, v in fields], timeout=(10, 60))
            response.raise_for_status()
            job = response.json()["jobID"]
            write_json(cache_index, {"job_id": job, "bbox_wsen": PADDED_AOI,
                                     "granule_id": meta["cmr_concept_id"], "requested_at": now()})

        for poll in range(120):
            data = json_get(session, f"{HARMONY}/jobs/{job}", params={"linktype": "https"})
            status = data["status"]
            if status in ("successful", "successful_with_errors"):
                break
            if status not in ("accepted", "running", "running_with_errors"):
                cache_index.unlink(missing_ok=True)
                raise ValueError(f"Harmony job {job} ended with status {status}")
            time.sleep(min(5 + poll, 15))
        else:
            raise ValueError(f"Harmony job {job} timed out and can be resumed")

        links = []
        while True:
            page = data.get("links", [])
            links.extend(entry["href"] for entry in page if entry.get("rel") == "data")
            next_url = next((entry["href"] for entry in page if entry.get("rel") == "next"), None)
            if not next_url:
                break
            if urlsplit(next_url).hostname != urlsplit(HARMONY).hostname:
                raise ValueError("Unexpected host on Harmony pagination link")
            data = json_get(session, next_url)

        metadata = {}
        with http_session() as anonymous:
            for url in links:
                parsed = urlsplit(url)
                if parsed.scheme != "https" or not parsed.hostname:
                    raise ValueError("Harmony provided a non-HTTPS asset URL")
                filename = unquote(Path(parsed.path).name)
                parts = re.split(r"[^A-Za-z0-9]+", filename)
                matches = [layer for layer in LAYERS if layer in parts]
                if len(matches) != 1 or matches[0] in metadata:
                    raise ValueError(f"Cannot identify unique Harmony science layer: {filename}")
                layer = matches[0]
                path = cache / f"{layer}.tif"
                transport = session if parsed.hostname.endswith(".earthdata.nasa.gov") else anonymous
                response_download(transport, url, path, read_cog)
                _, _, info = read_cog(path)
                metadata[layer] = {**file_record(path, root), "artifact_name": filename,
                                   "url_without_query": url.split("?")[0], **info}
    grid, layers = read_harmony_assets(cache, root, metadata)
    prov = {"mode": "Harmony native CRS subset", "job_id": job,
            "granule_id": meta["cmr_concept_id"], "downloaded_assets": metadata}
    write_json(completed_cache, prov)
    return grid, layers, prov

def validate_archive(path, meta):
    if path.stat().st_size != meta["archive_bytes"]:
        raise ValueError("HDF5 size differs from the CMR archive metadata")
    digest = md5()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(data)
    checksum = meta["archive_checksum"]
    if checksum["Algorithm"] != "MD5" or digest.hexdigest() != checksum["Value"]:
        raise ValueError("HDF5 checksum differs from the CMR archive metadata")


def check_grid(grid):
    t = grid.affine
    if grid.epsg is None or t.b != 0 or t.d != 0 or t.a <= 0 or t.e >= 0:
        raise ValueError("GCOV science grid is not regular north-up with a known CRS")
    return grid


def json_attrs(obj):
    def encode(value):
        if isinstance(value, np.ndarray):
            if h5py.check_dtype(ref=value.dtype) or value.dtype.kind == "O":
                return str(value.dtype)
            return encode(value.item()) if value.ndim == 0 else [encode(item) for item in value.tolist()]
        if isinstance(value, (np.generic, bytes)):
            return value.decode(errors="replace") if isinstance(value, bytes) else encode(value.item())
        if isinstance(value, float) and not np.isfinite(value):
            return str(value)
        return value
    return {k: encode(v) for k, v in obj.attrs.items()
            if k not in ("DIMENSION_LIST", "REFERENCE_LIST")}


def h5_slice(h5, group):
    x, y = (np.asarray(h5[f"{group}/{axis}Coordinates"][:]) for axis in ("x", "y"))
    spacing = [h5.get(f"{group}/{axis}CoordinateSpacing") for axis in ("x", "y")]
    sx, sy = (float(ds[()]) if ds is not None else float(coords[1] - coords[0])
              for ds, coords in zip(spacing, (x, y)))
    epsg = int(h5[f"{group}/projection"][()])
    if not np.allclose(np.diff(x), sx, rtol=0) or not np.allclose(np.diff(y), sy, rtol=0):
        raise ValueError("Inconsistent coordinate spacing in HDF5")
    if sx <= 0 or sy >= 0:
        raise ValueError("Unexpected HDF5 coordinate orientation")
    w, s, e, n = transform_bounds(4326, epsg, *PADDED_AOI, densify_pts=21)
    cols = np.flatnonzero((x >= w - sx) & (x <= e + sx))
    rows = np.flatnonzero((y >= s + sy) & (y <= n - sy))
    if not cols.size or not rows.size:
        raise ValueError("No grid coordinates in the study bounds")
    grid = Grid(cols.size, rows.size, Affine(sx, 0, x[cols[0]] - sx / 2,
                                             0, sy, y[rows[0]] - sy / 2), epsg)
    return check_grid(grid), slice(rows[0], rows[-1] + 1), slice(cols[0], cols[-1] + 1), x, y


def extract_hdf(h5, root, epoch):
    grid, rows, cols, x, y = h5_slice(h5, GROUP)
    group = h5[GROUP]
    pols = {v.decode() if isinstance(v, bytes) else str(v) for v in group["listOfPolarizations"][:]}
    if not {"HH", "HV"}.issubset(pols) or not REQUIRED.issubset(group):
        raise ValueError(f"{epoch} HDF5 missing HH/HV or required quality layers")
    layers = {}
    attributes = {}
    for key in [name for name in LAYERS if name in group]:
        ds = group[key]
        if ds.shape != (len(y), len(x)):
            raise ValueError(f"Unexpected HDF5 grid for {key}")
        z = np.asarray(ds[rows, cols], dtype=np.float64)
        fill = ds.attrs.get("_FillValue")
        if fill is not None and key != "mask":
            z[z == fill] = np.nan
        layers[key] = z
        attributes[key] = json_attrs(ds)
    metadata = {
        "variable_attributes": attributes, "projection_attributes": json_attrs(group["projection"]),
        "native_dimensions": [len(y), len(x)], "native_first_center": [x[0], y[0]],
        "native_last_center": [x[-1], y[-1]],
        "subset_row_column_start": [int(rows.start), int(cols.start)],
    }
    return grid, layers, metadata


def save_geometry(h5, path):
    group = f"{GCOV}/metadata/radarGrid"
    gg, rows, cols, x, y = h5_slice(h5, group)
    geo = h5[group]
    h = geo["heightAboveEllipsoid"][:]
    shape = len(h), len(y), len(x)
    arrays = {"height_above_ellipsoid_m": h, "x": x[cols], "y": y[rows], "epsg": gg.epsg}
    attributes = {}
    for name in ("incidenceAngle", "zeroDopplerAzimuthTime"):
        if name not in geo:
            continue
        ds = geo[name]
        if ds.shape != shape:
            raise ValueError(f"Unexpected {name} radar-grid coordinate order")
        arrays[name] = ds[:, rows, cols]
        attributes[name] = json_attrs(ds)
    pending = path.with_suffix(".npz.part")
    with pending.open("wb") as stream:
        np.savez_compressed(stream, **arrays)
    pending.replace(path)
    return {"variable_attributes": attributes, "grid": gg.metadata(),
            "projection_attributes": json_attrs(geo["projection"]),
            "dimensions": ["height_above_ellipsoid_m", "y", "x"]}


def hdf_identification(h5, meta):
    group = h5["/science/LSAR/identification"]
    names = ("zeroDopplerStartTime", "zeroDopplerEndTime", "productVersion",
             "orbitPassDirection", "lookDirection", "trackNumber", "frameNumber",
             "absoluteOrbitNumber")
    values = {name: group[name][()] for name in names}
    result = {key: value.item() if isinstance(value, np.generic) else value
              for key, value in values.items()}
    result = {key: value.decode() if isinstance(value, bytes) else value
              for key, value in result.items()}
    for key, want in {"trackNumber": 69, "frameNumber": 70, "orbitPassDirection": "Descending",
                      "productVersion": meta["version"]}.items():
        if result[key] != want:
            raise ValueError(f"HDF5 {key} does not match CMR")
    ns = "datetime64[ns]"
    for key, catalog_time in (("zeroDopplerStartTime", "acquisition_start_utc"),
                              ("zeroDopplerEndTime", "acquisition_end_utc")):
        actual = np.datetime64(result[key], "ns")
        expected = np.datetime64(meta[catalog_time].split("+")[0], "ns")
        if abs(actual - expected) > np.timedelta64(1000, "ns"):
            raise ValueError(f"HDF5 {key} does not match CMR within its timestamp precision")
    start = np.datetime64(result["zeroDopplerStartTime"], "ns").astype(ns).astype("int64")
    end = np.datetime64(result["zeroDopplerEndTime"], "ns").astype(ns).astype("int64")
    midpoint = start + (end - start) // 2
    result["frame_midpoint_utc"] = str(np.datetime64(int(midpoint), "ns")) + "Z"
    return result


def supplement_radar(token, meta, root, epoch, radar):
    """Screen the delivered GCOV data with its source exception mask and verify its native grid."""
    grid, layers, provenance = radar
    path = root / "raw" / f"{epoch}_nisar_geometry.npz"
    mask_path = root / "raw" / f"{epoch}_nisar_exceptions.npz"
    index = root / "raw" / f"{epoch}_nisar_geometry.json"
    native = root / "raw" / meta["filename"]
    if index.exists():
        info = json.loads(index.read_text())
        if (info["granule_id"] != meta["cmr_concept_id"] or
                info["science_subset_grid"] != grid.metadata() or
                info["geometry_asset"] != file_record(path, root) or
                info["exception_asset"] != file_record(mask_path, root)):
            raise ValueError(f"{epoch}: cached GCOV geometry does not match the radar subset")
        with np.load(mask_path, allow_pickle=False) as cache:
            layers[EXCEPTIONS] = cache[EXCEPTIONS]
        return grid, layers, {**provenance, "source_hdf_metadata": info}
    if native.exists():
        transport = h5py.File(native, "r")
    else:
        if not token:
            raise ValueError("Earthdata authorization required to verify the radar exception mask")
        transport = open_remote_hdf(token, meta)
    with transport as source:
        h5, etag = source if isinstance(source, tuple) else (source, None)
        hdf_grid, _, _, x, y = h5_slice(h5, GROUP)
        if (grid.epsg != hdf_grid.epsg or
                not np.allclose([grid.affine.a, grid.affine.e], [hdf_grid.affine.a, hdf_grid.affine.e],
                                atol=1e-9, rtol=0)):
            raise ValueError("Harmony result does not preserve the HDF5 science projection and spacing")
        first_x, first_y = grid.affine * (0.5, 0.5)
        col = int(round((first_x - x[0]) / grid.affine.a))
        row = int(round((first_y - y[0]) / grid.affine.e))
        if row < 0 or col < 0 or row + grid.height > len(y) or col + grid.width > len(x):
            raise ValueError("Delivered science window exceeds HDF5 dimensions")
        rows, cols = slice(row, row + grid.height), slice(col, col + grid.width)
        cx, cy = grid.centers()
        center_residual = float(np.hypot(cx - x[cols][None, :], cy - y[rows][:, None]).max())
        if center_residual > 1e-6:
            raise ValueError("Half-pixel or other native radar offset detected")
        band = h5[GROUP]
        for name in ("HHHH", "HVHV"):
            values = band[name][rows, cols]
            if not np.array_equal(values, layers[name], equal_nan=True):
                raise ValueError(f"Delivered {name} differs from actual HDF5 science values")
        ds = band[EXCEPTIONS]
        if ds.shape != (len(y), len(x)):
            raise ValueError("GCOV exception mask is on an unexpected grid")
        exceptions = ds[rows, cols]
        layers[EXCEPTIONS] = exceptions
        info = {
            "granule_id": meta["cmr_concept_id"], "url": meta["url"], "etag": etag,
            "identification": hdf_identification(h5, meta), "retrieved_utc": now(),
            "science_dimensions": [len(y), len(x)], "science_subset_grid": grid.metadata(),
            "projection_attributes": json_attrs(band["projection"]),
            "science_variable_attributes": {key: json_attrs(band[key]) for key in LAYERS if key in band},
            "hdf5_first_center": [float(x[0]), float(y[0])],
            "hdf5_last_center": [float(x[-1]), float(y[-1])],
            "subset_row_column": [row, col], "maximum_center_residual_m": center_residual,
            "hdf5_hh_hv_exact_array_match": True,
            "radar_geometry": save_geometry(h5, path),
        }
    pending = mask_path.with_suffix(".npz.part")
    with pending.open("wb") as stream:
        np.savez_compressed(stream, **{EXCEPTIONS: exceptions})
    pending.replace(mask_path)
    info.update(geometry_asset=file_record(path, root), exception_asset=file_record(mask_path, root))
    write_json(index, info)
    return grid, layers, {**provenance, "source_hdf_metadata": info}


def hdf_layers(token, meta, root, epoch, permit_download):
    raw = root / "raw"
    path = raw / meta["filename"]
    subset = raw / f"{epoch}_nisar_hyperslab.npz"
    index = raw / f"{epoch}_nisar_hyperslab.json"
    if index.exists() and not path.exists():
        provenance = json.loads(index.read_text())
        if (provenance["granule_id"] != meta["cmr_concept_id"] or
                provenance["hyperslab"] != file_record(subset, root)):
            raise ValueError("Cached radar hyperslab does not match its provenance")
        g = provenance["subset_grid"]
        grid = check_grid(Grid(g["width"], g["height"], Affine(*g["affine"]), g["epsg"]))
        with np.load(subset, allow_pickle=False) as cache:
            layers = {key: cache[key] for key in cache.files}
        return grid, layers, provenance

    if not path.exists() and not token:
        raise ValueError("Earthdata Login required for a numerical radar subset")
    if not path.exists():
        try:
            return range_hdf(token, meta, root, epoch, subset, index)
        except Exception as exc:
            if not permit_download:
                status = exc.response.status_code if isinstance(exc, requests.HTTPError) else None
                detail = f"HTTP {status}" if status is not None else type(exc).__name__
                raise ValueError(f"HDF5 byte-range access failed ({detail}); use a verified local archive "
                                 "or --allow-full-hdf5 for HTTPS download") from None
            logging.warning("%s: byte-range access failed, starting enabled archive download", epoch)

    with http_session(token) as session:
        response_download(session, meta["url"], path, lambda p: validate_archive(p, meta), resume=True)
    with h5py.File(path, "r") as h5:
        grid, layers, info = extract_hdf(h5, root, epoch)
    return grid, layers, {"mode": "validated HDF5 archive hyperslab",
                          "archive": file_record(path, root), **info}


@contextmanager
def open_remote_hdf(token, meta):
    from aiohttp import ClientTimeout
    import fsspec

    filename = meta["url"]
    size = meta["archive_bytes"]
    with http_session(token) as session:
        with session.get(filename, headers={"Range": "bytes=0-7", "Accept-Encoding": "identity"},
                         timeout=(10, 40), stream=True) as response:
            response.raise_for_status()
            if (response.status_code != 206 or
                    response.headers.get("Content-Range") != f"bytes 0-7/{size}" or
                    response.raw.read(8) != b"\x89HDF\r\n\x1a\n"):
                raise ValueError("Provider did not return the expected HDF5 byte range")
            etag = response.headers.get("ETag")
            resolved = response.url
    if urlsplit(resolved).scheme != "https":
        raise ValueError("Provider resolved the archive to a non-HTTPS endpoint")
    headers = {"Accept-Encoding": "identity"}
    if urlsplit(resolved).hostname == urlsplit(filename).hostname:
        headers["Authorization"] = f"Bearer {token}"
    if etag and not etag.startswith("W/"):
        headers["If-Match"] = etag
    fs = fsspec.filesystem("https", block_size=2**21, cache_type="blockcache",
                           cache_options={"maxblocks": 32},
                           client_kwargs={"timeout": ClientTimeout(total=90)}, headers=headers)
    with fs.open(resolved, "rb", size=size) as remote:
        with h5py.File(remote, "r") as h5:
            yield h5, etag


def range_hdf(token, meta, root, epoch, subset, index):
    with open_remote_hdf(token, meta) as (h5, etag):
        grid, layers, info = extract_hdf(h5, root, epoch)
    pending = subset.with_suffix(".npz.part")
    with pending.open("wb") as stream:
        np.savez_compressed(stream, **layers)
    pending.replace(subset)
    provenance = {"mode": "authenticated HDF5 byte-range hyperslab", "etag": etag,
                  "granule_id": meta["cmr_concept_id"], "subset_grid": grid.metadata(),
                  "hyperslab": file_record(subset, root), "retrieved_at": now(), **info}
    write_json(index, provenance)
    return grid, layers, provenance


def source_layers(token, meta, root, epoch, permit_download):
    path = root / "raw" / meta["filename"]
    harmony_error = None
    if not path.exists():
        if not token and (root / "raw" / f"{epoch}_nisar_hyperslab.json").exists():
            return hdf_layers(token, meta, root, epoch, permit_download)
        if not token and not (root / "raw" / f"{epoch}_harmony" / "assets.json").exists():
            raise ValueError("Earthdata authorization required to download numerical NISAR layers")
        try:
            return harmony_layers(token, meta, root, epoch)
        except Exception as exc:
            # A transient Harmony failure must never trigger an implicit multi-GB download.
            status = exc.response.status_code if isinstance(exc, requests.HTTPError) else None
            reason = f"HTTP {status}" if status is not None else str(exc)
            reason = re.sub(r"https?://[^\s'\"]+", "[remote URL]", reason)
            harmony_error = f"Harmony failed ({reason})"
            logging.warning("%s: %s", epoch, harmony_error)
    try:
        grid, data, prov = hdf_layers(token, meta, root, epoch, permit_download)
    except ValueError as exc:
        if harmony_error:
            raise ValueError(f"{harmony_error}. {exc}") from None
        raise
    if harmony_error:
        prov["harmony_status"] = harmony_error
    return grid, data, prov


def to_db(power):
    result = np.full(power.shape, np.nan)
    valid = np.isfinite(power) & (power > 0)
    result[valid] = 10 * np.log10(power[valid])
    return result


def pixel_offset(a, b):
    dx = (b.affine.c - a.affine.c) / a.affine.a
    dy = (b.affine.f - a.affine.f) / a.affine.e
    return [float(dx - round(dx)), float(dy - round(dy))]


def comparison_grid(loaded):
    june, october = (loaded[key][0] for key in EPOCHS)
    same_posting = (june.epsg == october.epsg == UTM and
                    np.allclose((june.affine.a, june.affine.e), (october.affine.a, october.affine.e),
                                rtol=0, atol=1e-6) and np.isclose(june.affine.a, -june.affine.e))
    offset = pixel_offset(june, october) if same_posting else None
    compatible = same_posting and max(map(abs, offset)) < 1e-6
    if june.epsg == UTM and np.isclose(june.affine.a, -june.affine.e):
        grid = reference_grid(june.affine.a, june.affine.c, june.affine.f)
        method = "shared native radar posting" if compatible else "June radar reference posting"
    else:
        grid = reference_grid(10)
        method = "10 m UTM lattice with origins at 0 m"
    return grid, {"method": method, "same_crs_and_posting": bool(same_posting),
                  "native_lattice_residual_xy_pixels": offset,
                  "physical_cross_sensor_residual_m": None,
                  "uncertainty_note": "No surveyed independent cross-sensor control points. Grid agreement only."}


def radar_products(out, loaded, grid, clip):
    results = {}
    e, n = grid.centers()
    compare_inside = shapely.intersects_xy(clip, e, n)
    for epoch, (src_grid, data, prov) in loaded.items():
        cx, cy = src_grid.centers()
        transformer = Transformer.from_crs(4326, src_grid.epsg, always_xy=True)
        src_aoi = transform(transformer.transform, shapely.segmentize(box(*AOI), .0001))
        inside = shapely.intersects_xy(src_aoi, cx, cy)
        mask = data["mask"]
        if np.any(np.isfinite(mask) & ((mask != np.trunc(mask)) | (mask < 0) | (mask > 255))):
            raise ValueError("Unexpected GCOV subswath mask codes")
        looks = data["numberOfLooks"]
        quality = (mask > 0) & (mask < 255) & np.isfinite(looks) & (looks > 0)
        quality &= data[EXCEPTIONS] == 0
        prov["native_subset_grid"] = src_grid.metadata()
        identity = prov["source_hdf_metadata"]["identification"]
        source_tags = {
            "ACQUISITION_START_UTC": identity["zeroDopplerStartTime"] + "Z",
            "ACQUISITION_END_UTC": identity["zeroDopplerEndTime"] + "Z",
            "PRODUCT_VERSION": identity["productVersion"],
        }
        source_shape = (src_grid.height, src_grid.width)
        for name, values in data.items():
            raw = np.asarray(values, dtype="float64")
            if raw.shape != source_shape:
                raise ValueError("Inconsistent source grid shape")
            tags = dict(source_tags)
            if name in ("HHHH", "HVHV"):
                tags["BACKSCATTER"] = "gamma0"
            write_raster(out / f"nisar_{epoch}_{name}_native_raw.tif", src_grid,
                         np.where(inside, raw, np.nan).astype("float32"), LAYERS[name], tags)
            if name in ("HHHH", "HVHV"):
                raw = np.where(quality & np.isfinite(raw) & (raw >= 0), raw, np.nan)
                db = to_db(np.where(inside, raw, np.nan))
                if not np.isfinite(db).any():
                    raise ValueError(f"{epoch} {name}: no positive science pixels within the AOI")
                write_raster(out / f"nisar_{epoch}_{name}_native_db.tif", src_grid,
                             db.astype("float32"), "dB", tags)
            destination = np.full((grid.height, grid.width), np.nan)
            reproject(raw, destination, src_transform=src_grid.affine, src_crs=f"EPSG:{src_grid.epsg}",
                      src_nodata=np.nan, dst_transform=grid.affine, dst_crs=f"EPSG:{grid.epsg}",
                      dst_nodata=np.nan, resampling=Resampling.nearest)
            key = f"nisar_{epoch}_{name}"
            results[key] = np.where(compare_inside, destination, np.nan)
            if name in ("HHHH", "HVHV"):
                results[key + "_db"] = to_db(results[key])
                results[key + "_valid"] = np.where(compare_inside,
                                                   np.isfinite(results[key]), np.nan)
    for name in ("HHHH", "HVHV"):
        results[f"nisar_{name}_change_db"] = results[f"nisar_october_{name}_db"] - results[f"nisar_june_{name}_db"]
        if not np.isfinite(results[f"nisar_{name}_change_db"]).any():
            raise ValueError(f"No common quality-screened {name} in the comparison footprint")
    return results


def comparison_figure(out, grid, layers, loaded):
    from matplotlib import pyplot as plt

    from matplotlib.ticker import MaxNLocator

    fig, axes = plt.subplots(2, 3, figsize=(13, 8), constrained_layout=True)
    same_scale = np.concatenate([layers[f"nisar_{epoch}_HHHH_db"].ravel() for epoch in EPOCHS])
    low, high = np.nanpercentile(same_scale, [2, 98])
    west, south, east, north = array_bounds(grid.height, grid.width, grid.affine)
    for index, epoch in enumerate(EPOCHS):
        src, data, _ = loaded[epoch]
        bounds = array_bounds(src.height, src.width, src.affine)
        looks = data["numberOfLooks"]
        valid = (data["mask"] > 0) & (data["mask"] < 255) & np.isfinite(looks) & (looks > 0)
        valid &= data[EXCEPTIONS] == 0
        native = to_db(np.where(valid, data["HHHH"], np.nan))
        aligned = layers[f"nisar_{epoch}_HHHH_db"]
        for column, (values, (w, s, e, n), title) in enumerate((
            (native, bounds, f"GCOV native EPSG:{src.epsg}"),
            (aligned, (west, south, east, north), "Comparison grid EPSG:32618"),
        )):
            ax = axes[index, column]
            p = ax.imshow(values, extent=(w, e, s, n), origin="upper",
                          vmin=low, vmax=max(high, low + .01), cmap="gray",
                          interpolation="nearest")
            ax.set_title(f"{epoch} HH · {title}")
            fig.colorbar(p, ax=ax, label="dB", shrink=.65)
        ax = axes[index, 2]
        z = ax.imshow(layers[f"lidar_{epoch}_m"], extent=(west, east, south, north),
                      origin="upper", vmin=0, vmax=8, cmap="terrain", interpolation="nearest")
        ax.set_title(f"{epoch} LiDAR · comparison grid")
        fig.colorbar(z, ax=ax, label="m NAVD88", shrink=.65)
        for ax in axes[index]:
            ax.xaxis.set_major_locator(MaxNLocator(3))
            if index == 1:
                ax.set_xlabel("Easting (m)")
            ax.ticklabel_format(style="plain", useOffset=False)
    fig.savefig(out / "duck_radar_lidar_alignment.png", dpi=150)
    plt.close(fig)
