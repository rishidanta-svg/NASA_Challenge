"""Rasterio XYZ reprojection and lossless, transparent scientific PNGs."""

from functools import lru_cache
from io import BytesIO

import httpx
import numpy as np
from PIL import Image
import rasterio
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject, transform_bounds

ORIGIN = 20037508.342789244
SIZE = 256
AWS_MAX = 15


def tile_bounds(z, x, y):
    side = 2 * ORIGIN / (1 << z)
    return -ORIGIN + x*side, ORIGIN - (y+1)*side, -ORIGIN + (x+1)*side, ORIGIN - y*side


@lru_cache(maxsize=32)
def aws_dem(z, x, y):
    response = httpx.get(f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png", timeout=6)
    response.raise_for_status()
    red, green, blue = np.moveaxis(np.asarray(Image.open(BytesIO(response.content)).convert("RGB"),
                                               dtype=np.float32), 2, 0)
    return red*256 + green + blue/256 - 32768


def terrain_background(z, x, y, affine):
    parent = min(z, AWS_MAX)
    scale = 1 << (z-parent)
    px, py = x//scale, y//scale
    source = aws_dem(parent, px, py)
    result = np.empty((SIZE, SIZE), np.float32)
    reproject(source, result, src_transform=from_bounds(*tile_bounds(parent,px,py), SIZE,SIZE),
              src_crs="EPSG:3857", dst_transform=affine, dst_crs="EPSG:3857",
              resampling=Resampling.bilinear)
    return result


def encode(values, colormap=None):
    if colormap is None:
        integer = np.clip(np.rint((values + 32768)*256), 0, 2**24-1).astype(np.uint32)
        pixels = np.stack([integer >> 16, (integer >> 8) & 255, integer & 255], axis=2).astype(np.uint8)
    else:
        stops = colormap["stops"]
        rgb = [[int(color[i:i+2],16) for i in (1,3,5)] for _, color in stops]
        valid = np.isfinite(values)
        pixels = np.zeros((SIZE,SIZE,4),dtype=np.uint8)
        for ch in range(3):
            pixels[:,:,ch][valid] = np.rint(np.interp(values[valid], [pos for pos,_ in stops],
                                                      [color[ch] for color in rgb])).astype(np.uint8)
        pixels[:,:,3][valid] = 255
    output = BytesIO()
    Image.fromarray(pixels).save(output, format="PNG", optimize=True)
    return output.getvalue()


def render(path, descriptor, z, x, y):
    bounds = tile_bounds(z, x, y)
    affine = from_bounds(*bounds, SIZE, SIZE)
    values = np.full((SIZE,SIZE), np.nan, np.float32)
    dem = descriptor["kind"] == "raster_dem"
    with rasterio.open(path) as source:
        a,b,c,d = transform_bounds(source.crs, "EPSG:3857", *source.bounds)
        if bounds[0] < c and bounds[2] > a and bounds[1] < d and bounds[3] > b:
            reproject(rasterio.band(source, 1), values, dst_transform=affine, dst_crs="EPSG:3857",
                      src_nodata=source.nodata, dst_nodata=np.nan, resampling=Resampling.nearest)
    if dem and not np.isfinite(values).all():
        background = terrain_background(z, x, y, affine)
        values = np.where(np.isfinite(values), values, background)
    return encode(values, descriptor.get("colormap"))
