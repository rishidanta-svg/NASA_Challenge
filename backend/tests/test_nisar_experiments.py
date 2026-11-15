from fastapi.testclient import TestClient
import numpy as np
import pytest

from backend.app import app, create_app
from backend.nisar_ablation import BUFFER_M, MODELS, heldout_predictions, strip_splits
from backend.nisar_shoreline import connected_offshore, despeckle

CLIENT = TestClient(app)


def test_speckle_filter_keeps_invalid_pixels_and_disconnected_dark_land():
    values = np.full((7, 7), -15.0)
    valid = np.ones(values.shape, dtype=bool)
    values[3, 3] = 15
    valid[4, 4] = False
    filtered = despeckle(values, valid)
    assert filtered[3, 3] == -15
    assert np.isnan(filtered[4, 4])
    dark = np.zeros((6, 6), dtype=bool)
    dark[:, 4:] = True
    dark[1:3, 1] = True
    seeds = np.indices(dark.shape)[1] == 5
    assert np.array_equal(connected_offshore(dark, seeds), np.indices(dark.shape)[1] >= 4)


def test_block_guard_and_tuning_exclude_heldout_labels():
    rng = np.random.default_rng(325)
    y = np.arange(705.0, 1200.0, 10)
    z = rng.normal(size=len(y))
    matrices = {key: rng.normal(size=(len(y), len(names))) for key, names in MODELS.items()}
    for start, end, train, test in strip_splits(y):
        assert not np.any(train & test)
        assert np.all((y[test] >= start) & (y[test] < end))
        assert np.min(np.abs(y[train, None] - y[test])) >= BUFFER_M
    predictions, logs = heldout_predictions(matrices, z, y)
    changed = z.copy()
    middle = (y >= 900) & (y < 1000)
    changed[middle] += 1000
    repeated, changed_logs = heldout_predictions(matrices, changed, y)
    for name in predictions:
        assert np.array_equal(predictions[name][middle], repeated[name][middle])
    assert logs[2]["selected_alpha"] == changed_logs[2]["selected_alpha"]


def test_real_hh_candidates_are_exposed_as_exploratory_without_shoreline_skill():
    data = CLIENT.get("/api/coastal/nisar?include_samples=true").json()
    assert data["input_qa"]["status"] == "supported"
    assert data["input_qa"]["shared_valid_cells"] == {"hh": 1310, "hv": 1310}
    assert data["input_qa"]["unlabeled_features"]["delta_hh_minus_hv_db"]["n"] == 1310
    old = CLIENT.get("/api/coastal/observations").json()
    assert old["radar_disagreement"]["opposite_strict_cells"] == 76
    optical = old["validation"]["targets"]["fixed_mhw_contour"]["raw_vs_tide"]["methods"]
    assert optical["raw"]["rmse_m"] == pytest.approx(7.41573046)
    assert optical["tide"]["rmse_m"] == pytest.approx(3.72829506)
    index = {d["id"]: d for d in CLIENT.get("/api/layers").json()}
    for epoch, candidates, tolerance_rows, residual in (("june", 39, 2, -39.9452433), ("october", 37, 1, -37.7597761)):
        actual = data["shoreline"]["epochs"][epoch]
        assert len(actual["rows"]) == 50
        assert actual["candidate_rows"] == candidates
        assert actual["rejected_rows"] + candidates == 50
        assert actual["track"] == 69 and actual["frame"] == 70
        assert actual["status"] == "exploratory"
        comp = actual["comparability"]
        assert comp["status"] == "failed"
        assert comp["within_band_rows"] == tolerance_rows
        assert comp["median_candidate_minus_expected_m"] == pytest.approx(residual)
        assert actual["validation"]["fixed_mhw_contour"]["status"] == "withheld"
        assert actual["validation"]["fixed_mhw_contour"]["n"] == 0
        assert actual["validation"]["fixed_mhw_contour"]["methods"] is None
        layer_id = f"nisar-hh-land-water-candidate-{epoch}"
        layer = CLIENT.get(index[layer_id]["url"]).json()
        assert all(f["properties"]["acquisition_id"] == actual["id"] for f in layer["features"])
        assert index[layer_id]["qa"]["waterline_status"] == "failed"
        assert layer["properties"]["status"] == "exploratory"
        assert sum(len(f["geometry"]["coordinates"]) if f["geometry"]["type"] == "LineString" else 1
                   for f in layer["features"]) == candidates
    october = data["shoreline"]["epochs"]["october"]["validation"]["fixed_mhw_contour"]
    assert october["reference_rows"] == 36
    assert october["candidate_overlap_rows"] == 27
    assert october["nisar_minus_reference_seconds"] == pytest.approx(1244.999667)
    assert "rows" not in CLIENT.get("/api/coastal/nisar").json()["shoreline"]["epochs"]["october"]


def test_real_ablation_metrics_are_recomputable_on_identical_cells():
    result = CLIENT.get("/api/coastal/nisar?include_samples=true").json()["terrain_ablation"]
    rows = result["samples"]
    assert result["n"] == len(rows) == 168
    assert len({(r["row"], r["column"]) for r in rows}) == 168
    assert result["classification"]["lod95_m"] is None
    assert result["classification"]["negative_observed_cells"] == 148
    assert result["classification"]["positive_observed_cells"] == 20
    assert result["terrain_model_deployment"]["status"] == "withheld"
    assert sum(r["n"] for r in result["per_strip"]) == 168
    assert len(result["per_strip"]) == 5
    for model, metric in result["metrics"].items():
        error = np.array([r["predictions_m"][model] - r["measured_change_m"] for r in rows])
        assert metric["rmse_m"] == pytest.approx(np.sqrt(np.mean(error ** 2)))
        assert metric["mae_m"] == pytest.approx(np.mean(abs(error)))
        assert metric["bias_m"] == pytest.approx(np.mean(error))
    assert result["ablation"]["C_minus_B_rmse_m"] == pytest.approx(0.00329268785)
    assert result["ablation"]["strips_with_lower_rmse_for_C"] == 1


def test_missing_nisar_experiments_leave_base_contract_available(tmp_path):
    client = TestClient(create_app(tmp_path))
    assert client.get("/api/study-area").status_code == 200
    data = client.get("/api/coastal/nisar").json()
    assert data["input_qa"]["status"] == data["shoreline"]["status"] == data["terrain_ablation"]["status"] == "withheld"
    assert data["shoreline"]["layer_ids"] == []
