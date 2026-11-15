# POLTERGEIST Duck FRF data foundation

For the GitHub data branch and portable loading instructions, see the [unified dataset handoff](HANDOFF.md). The paths below describe the extracted source archive.

The data collection covers the June and October 2026 Duck events and nearby Sentinel acquisitions. The unit of temporal indexing is an **individual acquisition**. The June and October group labels identify observation groups whose acquisitions can be hours or days apart. Each acquisition has its own UTC, reference acquisition and signed offset from the reference.

## Open the data

| File | Contents |
|---|---|
| `data/unified/duck_observations.nc` | CF-style NetCDF with acquisition, northing and easting dimensions, CRS, masks and physical units |
| `data/unified/duck_pixels.parquet` | The same values for the 1,450 grid cells intersecting the study footprint, keyed by acquisition, row and column |
| `data/unified/{june,october,additional}/` | Multiband GeoTIFFs, organized by acquisition group, with named and unit-tagged bands |
| `data/unified/observation_groups.json` | Zero-based acquisition indices for the NetCDF group selections |
| `data/unified/cross_date.{nc,tif}` and `cross_date_pixels.parquet` | October-minus-June layers with per-variable and joint overlap masks |
| `data/unified/cross_date_pairs.json` | The exact endpoint IDs, UTC timestamps, elapsed seconds and valid cell counts for each sensor pair |
| `data/unified/environment/` | Time series, acquisition joins, antecedent features, predicted tide stage and environmental contrasts |
| `data/unified/acquisition_manifest.json` | Source IDs, exact UTC, orbit and calibration metadata, status, alignment and layer paths |
| `data/unified/{geospatial_qa,verification,source_checksums}.json` | Machine-readable quality and integrity checks |
| `data/source_handoff/` | Unaltered verified NISAR and LiDAR snapshots, including native rasters, radar geometry, LiDAR profiles and the upstream contract |
| `data/raw/` | Public catalogue responses, native Sentinel windows, XML calibration metadata and the original or source-native environmental records |

```python
import json
from pathlib import Path
import pandas as pd
import xarray as xr

root = Path("data/unified")
ds = xr.open_dataset(root / "duck_observations.nc")
groups = json.loads((root / "observation_groups.json").read_text())
june = ds.isel(observation=groups["june"])
october = ds.isel(observation=groups["october"])
changes = xr.open_dataset(root / "cross_date.nc")
conditions = pd.read_parquet(root / "environment/nearest.parquet")
```

See [Schema and variable definitions](SCHEMA.md) and the [QA report](QA.md). Use observation IDs to join station features. Station measurements are point observations and retain station positions, timestamps and quality flags.

## Reproduce the outputs

The working environment used Python 3.12. Run from this directory. The included raw caches and handoff support a rebuild offline. To build a new output directory while preserving a delivered version, set `--output` to a fresh path for both builders and the verifier.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
comparison=data/source_handoff/data/processed/comparison-20261115T110433284883
lidar=data/source_handoff/data/processed/lidar-20261115T110225129264
.venv/bin/python build_geospatial.py --comparison "$comparison" --lidar "$lidar"
.venv/bin/python build_environment.py
.venv/bin/python validate_collection.py
```

The acquisition commands below use the public archive APIs. They preserve real acquisition UTC and native raster posting. Planetary Computer uses temporary Azure container access tokens. Supply a Planetary Computer subscription key through `PC_SDK_SUBSCRIPTION_KEY` if required by the archive. The scripts keep tokens in memory. Archive snapshots and rolling NDBC records may change with the retrieval date.

```sh
.venv/bin/python discover.py
.venv/bin/python acquire_satellite.py --comparison-manifest "$comparison/manifest.json"
.venv/bin/python acquire_environment.py
```

The verified NISAR/LiDAR snapshot is an upstream input. To update it, supply both processed directories with the upstream version-1 manifests, exact acquisition records and file checksums. The builder requires their LiDAR acquisition records to agree. It uses the reference affine and LiDAR support directly. The original ZIP can be unpacked into `data/source_handoff` to restore those directories.

## Source credit

Contains modified Copernicus Sentinel data 2026. Sentinel assets and catalogue metadata were accessed via Microsoft Planetary Computer and Element 84 Earth Search. NISAR GCOV source data are provided by NASA and the Alaska Satellite Facility DAAC. Coastal measurements are provided by the USACE Field Research Facility, Coastal Observations and Analysis Branch, and NOAA CO-OPS and NDBC. The upstream LiDAR manifest includes USACE scholarly-use and commercial-use terms.
