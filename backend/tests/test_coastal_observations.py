from math import hypot

from fastapi.testclient import TestClient
import numpy as np
import pytest

from backend.app import app, create_app
from backend.coastal_observations import X, crossing, paired_lidar
from backend.coastal_physics import MHW, NOAA_STATION, correct_waterline, wave_geometry

CLIENT = TestClient(app)
DATE = "2026-10-16T16:03:03Z"
TIDE = {
    "station_id": NOAA_STATION, "variable": "water_level", "value": 1.226, "unit": "m",
    "vertical_datum": "MLLW", "timestamp_utc": "2026-10-16T16:06:00Z", "tolerance_minutes": 12,
    "source_quality_json": '{"q":"v","f":"0,0,0,0"}',
}
SLOPE = {"slope_m_per_m": 0.1, "units": "m/m", "coreg_qc_flag": 1, "acquired_at": "2026-10-10T00:00:00Z",
         "slope_p10_p90_m_per_m": [0.05, 0.2]}


def test_frf_sign_and_duck_datum():
    result = correct_waterline(90, DATE, TIDE, MHW, SLOPE)
    assert result["x_frf_m"] == pytest.approx(92)
    assert result["sigma_m"] is None
    assert result["slope_sensitivity_frf_m"] == pytest.approx([91, 94])
    lower_tide = {**TIDE, "value": 0.826}
    assert correct_waterline(90, DATE, lower_tide, MHW, SLOPE)["x_frf_m"] == pytest.approx(88)
    same_datum = {**MHW, "vertical_datum": "MLLW", "value": 1.026}
    assert correct_waterline(90, DATE, TIDE, same_datum, SLOPE)["x_frf_m"] == pytest.approx(92)


@pytest.mark.parametrize("tide,reference,slope", [
    ({**TIDE, "vertical_datum": "MSL"}, MHW, SLOPE),
    ({**TIDE, "timestamp_utc": "2026-10-16T18:01:00Z"}, MHW, SLOPE),
    ({**TIDE, "timestamp_utc": "2026-10-16T16:03:03"}, MHW, SLOPE),
    ({**TIDE, "source_quality_json": '{"q":"p","f":"0,1,0,0"}'}, MHW, SLOPE),
    ({**TIDE, "variable": "tide_prediction"}, MHW, SLOPE),
    ({**TIDE, "value": np.nan}, MHW, SLOPE),
    (TIDE, {**MHW, "station_id": "Other station"}, SLOPE),
    (TIDE, {**MHW, "unit": "ft"}, SLOPE),
    (TIDE, MHW, {**SLOPE, "slope_m_per_m": 0.0}),
    (TIDE, MHW, {**SLOPE, "units": "degrees"}),
    (TIDE, MHW, {**SLOPE, "acquired_at": DATE}),
])
def test_withholding_invalid_physical_inputs(tide, reference, slope):
    result = correct_waterline(90, DATE, tide, reference, slope)
    assert result["status"] == "withheld"
    assert result["x_frf_m"] is None
    assert result["reasons"]


def test_uncertainty_and_experimental_mean_setup():
    errors = {"extract_m": 1, "tide_m": 0.03, "slope_m_per_m": 0.02, "registration_m": 0.5}
    tide = correct_waterline(90, DATE, TIDE, MHW, SLOPE, errors=errors)
    assert tide["sigma_m"] == pytest.approx(hypot(1, 0.3, 0.4, 0.5))
    wave = wave_geometry(0.6, 6, 71.8)
    result = correct_waterline(90, DATE, TIDE, MHW, SLOPE, wave=wave)
    assert result["setup_m"] > 0
    assert result["x_frf_m"] == pytest.approx(tide["x_frf_m"] + result["setup_m"] / 0.1)
    assert correct_waterline(90, DATE, TIDE, MHW, SLOPE, wave=wave, reference_wave=wave)["setup_m"] == 0
    assert wave_geometry(0.6, 6, 251.8) is None


def test_optical_crossing_respects_mask_support():
    values = (X - 85.5) / 100
    assert crossing(values, 0, 20) == pytest.approx(85.5)
    bad = values.copy()
    bad[(X >= 85) & (X <= 87)] = np.nan
    assert crossing(bad, 0, 20) is None
    bad = values.copy()
    bad[(X > 95) & (X < 112)] = -0.3
    bad[X > 115] = 0.6
    # The first crossing cannot satisfy 20 m of connected wet support.
    assert crossing(bad, 0, 20) > 110


def test_live_contracts_reproduce_matched_observations_without_relabeling():
    evidence = CLIENT.get("/api/coastal/observations?include_samples=true").json()
    radar = evidence["radar_disagreement"]
    assert radar["status"] == "conditional"
    assert radar["strict_overlap_cells"] == 168
    assert radar["opposite_strict_cells"] == 76
    assert radar["matched_radar_cells"] == 1310
    assert radar["opposite_radar_cells"] == 671
    assert radar["noise_thresholds_db"] is None
    assert radar["s1_minus_nisar_seconds"]["june"] == pytest.approx(1033427.97665)
    assert abs(radar["s1_minus_nisar_seconds"]["october"]) < 3600
    layer = CLIENT.get("/api/boundaries/radar-disagreement.geojson").json()
    assert sum(f["properties"]["strict_overlap"] for f in layer["features"]) == 76
    assert all(f["properties"]["hh_change_db"] * f["properties"]["vv_change_db"] < 0 for f in layer["features"])

    targets = evidence["validation"]["targets"]
    for target in targets.values():
        for metric, methods in (("raw_vs_tide", ("raw", "tide")), ("raw_vs_tide_vs_setup", ("raw", "tide", "setup"))):
            rows = [row for row in target["samples"] if all(k in row for k in methods)]
            assert target[metric]["n"] == len(rows)
            for method in methods:
                error = np.array([r[method] - r["reference"] for r in rows])
                actual = target[metric]["methods"][method]
                assert actual["rmse_m"] == pytest.approx(np.sqrt(np.mean(error**2)))
                assert actual["mae_m"] == pytest.approx(np.mean(abs(error)))
                assert actual["bias_m"] == pytest.approx(np.mean(error))
    fixed = targets["fixed_mhw_contour"]
    assert fixed["raw_vs_tide"]["n"] == 36
    assert list(fixed["by_date"]) == ["2026-10"]
    assert fixed["raw_vs_tide"]["methods"]["tide"]["rmse_m"] == pytest.approx(3.72829506)
    assert evidence["terrain"]["native_paired_cells"] == 17466

    analysis = CLIENT.get("/api/analysis/FRF-950").json()["coastal_observations"]
    june = analysis["waterlines"][0]
    assert june["acquired_at"].startswith("2026-06-18T16:03:02")
    assert june["tide"]["shift_m"] == pytest.approx((1.075 - 1.026) / 0.1333091)
    assert june["tide"]["slope"]["acquired_at"].startswith("2026-06-15")
    assert june["tide"]["sigma_m"] is None
    transect = CLIENT.get("/api/transects/FRF-950").json()
    assert transect["measured_change"]["status"] == "supported"
    change = transect["measured_change"]["change_profile"]
    assert change == analysis["terrain"]["change_profile"]
    assert change[0]["dz_m"] == pytest.approx(7.966601 - 7.962424)
    for name in ("ndwi", "mndwi", "tide", "setup"):
        feature = CLIENT.get(f"/api/boundaries/physics-s2-{name}-june.geojson").json()["features"][0]
        assert feature["properties"]["acquisition_id"] == june["acquisition_id"]
        assert feature["properties"]["processing_version"] == evidence["processing_version"]


def test_missing_bundles_report_withheld(tmp_path):
    client = TestClient(create_app(tmp_path))
    result = client.get("/api/coastal/observations").json()
    assert result["status"] == result["terrain"]["status"] == result["radar_disagreement"]["status"] == "withheld"
    assert result["terrain"]["reasons"]
    assert client.get("/api/boundaries/physics-s2-tide-june.geojson").status_code == 404
    assert paired_lidar(tmp_path, {})["status"] == "withheld"
