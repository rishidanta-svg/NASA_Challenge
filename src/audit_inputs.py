"""Offline integrity, schema and spatial-support audit of delivered inputs."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import rasterio
import xarray as xr
from metadata import read_nisar_metadata

ROOT = Path(__file__).resolve().parents[1]


def audit(root=ROOT):
    checks = []
    def record(name, status, detail):
        checks.append(dict(check=name, status=status, detail=detail))
    for stem, variables in [('s1', ['VV','VH']), ('s2', ['NDWI','MNDWI']), ('nisar', ['HH','HV'])]:
        try:
            meta_path = root / f'data/processed/{stem}_meta.csv'
            meta = read_nisar_metadata(meta_path) if stem == 'nisar' else pd.read_csv(meta_path)
            required = {'date_key', 'acquisition_utc', 'item_id'} if stem != 'nisar' else {'date_key', 'begin_utc', 'granule'}
            if not required.issubset(meta) or meta[list(required)].isna().any().any() or meta.date_key.duplicated().any():
                raise ValueError('missing/empty metadata columns or duplicate epoch')
            with xr.open_dataset(root / f'data/processed/{stem}_profiles.nc') as ds:
                if set(ds.date.values) != set(meta.date_key):
                    raise ValueError('NetCDF and metadata analysis epochs differ')
                for var in variables:
                    if var not in ds or set(ds[var].dims) != {'date','y','x'}:
                        raise ValueError(f'missing variable or incompatible dimensions: {var}')
                    if not np.isfinite(ds[var].values).any():
                        raise ValueError(f'no finite data: {var}')
                for coord in ['x','y']:
                    if not np.all(np.diff(ds[coord].values) > 0):
                        raise ValueError(f'{coord} must increase strictly')
            record(stem + ' metadata/profile schema', 'PASS', 'IDs, date keys, variables and coordinates are compatible')
        except Exception as exc:
            record(stem + ' metadata/profile schema', 'FAIL', str(exc))
    for bundle in ['lidar','comparison']:
        try:
            directory = root / 'data/processed/verified' / bundle
            manifest = json.loads((directory/'manifest.json').read_text())
            for item in manifest['files']:
                path = directory/item['filename']
                if not path.is_file() or path.stat().st_size != item['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
                    raise ValueError(f'asset missing or checksum differs: {path.name}')
                if path.suffix == '.tif':
                    with rasterio.open(path) as raster:
                        if raster.crs is None or not raster.crs.is_projected or raster.transform.determinant == 0:
                            raise ValueError(f'invalid projected raster geometry: {path.name}')
            record(bundle + ' bundle integrity/CRS', 'PASS', f"{len(manifest['files'])} assets match manifests; projected raster geometry valid")
        except Exception as exc:
            record(bundle + ' bundle integrity/CRS', 'FAIL', str(exc))
    try:
        with xr.open_dataset(root/'data/processed/lidar_scans.nc') as ds:
            if 'NAVD88' not in ds.attrs.get('vertical_datum',''):
                raise ValueError('LiDAR vertical datum missing or incompatible')
            delta = ds.elevation.sel(date='2026-10') - ds.elevation.sel(date='2026-06')
            native = root/'data/processed/verified/lidar/lidar_delta_z_native.tif'
            with rasterio.open(native) as raster:
                b = raster.read(1,masked=True).filled(np.nan)
                a = delta.sel(yFRF=slice(700,1190)).values[::-1]
                if a.shape != b.shape:
                    raise ValueError('native raster and shared FRF grid dimensions differ')
                joint = np.isfinite(a) & np.isfinite(b)
                error = float(np.max(np.abs(a[joint]-b[joint])))
                if error > 1e-6:
                    raise ValueError(f'joint native elevation differences disagree by {error} m')
                detail = {'main_full_cells': int(np.isfinite(delta).sum()), 'main_full_median_m': float(np.nanmedian(delta)),
                          'main_shared_cells': int(np.isfinite(a).sum()), 'map_native_cells': int(np.isfinite(b).sum()),
                          'map_native_median_m':float(np.nanmedian(b)), 'mask_disagreements_shared_grid':int(np.sum(np.isfinite(a)!=np.isfinite(b))),
                          'joint_max_difference_m':error,
                          'support': 'main y=700..1199; map native y=700..1190, reversed row order; masks retained separately'}
                record('LiDAR common-support/datum audit','PASS',detail)
    except Exception as exc:
        record('LiDAR common-support/datum audit','FAIL',str(exc))
    record('Physics collection delivery', 'PENDING' if not (root/'physics-data-foundation/data/duck_observations.nc').is_file() else 'NOT VERIFIED',
           'Generated physics collection requires separate delivery and validation; scripts/QA prose do not establish data availability')
    return checks


if __name__ == '__main__':
    checks = audit()
    target = ROOT/'outputs/input_audit.json'
    target.write_text(json.dumps({'checks':checks},indent=2)+'\n')
    for row in checks:
        print(f"[{row['status']}] {row['check']}: {row['detail']}")
    raise SystemExit(1 if any(c['status']=='FAIL' for c in checks) else 0)
