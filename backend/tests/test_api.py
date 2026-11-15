import json
import math
from io import BytesIO
from hashlib import sha256

from fastapi.testclient import TestClient
import numpy as np
from PIL import Image
import rasterio
from rasterio.warp import transform

from backend.app import ROOT, create_app
from backend.environment import observation
from backend.raster import SIZE, tile_bounds

DATA = ROOT / "data/processed/verified"
CLIENT = TestClient(create_app())


def xy(lng, lat, z):
    n = 1 << z
    return int((lng + 180) / 360 * n), int((1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n)


def test_metadata_and_missing_products(tmp_path):
    acquisitions = CLIENT.get("/api/acquisitions").json()
    assert len(acquisitions) == 11
    assert {a["sensor"] for a in acquisitions} == {"LIDAR", "NISAR", "SENTINEL-1", "SENTINEL-2"}
    assert len({a["id"] for a in acquisitions}) == len(acquisitions)
    assert len([a for a in acquisitions if a["sensor"] == "NISAR"]) == 3
    study = CLIENT.get("/api/study-area").json()
    assert study["geometry"]["coordinates"][0][0] == [-75.753384, 36.183704]
    result = CLIENT.get("/api/analysis/FRF-950")
    assert result.json()["status"] == "unavailable"
    assert CLIENT.get("/api/transects/../private.txt").status_code == 404
    assert CLIENT.get("/api/tiles/lidar-dz-2026-oct-jun/4/16/0.png").status_code == 404
    assert CLIENT.get("/api/layers", headers={"Origin": "http://localhost:5173"}).headers[
        "access-control-allow-origin"] == "http://localhost:5173"
    missing = TestClient(create_app(tmp_path))
    assert missing.get("/api/layers").json() == []
    assert missing.get("/api/terrain/change").json()["status"] == "unavailable"


def test_profiles_are_measured_and_have_explicit_reference():
    node = CLIENT.get("/api/transects/FRF-950").json()
    source = next(p for p in json.loads((DATA/"lidar/profiles.json").read_text())["profiles"] if p["id"] == "FRF-950")
    assert node["boundaries"] == []
    for index, epoch in enumerate(("june", "october")):
        assert node["profiles"][index]["points"][0] == {"x_m": 0.0, "z_m": source[epoch][0]["z"]}
        assert node["profiles"][index]["acquired_at"] == source[epoch + "_utc"]
    assert CLIENT.get("/api/transects/observations.geojson").json()["features"]


def test_exact_cog_and_web_mercator_pixel_colors():
    path = DATA / "comparison/nisar_june_HHHH_db.tif"
    original = path.read_bytes()
    result = CLIENT.get("/api/rasters/nisar-hh-june.tif")
    assert sha256(result.content).digest() == sha256(original).digest()
    z = 16
    with rasterio.open(BytesIO(original)) as src:
        where = np.argwhere(np.isfinite(src.read(1)))
        row, col = where[len(where)//2]
        e, n = src.xy(row,col)
        d = float(src.read(1)[row,col])
    lng, lat = (v[0] for v in transform(32618,4326,[e],[n]))
    x, y = xy(lng, lat, z)
    out = CLIENT.get(f"/api/tiles/nisar-hh-june/{z}/{x}/{y}.png")
    assert out.status_code == 200
    image = np.array(Image.open(BytesIO(out.content)))
    ex, ny = (v[0] for v in transform(32618,3857,[e],[n]))
    w,s,e,n = tile_bounds(z,x,y)
    i,j = int((n-ny)/(n-s)*SIZE),int((ex-w)/(e-w)*SIZE)
    rgb = [int(round(np.interp(d, [-34,-18,1], values))) for values in zip(
        (23,20,51),(73,117,132),(251,244,193))]
    assert image[i,j].tolist() == [*rgb,255]
    empty = CLIENT.get("/api/tiles/nisar-hh-june/16/0/0.png")
    assert np.count_nonzero(np.array(Image.open(BytesIO(empty.content)))[:,:,3]) == 0


def test_noaa_missing_never_becomes_zero():
    row = observation("water_level", ("water_level","Water level","m","v"),
                      {"t":"2026-11-15 12:30","v":"","q":"p"})
    assert row["value"] is None
    assert row["observed_at"] == "2026-11-15T12:30:00+00:00"
    assert row["quality"] == "preliminary" and row["datum"] == "NAVD88"


def test_terrarium_packs_real_lidar_height(monkeypatch):
    # Isolate the background in this test. The browser test requests real AWS tiles.
    monkeypatch.setattr("backend.raster.terrain_background",
                        lambda *args: np.full((256, 256), 12.25, dtype=np.float32))
    src = DATA / "lidar/lidar_october_utm_1m.tif"
    z = 18
    with rasterio.open(src) as dataset:
        values = dataset.read(1)
        row, col = np.argwhere(np.isfinite(values))[len(np.argwhere(np.isfinite(values)))//2]
        east, north = dataset.xy(row, col)
        surveyed = float(values[row, col])
    lng, lat = (v[0] for v in transform(32618,4326,[east],[north]))
    x, y = xy(lng, lat, z)
    png = CLIENT.get(f"/api/tiles/lidar-dem-october/{z}/{x}/{y}.png")
    assert png.status_code == 200
    pixels = np.asarray(Image.open(BytesIO(png.content)), dtype=np.int32)
    e, n = (v[0] for v in transform(32618,3857,[east],[north]))
    w,s,right,top = tile_bounds(z,x,y)
    red, green, blue = pixels[int((top-n)/(top-s)*SIZE),int((e-w)/(right-w)*SIZE)]
    assert abs((red*256 + green + blue/256 - 32768) - surveyed) < 1/256
