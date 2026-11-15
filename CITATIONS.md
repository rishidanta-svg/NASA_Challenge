# Data citations

All data accessed 2026-11-15. All times UTC.

| Dataset | Product / granule ID | Acquisition (UTC) | URL |
|---|---|---|---|
| USACE FRF dune lidar DEM (duneLidarDEM, hourly) | FRF-geomorphology_DEMs_duneLidarDEM_202606.nc, coregQCFlag 1 | 2026-06-19T00:31:03 | https://chldata.erdc.dren.mil/thredds/dodsC/frf/geomorphology/DEMs/duneLidarDEM/2026/FRF-geomorphology_DEMs_duneLidarDEM_202606.nc |
| USACE FRF dune lidar DEM (duneLidarDEM, hourly) | FRF-geomorphology_DEMs_duneLidarDEM_202609.nc, coregQCFlag 1 | 2026-09-29T10:33:03 | https://chldata.erdc.dren.mil/thredds/dodsC/frf/geomorphology/DEMs/duneLidarDEM/2026/FRF-geomorphology_DEMs_duneLidarDEM_202609.nc |
| USACE FRF dune lidar DEM (duneLidarDEM, hourly) | FRF-geomorphology_DEMs_duneLidarDEM_202610.nc, coregQCFlag 1 | 2026-10-16T23:33:04 | https://chldata.erdc.dren.mil/thredds/dodsC/frf/geomorphology/DEMs/duneLidarDEM/2026/FRF-geomorphology_DEMs_duneLidarDEM_202610.nc |
| NASA-ISRO NISAR L2 GCOV, HH/HV | NISAR_L2_PR_GCOV_024_069_D_070_4005_DHDH_A_20260630T235334_20260630T235409_P05023_N_F_J_001 | 2026-06-30T23:53:34Z to end not recorded | source URL not recorded; local HDF5 input |
| Copernicus Sentinel-1 RTC (Microsoft Planetary Computer), VV/VH, relative orbit 106 ascending | S1A_IW_GRDH_1SDV_20260623T225806_20260623T225835_065103_0834CA_rtc | 2026-06-23T22:58:20.739610Z | https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-1-rtc/items/S1A_IW_GRDH_1SDV_20260623T225806_20260623T225835_065103_0834CA_rtc |
| Copernicus Sentinel-1 RTC (Microsoft Planetary Computer), VV/VH, relative orbit 106 ascending | S1D_IW_GRDH_1SDV_20261004T225729_20261004T225759_004872_009297_rtc | 2026-10-04T22:57:44.438136Z | https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-1-rtc/items/S1D_IW_GRDH_1SDV_20261004T225729_20261004T225759_004872_009297_rtc |
| Copernicus Sentinel-1 RTC (Microsoft Planetary Computer), VV/VH, relative orbit 106 ascending | S1D_IW_GRDH_1SDV_20261016T225729_20261016T225759_005047_0098AC_rtc | 2026-10-16T22:57:44.383059Z | https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-1-rtc/items/S1D_IW_GRDH_1SDV_20261016T225729_20261016T225759_005047_0098AC_rtc |
| Copernicus Sentinel-2 L2A (Earth Search on AWS), processing offset applied: True | S2C_18SVF_20260618_0_L2A | 2026-06-18T16:03:02.616000Z | https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a/items/S2C_18SVF_20260618_0_L2A |
| Copernicus Sentinel-2 L2A (Earth Search on AWS), processing offset applied: True | S2B_18SVF_20260928_0_L2A | 2026-09-28T15:53:06.776000Z | https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a/items/S2B_18SVF_20260928_0_L2A |
| Copernicus Sentinel-2 L2A (Earth Search on AWS), processing offset applied: True | S2C_18SVF_20261016_0_L2A | 2026-10-16T16:03:03.679000Z | https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a/items/S2C_18SVF_20261016_0_L2A |
| NOAA CO-OPS water level, station 8651370 Duck NC (6-min, NAVD88, metric) | product=water_level | 2026-06-18/19, 2026-09-28/29, 2026-10-16/17 | https://api.tidesandcurrents.noaa.gov/api/prod/datagetter |
| NOAA CO-OPS tidal datums, station 8651370 (epoch 1983-2001) | MHW, NAVD88 | n/a | https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/8651370/datums.json |

Contains modified Copernicus Sentinel data (2026). Lidar courtesy of the USACE Field Research Facility, Duck NC.
Lidar QC definitions (coregQCFlag 1: plane-matching co-registration, RMS reflector error < 0.1 m, assessment-plane offsets < 0.1 m) are from the FRF file metadata.
AI use: analysis code was written with assistance from Claude (Anthropic) and must be reviewed and understood by the team.
