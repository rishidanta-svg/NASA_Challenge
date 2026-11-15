import csv
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.science import number

CLIENT = TestClient(create_app())


def test_boundary_positions_are_not_elevations_and_times_are_not_month_labels():
    response = CLIENT.get('/api/boundary-analysis/FRF-950')
    assert response.status_code == 200
    data = response.json()
    assert data['quantity'] == 'cross-shore boundary position'
    assert 'points' not in data
    assert len(data['records']) == 6
    june = next(r for r in data['records'] if r['epoch'] == '2026-06' and r['feature'] == 'dunetoe')
    nisar = next(o for o in june['observations'] if o['product'] == 'NISAR_HH')
    assert nisar['acquired_at'] == '2026-06-30T23:53:34Z'
    assert abs(nisar['lidar_offset_hours'] - 287.3753) < .001
    assert len(data['validation']) == 3
    assert CLIENT.get('/api/analysis/FRF-950').json()['status'] == 'unavailable'
    assert CLIENT.get('/api/boundary-analysis/unknown').status_code == 404


def test_missing_files_and_unmatched_rows_do_not_invent_results(tmp_path):
    client = TestClient(create_app(science_root=tmp_path))
    assert client.get('/api/boundary-analysis/FRF-950').json()['status'] == 'unavailable'
    assert number('nan') is None and number('inf') is None and number('') is None


def test_ambiguous_estimates_are_withheld_and_source_values_preserved():
    from backend.app import ROOT
    from backend.science import Science
    science = Science(ROOT)
    row = next(r for r in science.states if r['dunetoe_status'].startswith('ambiguous'))
    result = science.analysis({'properties': {'id': 'test', 'frf_y_m': float(row['y'])}})
    dune = next(r for r in result['records'] if r['epoch'] == row['date'] and r['feature'] == 'dunetoe')
    assert dune['x_frf_m'] is None
    assert dune['interval90_frf_m'] is None
    assert dune['status'].startswith('ambiguous')
    water = next(r for r in result['records'] if r['epoch'] == row['date'] and r['feature'] == 'waterline')
    assert water['x_frf_m'] == float(row['waterline_x_m'])
