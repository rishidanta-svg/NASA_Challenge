import json
import logging
import math
import shutil
import sys
from io import BytesIO
from hashlib import sha256

from fastapi.testclient import TestClient
import numpy as np
from PIL import Image
import pyarrow as pa
import pyarrow.parquet as pq
import rasterio
from rasterio.warp import transform

from backend.app import ROOT, create_app
from backend.environment import observation
from backend.raster import SIZE, tile_bounds

DATA = ROOT / "data/processed/verified"
UNIFIED = DATA / "unified"
CLIENT = TestClient(create_app())


def xy(lng, lat, z):
    n = 1 << z
    return int((lng + 180) / 360 * n), int((1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n)


def test_metadata_and_missing_products(tmp_path):
    acquisitions = CLIENT.get("/api/acquisitions").json()
    assert len(acquisitions) == 28
    assert {a["sensor"] for a in acquisitions} == {"LIDAR", "NISAR", "SENTINEL-1", "SENTINEL-2"}
    assert len([a for a in acquisitions if a["group"] == "june"]) == 5
    assert len([a for a in acquisitions if a["group"] == "october"]) == 4
    assert len([a for a in acquisitions if a["group"] == "additional"]) == 19
    # Verify distinct June Sentinel-1 passes (June 16 Track 4 vs June 30 Track 106)
    june_s1 = CLIENT.get("/api/acquisitions?group=june&sensor=SENTINEL-1").json()
    assert len(june_s1) == 2
    assert {a["qa"]["relative_orbit"] for a in june_s1} == {4, 106}
    # Verify matched environmental summary on acquisitions
    s1_jun16 = next(a for a in june_s1 if a["qa"]["relative_orbit"] == 4)
    assert s1_jun16["environment"]["water_level_m_mllw"] == 1.176
    assert s1_jun16["environment"]["predicted_tide_stage"] == "rising"
    assert s1_jun16["environment"]["wave_hs_m_17m"] == 0.734

    study = CLIENT.get("/api/study-area").json()
    assert study["geometry"]["coordinates"][0][0] == [-75.753384, 36.183704]
    result = CLIENT.get("/api/analysis/FRF-950").json()
    assert result["transect_id"] == "FRF-950"
    assert result["inferred"] is True
    assert result["state_scope"] == "observed boundary features; not full terrain or bathymetry"
    assert len(result["epochs"]) == 3
    jun_ep = next(e for e in result["epochs"] if e["date"] == "2026-06")
    assert jun_ep["waterline"]["x_frf_m"] == 94.23
    assert jun_ep["waterline"]["x_m"] == 44.23
    assert jun_ep["dunetoe"]["accepted_x_frf_m"] == 62.8
    assert jun_ep["dunetoe"]["accepted_x_m"] == 12.8
    assert result["physics_model"]["status"] == "unavailable"
    # Verify ambiguous VV/VH disagreement withholding on FRF-1050 (June 2026: VV=60.5 m, VH=109.5 m)
    a1050 = CLIENT.get("/api/analysis/FRF-1050").json()
    jun1050 = next(e for e in a1050["epochs"] if e["date"] == "2026-06")
    assert jun1050["dunetoe"]["accepted_x_frf_m"] is None
    assert jun1050["dunetoe"]["status"].startswith("ambiguous:")
    assert CLIENT.get("/api/boundaries/s2-boundary-june.geojson").status_code == 200
    assert CLIENT.get("/api/boundaries/nisar-boundary-october.geojson").status_code == 200
    assert CLIENT.get("/api/boundaries/unknown.geojson").status_code == 404
    assert CLIENT.get("/api/transects/../private.txt").status_code == 404
    assert CLIENT.get("/api/tiles/lidar-dz-2026-oct-jun/4/16/0.png").status_code == 404
    assert CLIENT.get("/api/layers", headers={"Origin": "http://localhost:5173"}).headers[
        "access-control-allow-origin"] == "http://localhost:5173"
    missing = TestClient(create_app(tmp_path))
    assert missing.get("/api/layers").json() == []
    assert missing.get("/api/terrain/change").json()["status"] == "unavailable"


def test_unified_layers_preserve_full_sensor_coverage_and_168_overlap():
    layers = {l["id"]: l for l in CLIENT.get("/api/layers").json()}
    # Individual sensor layers must retain their full valid study-area coverage, not 168-cell clipped
    assert layers["nisar-hh-june"]["qa"]["valid_study_cells"] == 1310
    assert layers["s1-vv-2026-06-16"]["qa"]["valid_study_cells"] == 1450
    assert layers["s1-vv-2026-06-30"]["qa"]["valid_study_cells"] == 1450
    assert layers["s1-vv-2026-10-16"]["qa"]["valid_study_cells"] == 1450
    assert layers["s2-ndwi-2026-06-18"]["qa"]["valid_study_cells"] == 1442
    assert layers["s2-ndwi-2026-10-16"]["qa"]["valid_study_cells"] == 1450
    assert layers["s1-vv-change"]["qa"]["valid_study_cells"] == 1450
    assert layers["s2-ndwi-change"]["qa"]["valid_study_cells"] == 1442
    # Only the explicit 4-sensor overlap layer and 10m LiDAR change have 168 cells
    assert layers["all-sensor-overlap"]["qa"]["valid_study_cells"] == 168

    pairs = CLIENT.get("/api/comparisons/pairs").json()
    assert pairs["study_cells"] == 1450
    assert pairs["change_valid_overlap_counts"]["all_sensor_valid_overlap"] == 168
    assert pairs["change_valid_overlap_counts"]["nisar_HHHH_db_change_valid"] == 1310
    assert pairs["change_valid_overlap_counts"]["s1_VV_gamma0_db_change_valid"] == 1450
    assert pairs["change_valid_overlap_counts"]["s2_ndwi_change_valid"] == 1442
    assert len(pairs["environment_contrasts"]) == 152

    env_all = CLIENT.get("/api/environment/acquisitions").json()
    assert len(env_all["acquisitions"]) == 28
    lidar_id = "FRF-geomorphology_DEMs_duneLidarDEM_202606.nc#time_index=111"
    env_lidar = CLIENT.get(f"/api/environment/acquisitions/{lidar_id}").json()
    assert env_lidar["id"] == lidar_id
    assert env_lidar["summary"]["water_level_m_mllw"] == 0.797
    assert len(env_lidar["nearest"]) == 38


def test_profiles_are_measured_and_have_explicit_reference():
    node = CLIENT.get("/api/transects/FRF-950").json()
    source = next(p for p in json.loads((DATA/"lidar/profiles.json").read_text())["profiles"] if p["id"] == "FRF-950")
    assert node["properties"]["x_origin_frf_m"] == 50.0
    assert len(node["boundaries"]) >= 10
    s2_jun = next(b for b in node["boundaries"] if b["sensor"] == "SENTINEL-2" and b["epoch_label"] == "June 2026")
    assert s2_jun["x_frf_m"] == 94.23
    assert s2_jun["x_m"] == 44.23
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

    # Also verify multiband unified GeoTIFF tile rendering for Sentinel-1 (band 2) and Sentinel-2 (band 14)
    s1_tif = UNIFIED / "june/15_Sentinel-1.tif"
    with rasterio.open(s1_tif) as src:
        band2 = src.read(2)
        where = np.argwhere(np.isfinite(band2))
        row, col = where[len(where)//2]
        e, n = src.xy(row, col)
        val_db = float(band2[row, col])
    lng, lat = (v[0] for v in transform(32618, 4326, [e], [n]))
    x, y = xy(lng, lat, z)
    s1_tile = CLIENT.get(f"/api/tiles/s1-vv-2026-06-30/{z}/{x}/{y}.png")
    assert s1_tile.status_code == 200
    s1_img = np.array(Image.open(BytesIO(s1_tile.content)))
    ex, ny = (v[0] for v in transform(32618, 3857, [e], [n]))
    w, s, e_b, n_b = tile_bounds(z, x, y)
    i, j = int((n_b - ny) / (n_b - s) * SIZE), int((ex - w) / (e_b - w) * SIZE)
    expected_rgb = [int(round(np.interp(val_db, [-34, -18, 1], values))) for values in zip(
        (23, 20, 51), (73, 117, 132), (251, 244, 193))]
    assert s1_img[i, j].tolist() == [*expected_rgb, 255]


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


def _stage_unified_env_fixture(tmp_path):
    """Create a minimal verified + unified tree with real environmental Parquet files in tmp_path."""
    unified = tmp_path / "unified"
    env_dir = unified / "environment"
    env_dir.mkdir(parents=True)
    for name in ("acquisition_manifest.json", "cross_date_pairs.json", "geospatial_qa.json"):
        shutil.copy2(UNIFIED / name, unified / name)
    shutil.copy2(UNIFIED / "environment/environment_qa.json", env_dir / "environment_qa.json")
    for name in ("nearest.parquet", "tide_stage.parquet", "antecedent.parquet", "cross_date.parquet"):
        shutil.copy2(UNIFIED / "environment" / name, env_dir / name)
    return tmp_path, env_dir


def test_real_duck_environmental_observations_and_empty_time_range(tmp_path):
    env_all_res = CLIENT.get("/api/environment/acquisitions")
    assert env_all_res.status_code == 200
    env_all = env_all_res.json()
    assert env_all["status"] == "available"
    assert len(env_all["acquisitions"]) == 28
    assert len(env_all["cross_date_contrasts"]) == 152
    assert any(a["summary"]["water_level_m_mllw"] is not None for a in env_all["acquisitions"])

    lidar_id = "FRF-geomorphology_DEMs_duneLidarDEM_202606.nc#time_index=111"
    detail = CLIENT.get(f"/api/environment/acquisitions/{lidar_id}").json()
    assert detail["summary"]["water_level_timestamp_utc"] is not None
    assert {r["station_id"] for r in detail["nearest"]} >= {"NOAA CO-OPS 8651370", "USACE FRF Waverider 17m"}
    assert all("unit" in r and r["unit"] for r in detail["nearest"])

    # Valid dataset with zero acquisitions in the selected time range returns empty list, not an error
    empty_range = CLIENT.get(
        "/api/environment/acquisitions",
        params={"start": "2025-01-01T00:00:00Z", "end": "2025-01-02T00:00:00Z"},
    )
    assert empty_range.status_code == 200
    assert empty_range.json()["status"] == "available"
    assert empty_range.json()["acquisitions"] == []

    # Legitimately absent unified dataset returns explicit unavailable status
    absent = TestClient(create_app(tmp_path / "absent"))
    assert absent.get("/api/environment/acquisitions").json()["status"] == "unavailable"

    # Valid Parquet files with valid schemas and zero rows remain available with empty records
    root, env_dir = _stage_unified_env_fixture(tmp_path / "zero_rows")
    for name in ("nearest.parquet", "tide_stage.parquet", "antecedent.parquet", "cross_date.parquet"):
        table = pq.read_table(env_dir / name)
        pq.write_table(table.slice(0, 0), env_dir / name)
    zero_client = TestClient(create_app(root))
    zero_res = zero_client.get("/api/environment/acquisitions")
    assert zero_res.status_code == 200
    zero_body = zero_res.json()
    assert zero_body["status"] == "available"
    assert len(zero_body["acquisitions"]) == 28
    assert all(a["summary"] is None for a in zero_body["acquisitions"])
    assert zero_body["cross_date_contrasts"] == []
    zero_detail = zero_client.get(f"/api/environment/acquisitions/{lidar_id}")
    assert zero_detail.status_code == 200
    assert zero_detail.json()["nearest"] == []


def _assert_env_error_response_and_logs(client, caplog, expected_path_fragment, expected_exc_name):
    res = client.get("/api/environment/acquisitions")
    assert res.status_code == 500
    assert res.headers["content-type"].startswith("application/problem+json")
    body = res.json()
    assert body["status"] == 500
    assert "Traceback" not in body["detail"]
    assert str(expected_path_fragment) not in body["detail"]
    assert "/Users/" not in body["detail"]

    detail_res = client.get("/api/environment/acquisitions/FRF-geomorphology_DEMs_duneLidarDEM_202606.nc#time_index=111")
    assert detail_res.status_code == 500

    pairs_res = client.get("/api/comparisons/pairs")
    assert pairs_res.status_code == 200
    pairs = pairs_res.json()
    assert pairs["environment_status"] == "error"
    assert pairs["environment_contrasts"] is None
    assert pairs["environment_error"]

    acqs = client.get("/api/acquisitions").json()
    assert len(acqs) == 28
    assert all(a["environment"] is None for a in acqs)

    error_logs = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert any(expected_path_fragment in msg and expected_exc_name in msg for msg in error_logs), error_logs


def test_environment_failure_pyarrow_missing(monkeypatch, caplog):
    caplog.set_level(logging.ERROR, logger="backend.catalog")
    monkeypatch.setitem(sys.modules, "pyarrow", None)
    monkeypatch.setitem(sys.modules, "pyarrow.parquet", None)
    client = TestClient(create_app())
    _assert_env_error_response_and_logs(client, caplog, "nearest.parquet", "ModuleNotFoundError")


def test_environment_failure_missing_parquet(tmp_path, caplog):
    caplog.set_level(logging.ERROR, logger="backend.catalog")
    root, env_dir = _stage_unified_env_fixture(tmp_path)
    (env_dir / "nearest.parquet").unlink()
    client = TestClient(create_app(root))
    _assert_env_error_response_and_logs(client, caplog, "nearest.parquet", "FileNotFoundError")


def test_environment_failure_corrupted_parquet(tmp_path, caplog):
    caplog.set_level(logging.ERROR, logger="backend.catalog")
    root, env_dir = _stage_unified_env_fixture(tmp_path)
    (env_dir / "nearest.parquet").write_bytes(b"corrupted-not-parquet")
    client = TestClient(create_app(root))
    _assert_env_error_response_and_logs(client, caplog, "nearest.parquet", "ArrowInvalid")


def test_environment_failure_unexpected_schema(tmp_path, caplog):
    caplog.set_level(logging.ERROR, logger="backend.catalog")
    root, env_dir = _stage_unified_env_fixture(tmp_path)
    pq.write_table(pa.table({"unexpected_col": [1, 2, 3]}), env_dir / "nearest.parquet")
    client = TestClient(create_app(root))
    _assert_env_error_response_and_logs(client, caplog, "nearest.parquet", "SchemaError")


def test_health_and_optional_spa_serving(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Poltergeist</title>", encoding="utf8")
    (dist / "assets" / "app.js").write_text("console.log('ok');", encoding="utf8")
    monkeypatch.setenv("POLTERGEIST_FRONTEND_DIST", str(dist))

    client = TestClient(create_app())
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    root_page = client.get("/")
    assert root_page.status_code == 200
    assert "Poltergeist" in root_page.text

    asset = client.get("/assets/app.js")
    assert asset.status_code == 200
    assert "ok" in asset.text

    unknown_api = client.get("/api/does-not-exist")
    assert unknown_api.status_code == 404
