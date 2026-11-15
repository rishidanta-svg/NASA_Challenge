"""Retrieve native Sentinel pixel windows and authoritative metadata for Duck."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import io
import json
from pathlib import Path
import os
import re
from threading import Lock
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

import numpy as np
import rasterio
from rasterio.transform import array_bounds
from rasterio.windows import Window, from_bounds
from rasterio.warp import transform_bounds
import requests
from shapely.geometry import box, shape

from discover import BBOX

BANDS = {"B02": ("blue", 10, 1), "B03": ("green", 10, 2), "B04": ("red", 10, 3),
         "B08": ("nir", 10, 7), "B11": ("swir16", 20, 11), "B12": ("swir22", 20, 12)}
TOKEN_API = "https://planetarycomputer.microsoft.com/api/sas/v1/token"
TOKENS = {}
TOKEN_LOCK = Lock()
GROUPS = ("june", "september", "october")


def stac_items(root, name):
    seen = {}
    for period in GROUPS:
        path = root / f"{name}_{period}.json"
        if not path.exists():
            raise FileNotFoundError(path)
        data = json.loads(path.read_text())
        if (any(link.get("rel") == "next" for link in data.get("links", []))
                and data.get("context", {}).get("matched") != len(data["features"])):
            raise ValueError(f"Paginated search must be expanded before acquisition: {path}")
        for item in data["features"]:
            if shape(item["geometry"]).intersects(box(*BBOX)):
                seen[item["id"]] = item
    return list(seen.values())


def signed_url(href):
    if ".blob.core.windows.net/" not in href:
        return href
    parsed = urlsplit(href)
    account = parsed.hostname.split(".")[0]
    container = parsed.path.split("/")[1]
    key = (account, container)
    with TOKEN_LOCK:
        if key not in TOKENS:
            headers = {}
            subscription = os.environ.get("PC_SDK_SUBSCRIPTION_KEY")
            if subscription:
                headers["Ocp-Apim-Subscription-Key"] = subscription
            response = requests.get(f"{TOKEN_API}/{account}/{container}", headers=headers, timeout=20)
            if not response.ok:
                raise RuntimeError(f"SAS token status {response.status_code} for {account}/{container}")
            TOKENS[key] = response.json()["token"].lstrip("?")
    return href + "?" + TOKENS[key]


def xml_asset(item, key, target):
    if not target.exists():
        response = requests.get(signed_url(item["assets"][key]["href"]), timeout=30)
        if not response.ok:
            raise RuntimeError(f"{key} returned HTTP {response.status_code}")
        ET.fromstring(response.content)
        target.write_bytes(response.content)
    return ET.parse(target).getroot()


class RangeReader(io.RawIOBase):
    """Seekable HTTP reader that checks exact byte ranges and retries short transfers."""

    def __init__(self, href):
        self.href = href
        self.session = requests.Session()
        self.position = 0
        try:
            _, self.length = self.fetch(0, 0)
        except BaseException:
            self.session.close()
            raise

    def fetch(self, start, end):
        for attempt in range(4):
            try:
                headers = {"Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"}
                with self.session.get(self.href, headers=headers, timeout=15, stream=True) as response:
                    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
                    if response.status_code != 206 or match is None or tuple(map(int, match.groups()[:2])) != (start, end):
                        raise RuntimeError(f"Invalid HTTP range response ({response.status_code})")
                    data = response.content
                    if len(data) != end - start + 1:
                        raise RuntimeError("Incomplete HTTP range response")
                    return data, int(match.group(3))
            except (requests.RequestException, RuntimeError):
                if attempt == 3:
                    raise
        raise RuntimeError("HTTP range retries exhausted")

    def seek(self, offset, whence=io.SEEK_SET):
        start = {io.SEEK_SET: 0, io.SEEK_CUR: self.position, io.SEEK_END: self.length}[whence]
        self.position = start + offset
        return self.position

    def tell(self):
        return self.position

    def read(self, size=-1):
        remaining = max(0, self.length - self.position)
        length = min(remaining, size) if size >= 0 else remaining
        if length > 64 * 1024 * 1024:
            raise RuntimeError("Refusing an unbounded full-scene TIFF read")
        output = bytearray()
        while len(output) < length:
            chunk = min(length - len(output), 32768)
            data, _ = self.fetch(self.position, self.position + chunk - 1)
            output.extend(data)
            self.position += chunk
        return bytes(output)

    def close(self):
        self.session.close()
        super().close()


def save_window(item, key, target, grid, expected_spacing, nodata=None):
    asset = item["assets"][key]
    if target.exists():
        with rasterio.open(target) as src:
            return src.tags()
    transform = rasterio.Affine(*grid["affine"])
    bounds = array_bounds(grid["height"], grid["width"], transform)
    left, bottom, right, top = bounds
    padded = (left - 60, bottom - 60, right + 60, top + 60)
    for attempt in range(3):
        try:
            with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_TIMEOUT="25", GDAL_HTTP_VERSION="1.1"):
                href = signed_url(asset["href"])
                options = {"opener": lambda _name, _mode: RangeReader(href)} if attempt else {}
                raster_path = item["id"] + "-" + key + ".tif" if options else href
                with rasterio.open(raster_path, **options) as src:
                    if not np.allclose(src.res, (expected_spacing, expected_spacing)):
                        raise ValueError(f"Unexpected native spacing for {item['id']}/{key}: {src.res}")
                    src_bounds = transform_bounds(f"EPSG:{grid['epsg']}", src.crs, *padded, densify_pts=21)
                    roi = from_bounds(*src_bounds, transform=src.transform)
                    x0, y0 = np.floor([roi.col_off, roi.row_off]).astype(int)
                    x1, y1 = np.ceil([roi.col_off + roi.width, roi.row_off + roi.height]).astype(int)
                    w = Window(x0, y0, x1 - x0, y1 - y0).intersection(Window(0, 0, src.width, src.height))
                    pixels = src.read(1, window=w)
                    profile = src.profile.copy()
                    profile.update(driver="GTiff", transform=src.window_transform(w), width=pixels.shape[1],
                                   height=pixels.shape[0], nodata=src.nodata if nodata is None else nodata,
                                   tiled=False, compress="deflate")
                    profile.pop("blockxsize", None)
                    profile.pop("blockysize", None)
                    tags = src.tags()
                    tags.update(source_asset=asset["href"], source_id=item["id"],
                                source_window_col_row_width_height=json.dumps([int(v) for v in w.flatten()]),
                                source_full_shape_yx=json.dumps(list(src.shape)))
                    with rasterio.open(target, "w", **profile) as dst:
                        dst.write(pixels, 1)
                        dst.update_tags(**tags)
                    return tags
        except (requests.RequestException, rasterio.errors.RasterioError, RuntimeError) as exc:
            target.unlink(missing_ok=True)
            if attempt == 2:
                raise RuntimeError(f"Native download failed for {item['id']}/{key}: {type(exc).__name__}") from None
    raise RuntimeError("Native window acquisition exhausted")


def xml_value(root, tag):
    return next(e.text for e in root.iter() if e.tag.split("}")[-1] == tag)


def optical(pc, earth, root, grid):
    output = root / pc["id"]
    output.mkdir(parents=True, exist_ok=True)
    product = xml_asset(pc, "product-metadata", output / "product.xml")
    tile = xml_asset(earth, "granule_metadata", output / "tile.xml")
    timestamp = xml_value(tile, "SENSING_TIME")
    quant = float(xml_value(product, "BOA_QUANTIFICATION_VALUE"))
    offsets = {int(e.attrib["band_id"]): float(e.text) for e in product.iter()
               if e.tag.split("}")[-1] == "BOA_ADD_OFFSET"}
    for key, (_, spacing, band_id) in BANDS.items():
        if band_id not in offsets:
            raise ValueError(f"Missing producer offset for {pc['id']}/{key}")
        save_window(pc, key, output / f"{key}_dn.tif", grid, spacing, nodata=0)
    save_window(pc, "SCL", output / "SCL.tif", grid, 20, nodata=0)
    # An independent delivered encoding checks for double offset and clipped negatives.
    encoding_check = {}
    for key, (asset, spacing, band_id) in BANDS.items():
        local = output / f"{key}_e84_dn.tif"
        try:
            save_window(earth, asset, local, grid, spacing, nodata=0)
        except RuntimeError:
            encoding_check[key] = {"status": "independent_COG_window_unavailable"}
            continue
        with rasterio.open(local) as e84, rasterio.open(output / f"{key}_dn.tif") as original:
            if (e84.crs, e84.transform, e84.shape) != (original.crs, original.transform, original.shape):
                raise ValueError(f"Provider grid mismatch for {pc['id']}/{key}")
            c = original.read(1).astype("int32")
            e = e84.read(1).astype("int32")
            good = (c > 0) & (e > 0) & (c + offsets[band_id] > 0)
            delta = e[good] - c[good]
            if delta.size and not bool(np.all(delta == offsets[band_id])):
                raise ValueError(f"Provider DN cross-check failed for {pc['id']}/{key}")
            encoding_check[key] = {"matched_positive_samples": int(delta.size),
                                   "original_positive_e84_zero": int(np.count_nonzero((c > 0) & (e == 0))),
                                   "expected_Earth_Search_minus_Planetary_Computer_DN": offsets[band_id]}
    return {"sensor": "Sentinel-2", "id": pc["id"], "timestamp_utc": timestamp,
            "alternate_stac_item_id": earth["id"], "manufacturer_product_id": pc["properties"]["s2:product_uri"],
            "quantification": quant, "offset_dn": {key: offsets[band_id] for key, (_, _, band_id) in BANDS.items()},
            "encoding_check": encoding_check, "tile_cloud_percent": earth["properties"]["eo:cloud_cover"],
            "planetary_computer_item": pc, "earth_search_item": earth}


def radar(pc, grd, root, grid):
    output = root / pc["id"]
    output.mkdir(parents=True, exist_ok=True)
    checks = {}
    for key in ("vv", "vh"):
        tags = save_window(pc, key, output / f"{key}_gamma0.tif", grid, 10)
        checks[key] = {k: tags[k] for k in ("Acquisition_DateTime", "IncidenceNearAngle", "IncidenceFarAngle",
                                           "OrbitDirection", "LookDirection") if k in tags}
    return {"sensor": "Sentinel-1", "id": pc["id"], "timestamp_utc": pc["properties"]["datetime"],
            "manufacturer_product_id": pc["properties"]["s1:product_identifier"],
            "incidence_angle_deg_near_far": [float(checks["vv"][key])
                                               for key in ("IncidenceNearAngle", "IncidenceFarAngle")],
            "local_incidence_angle_deg": None, "radar_tag_checks": checks,
            "planetary_computer_item": pc, "earth_search_grd_item": grd}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discovery", type=Path, default=Path("data/raw/discovery"))
    parser.add_argument("--native", type=Path, default=Path("data/raw/sentinel_native"))
    parser.add_argument("--comparison-manifest", required=True, type=Path)
    parser.add_argument("--workers", default=4, type=int)
    args = parser.parse_args()
    grid = json.loads(args.comparison_manifest.read_text())["comparison"]["grid"]
    args.native.mkdir(parents=True, exist_ok=True)
    earth = {i["properties"]["s2:product_uri"]: i for i in stac_items(args.discovery, "s2_earth")}
    grd = {i["id"]: i for i in stac_items(args.discovery, "s1_earth_grd")}
    tasks = [(optical, i, earth[i["properties"]["s2:product_uri"]])
             for i in stac_items(args.discovery, "s2_pc")]
    tasks.extend((radar, i, grd[i["id"].removesuffix("_rtc")])
                 for i in stac_items(args.discovery, "s1_pc_rtc"))
    results = []
    errors = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(worker, i, other, args.native, grid): i["id"] for worker, i, other in tasks}
        for future in as_completed(futures):
            scene_id = futures[future]
            try:
                result = future.result()
                results.append(result)
                print("Retrieved", scene_id, flush=True)
            except Exception as exc:
                errors.append({"id": scene_id, "failure": str(exc)})
                print("Unavailable", scene_id, str(exc), flush=True)
    manifest = {"observations": sorted(results, key=lambda r: r["timestamp_utc"]), "failures": errors}
    partial = args.native / "acquisition.json.part"
    partial.write_text(json.dumps(manifest, indent=2) + "\n")
    partial.replace(args.native / "acquisition.json")
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
