# Duck data quality report

**Release date** 15 November 2026

**Status** June and October source data assembled and verified on the shared grid. The collection has 28 acquisitions, including 19 additional Sentinel acquisitions.

## Acquisition and timing

UTC timestamps below are rounded to the nearest second for display. The NetCDF and provenance manifest retain source precision. Offsets are relative to the corresponding NISAR granule midpoint.

| Group and sensor | Acquisition UTC | Offset | Geometry or quality |
|---|---|---:|---|
| June Sentinel-1A | June 16 23:06:17 | −48 h 47 min 36 s | Ascending track 4. RTC VV/VH. Scene incidence 30.69°–46.04°. |
| June Sentinel-2C | June 18 16:03:03 | −7 h 50 min 50 s | MGRS 18SVF, descending track 54. Tile cloud 56.66%. Study grid cloud 0.55%, 8 of 1,450 cells. |
| June NISAR | June 18 23:53:52 | Reference | Descending track 069, frame 070. Frequency A HH/HV. |
| June USACE LiDAR | June 19 00:31:04 | +37 min 12 s | Scan QC 1. Index 111. |
| June Sentinel-1D | June 30 22:57:40 | +11 d 23 h 3 min 48 s | Ascending track 106. RTC VV/VH. Scene incidence 30.69°–45.99°. |
| October Sentinel-2C | October 16 16:03:04 | −7 h 50 min 45 s | MGRS 18SVF, descending track 54. Tile cloud 3.98%. Zero SCL cloud or cloud-shadow cells over the study grid. |
| October Sentinel-1D | October 16 22:57:44 | −56 min 5 s | Ascending track 106. RTC VV/VH. Scene incidence 30.69°–46.00°. |
| October USACE LiDAR | October 16 23:33:04 | −20 min 45 s | Scan QC 1. Index 362. |
| October NISAR | October 16 23:53:49 | Reference | Descending track 069, frame 070. Frequency A HH/HV. |

The repeat Sentinel-1 pair is June 30 and October 16, 108.00005 days apart. Both use Sentinel-1D and ascending track 106. June 16 is the closer radar pass to the June NISAR scene and is included as an individual observation. The June 23 track-106 Sentinel-1A pass and June 28 track-4 Sentinel-1A pass are additional observations. The September 27 track-4 pass and cloud-screened September 28, October 1 and October 13 optical scenes provide intermediate context. Heavily clouded optical acquisitions retain native data and masks. The selected discovery windows were June 11–30, September 25–October 2 and October 12–20. The catalogs also list a June 11 GRD pass and a 30 m OPERA RTC burst. Its VV/VH assets redirected to Earthdata Login and remain catalogue records in this package.

The June and October optical products are `S2C_MSIL2A_20260618T154811_N0512_R054_T18SVF_20260618T205116.SAFE` and `S2C_MSIL2A_20261016T155241_N0513_R054_T18SVF_20261016T193412.SAFE`. Environmental matching uses the producer tile XML sensing time. Planetary Computer's optical STAC `datetime` corresponds to the datatake start for these records. Both timestamps and both catalog IDs are retained. [Planetary Computer Sentinel-2 product](https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a) · [Element 84 Earth Search](https://github.com/Element84/earth-search)

Sentinel-1 calibration uses Catalyst RTC gamma-zero linear power from Planetary Computer. The GRD records document parent acquisition geometry and archive alternatives. A GRD workflow would require Sentinel-1 orbit information, border/thermal noise processing, ESA radiometric calibration, terrain correction with a DEM and documented output geometry. The RTC source supplies scene near/far angles and nodata. A measured local incidence-angle raster and a separate layover/shadow code layer are unavailable in the chosen RTC assets. [Planetary Computer RTC methodology](https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-1-rtc) · [ASF OPERA RTC guide](https://hyp3-docs.asf.alaska.edu/guides/opera_rtc_product_guide/)

## Spatial checks and valid overlap

The 10 m comparison lattice is the verified NISAR grid. The GeoTIFF affine, EPSG code, pixel centers and WGS84 coordinates were checked. The 1,508-cell bounding raster contains 1,450 cells intersecting the study footprint. The handoff's NISAR eligibility is defined at cell centers, leaving 1,310 radar-eligible cells. Checked upstream files matched 84 file hashes across both handoff snapshots. Native Sentinel sample verification covered 95,892 aligned values. The pixel table contains 40,600 unique acquisition/cell rows.

| Cross-date quantity | Days between acquisitions | Joint valid cells |
|---|---:|---:|
| NISAR HH/HV backscatter change | 119.99996 | 1,310 per polarization |
| Sentinel-1 VV/VH backscatter change | 108.00005 | 1,450 per polarization |
| Sentinel-2 reflectance and indices | 120.00001 | 1,442 per band or index |
| Measured LiDAR elevation change | 119.95972 | 168 |
| All-sensor overlap | Separate sensor pair intervals | 168 |

The 168 measured change cells cover 11.59% of the intersecting footprint. An independent sample at E 432375 m, N 4004825 m reproduced the upstream LiDAR change of −0.215214 m. The upstream 1 m LiDAR retains 17,466 native paired cells and source NAVD88 (geoid12b). The upstream reflector RMS was 0.0975 m in June and 0.0754 m in October. The shared lattice and internal coordinate agreement establish numerical alignment. Physical co-registration error against independent control remains unmeasured. Reflectance and HH/HV or VV/VH scattering changes may also respond to water state, wet sand, foam, geometry and atmospheric or radiometric differences. [Upstream data contract](data/source_handoff/reports/duck_pipeline.md)

All six optical bands passed the second-catalog encoding check for the selected acquisitions wherever both providers delivered positive comparable values. Producer calibration preserves valid signed reflectance. SCL, SWIR and MNDWI retain 20 m source support when presented on the comparison grid. The SCL water class is an optical classification and contains mixed pixels near the shore. June and October EO, LiDAR and station observations remain indexed by their exact timestamps and matching offsets.

## Environmental checks

- Station 8651370 verified water level and FRF 17 m significant wave height match all 28 acquisition times within their stated tolerances. Around the June and October NISAR midpoints, respectively, water levels are 0.576 and 0.516 m MLLW, measured 7.5 s and 11.0 s later. FRF 17 m significant wave heights are 0.592 and 0.756 m, measured about six minutes later. Wave period/direction and station winds keep their individual time matches. [NOAA CO-OPS response fields](https://api.tidesandcurrents.noaa.gov/api/dev/responseHelp.html) · [USACE FRF 17 m archive](https://chldata.erdc.dren.mil/thredds/catalog/frf/oceanography/waves/waverider-17m/2026/catalog.html)
- Nearest qualifying rain readings exist for all 28 acquisitions. The conservative complete-bin totals are available for 28, 27, 26, 22 and 19 acquisitions in the nominal 1, 6, 24, 72 and 168-hour windows, respectively. Source intervals and QC are retained. [FRF rain archive](https://chldata.erdc.dren.mil/thredds/catalog/frf/meteorology/metGauges/rain/2026/catalog.html)
- FRF total water level records meet the 30-minute tolerance and QC gate for five acquisitions. The three primary-group matches are in June. October also has source observations within the archive, with gaps or quality exclusions around the target passes. The nearshore hydrodynamics source retains measured cross-shore profiles sampled at approximately 1 m with original flags. Those station values remain sparse at the acquisition times. Checked source values include 14,905 valid numeric nearshore wave-height samples across the three months. [FRF runup archive](https://chldata.erdc.dren.mil/thredds/catalog/frf/oceanography/waves/lidarWaveRunup/2026/catalog.html) · [FRF hydrodynamics archive](https://chldata.erdc.dren.mil/thredds/catalog/frf/oceanography/waves/lidarHydrodynamics/2026/catalog.html)

The observation tables preserve 290,341 station/value records and 694 qualifying acquisition/variable/station matches. They include NDBC archive and preliminary streams with provenance. The 17 m FRF and NDBC 44056 feeds share a buoy. Direct measurements of beach moisture, roughness and vegetation structure are unavailable. Environmental and satellite QA reports are in `data/unified`.
