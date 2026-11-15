from fastapi.testclient import TestClient
from backend.app import create_app
from backend.science import number, Science


def test_superseded_boundary_endpoint_does_not_serve_old_results():
    client=TestClient(create_app())
    assert client.get('/api/boundary-analysis/FRF-950').json()['status']=='unavailable'
    assert client.get('/api/boundary-analysis/unknown').status_code==404
    result=client.get('/api/analysis/FRF-950').json()
    assert 'coastal_observations' in result
    assert result['coastal_observations']['waterlines'][0]['acquired_at'].startswith('2026-06-18')


def test_missing_legacy_files_do_not_invent_outputs(tmp_path):
    assert Science(tmp_path).analysis({'properties':{'id':'none','frf_y_m':950}})['status']=='unavailable'
    assert all(number(v) is None for v in ['nan','inf',''])
