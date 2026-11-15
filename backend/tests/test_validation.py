import sys
from pathlib import Path
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from metadata import read_nisar_metadata
from audit_inputs import audit


def metadata(tmp_path, **changes):
    row = dict(date_key='2026-06', granule='NISAR_20260630T235334_example', begin_utc='2026-06-30T23:53:34Z',pixel_m_x=10,pixel_m_y=10)
    row.update(changes)
    path = tmp_path/'metadata.csv'
    pd.DataFrame([row]).to_csv(path,index=False)
    return path


def test_normalizes_legacy_without_relabeling_identity(tmp_path):
    p=metadata(tmp_path)
    df=pd.read_csv(p).rename(columns={'granule':'granule_ur'})
    df['concept_id']='G123-ASF';df.to_csv(p,index=False)
    result=read_nisar_metadata(p)
    assert result.granule.iloc[0]=='NISAR_20260630T235334_example'
    assert result.concept_id.iloc[0]=='G123-ASF'


@pytest.mark.parametrize('changes',[
    {'begin_utc':'2026-06-18T23:53:34Z'}, {'begin_utc':'2026-06-30T23:53:34'},
    {'pixel_m_x':0}, {'pixel_m_y':float('inf')}, {'granule':None}])
def test_incompatible_metadata_is_rejected(tmp_path,changes):
    with pytest.raises(ValueError):read_nisar_metadata(metadata(tmp_path,**changes))


def test_duplicate_epoch_and_missing_columns_fail_clearly(tmp_path):
    p=metadata(tmp_path);df=pd.read_csv(p);pd.concat([df,df]).to_csv(p,index=False)
    with pytest.raises(ValueError,match='duplicate'):read_nisar_metadata(p)
    df.drop(columns='pixel_m_y').to_csv(p,index=False)
    with pytest.raises(ValueError,match='missing'):read_nisar_metadata(p)


def test_missing_inputs_report_failure_and_do_not_create_measurements(tmp_path):
    result=audit(tmp_path)
    assert sum(r['status']=='FAIL' for r in result)==6
    assert result[-1]['status']=='PENDING'


def test_one_epoch_cannot_support_an_all_date_scientific_claim():
    from make_report import tag_feature_match, tag_better
    matrix=pd.DataFrame([dict(date=d,product='NISAR_HH',lidar_boundary='B2_dunetoe',RMSE_m=3,pixel_m=10) for d in ['2026-06','pooled']])
    assert tag_feature_match(matrix,'NISAR_HH','B2_dunetoe')[0] != 'SUPPORTED'
    comparison=pd.DataFrame([dict(date=d,product=p,lidar_boundary='B2_dunetoe',RMSE_m=m,RMSE_lo=m-.1,RMSE_hi=m+.1) for d in ['2026-06','pooled'] for p,m in [('a',1),('b',4)]])
    assert tag_better(comparison,'a','b','B2_dunetoe')[0] != 'SUPPORTED'


def test_configurable_nisar_reader_transforms_window_before_selection(tmp_path, monkeypatch):
    import h5py
    import numpy as np
    import xarray as xr
    from pyproj import Transformer
    import nisar
    bounds=Transformer.from_crs(32618,3857,always_xy=True).transform_bounds(*nisar.utm_window(),densify_pts=21)
    source=tmp_path/(nisar.GRANULE+'.h5')
    with h5py.File(source,'w') as f:
        g=f.create_group('science/LSAR/GCOV/grids/frequencyA')
        g['projection']=3857
        g['xCoordinates']=np.linspace(bounds[0]-50,bounds[2]+50,60)
        g['yCoordinates']=np.linspace(bounds[3]+50,bounds[1]-50,60)
        g['HHHH']=np.ones((60,60));g['HVHV']=np.full((60,60),.1)
    output=tmp_path/'processed'
    monkeypatch.setattr(sys,'argv',['nisar.py','--input',str(source),'--output-dir',str(output)])
    nisar.main()
    with xr.open_dataset(output/'nisar_profiles.nc') as ds:
        assert ds.sizes['date']==1 and ds.sizes['y']==50
        assert np.isfinite(ds.HH.values).any()
        assert np.nanmax(abs(ds.HH.values)) < 1e-6
        assert np.nanmax(abs(ds.HV.values+10)) < 1e-6
    meta=read_nisar_metadata(output/'nisar_meta.csv')
    assert meta.epsg.iloc[0]==3857
    assert meta.granule.iloc[0]==nisar.GRANULE
