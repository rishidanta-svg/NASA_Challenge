"""Shared study geometry, raster export and provenance utilities."""

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from affine import Affine
import numpy as np
from pyproj import Transformer
import rasterio
from rasterio.shutil import copy as copy_raster
from shapely import segmentize
from shapely.geometry import box
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[1]
AOI = (-75.753384, 36.183704, -75.750335, 36.188260)
ALONGSHORE = (700, 1190)
UTM = 32618
EPOCHS = {
    "june": ("202606", "2026-06-19T00:31:04Z", 111),
    "october": ("202610", "2026-10-16T23:33:04Z", 362),
}
VERTICAL_DATUM = "NAVD88 (geoid12b)"
TO_UTM = Transformer.from_crs(4326, UTM, always_xy=True)
TO_WGS84 = Transformer.from_crs(UTM, 4326, always_xy=True)
AOI_UTM = transform(TO_UTM.transform, segmentize(box(*AOI), 0.0001))


@dataclass(frozen=True)
class Grid:
    width: int
    height: int
    affine: Affine
    epsg: int = UTM

    def centers(self):
        rows, cols = np.indices((self.height, self.width))
        return self.affine * (cols + 0.5, rows + 0.5)

    def metadata(self):
        return dict(epsg=self.epsg, width=int(self.width), height=int(self.height),
                    affine=list(self.affine)[:6], first_center=list(self.affine * (0.5, 0.5)))


def reference_grid(spacing, x_origin=0, y_origin=0):
    left, bottom, right, top = AOI_UTM.bounds
    west = x_origin + np.floor((left - x_origin) / spacing) * spacing
    north = y_origin + np.ceil((top - y_origin) / spacing) * spacing
    return Grid(int(np.ceil((right - west) / spacing)),
                int(np.ceil((north - bottom) / spacing)),
                Affine(spacing, 0, west, 0, -spacing, north))


def utc(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def now():
    return datetime.now(timezone.utc).isoformat()


def array(variable):
    return np.ma.asarray(variable, dtype="float64").filled(np.nan)


def write_json(path, payload):
    pending = path.with_suffix(path.suffix + ".part")
    pending.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    pending.replace(path)


def file_record(path, root):
    with path.open("rb") as stream:
        digest = sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"filename": str(path.relative_to(root)), "bytes": path.stat().st_size,
            "sha256": digest.hexdigest()}


def write_raster(path, grid, values, unit, tags=None):
    data = np.asarray(values)
    if data.shape != (grid.height, grid.width):
        raise ValueError(f"{path.name}: grid and raster shape differ")
    with rasterio.io.MemoryFile() as mem:
        with mem.open(driver="GTiff", width=grid.width, height=grid.height,
                      count=1, dtype=data.dtype, crs=f"EPSG:{grid.epsg}",
                      transform=grid.affine, nodata=np.nan) as out:
            out.write(data, 1)
            out.set_band_unit(1, unit)
            out.update_tags(AREA_OR_POINT="Area", **(tags or {}))
        pending = path.with_suffix(".tif.part")
        with mem.open() as raster:
            copy_raster(raster, pending, driver="COG", compress="DEFLATE",
                        overview_count=0)
        pending.replace(path)


def stats(values):
    finite = np.asarray(values)[np.isfinite(values)]
    result = {"valid_pixels": int(finite.size)}
    if finite.size:
        result.update(min=float(finite.min()), max=float(finite.max()),
                      mean=float(finite.mean()), median=float(np.median(finite)),
                      std=float(finite.std()), rmse=float(np.sqrt(np.mean(finite**2))))
    return result
