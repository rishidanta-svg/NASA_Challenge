# Duck FRF June–October 2026 data pipeline

Run from the repository root on macOS or Linux with Python 3.9–3.12.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-geospatial.txt
.venv/bin/python scripts/run_duck_pipeline.py catalog
.venv/bin/python scripts/run_duck_pipeline.py lidar
.venv/bin/python scripts/run_duck_pipeline.py all
```

The catalog stage uses the exact pinned ASF and CMR records. The LiDAR stage needs public USACE OPeNDAP access on the first run and reuses its two timestamp-checked slices thereafter. For radar, set a valid `EARTHDATA_TOKEN` locally or configure `urs.earthdata.nasa.gov` in your local `.netrc` with Earthdata credentials and appropriate file permissions. The runner also recognizes `EARTHDATA_USERNAME` and `EARTHDATA_PASSWORD` provided together by the local environment. Authorize the Harmony and ASF applications in Earthdata Login if prompted. Keep credentials outside the repository. [Earthdata Login](https://urs.earthdata.nasa.gov/), [ASF Harmony guide](https://nisar-docs.asf.alaska.edu/harmony/).

Harmony requests GCOV Frequency A HHHH, HVHV, the subswath mask, number of looks, and the RTC gamma-to-sigma factor. It requests a padded geographic subset in the original radar projection. The padded window supports checking source centers and matching edge pixels. Products are clipped to the study area on export. The first fallback streams only HDF5 byte ranges needed for the padded hyperslab and caches the extracted data with a checksum. If the archive server cannot provide byte ranges, put the exact CMR-named HDF5 files in `data/raw/` or pass `--allow-full-hdf5` for authenticated, resumable HTTPS transfer. Both archives total 9,894,363,136 bytes. The fallback validates archive sizes and MD5 checksums, then reads raster hyperslabs through h5py. It exports a separate incidence-angle cube if the HDF5 carries one on a supported radar grid. A supplementary HDF5 byte-range read verifies the delivered HH/HV arrays and their pixel centers, applies the original input-data exception mask, and retains acquisition geometry. The geometry NPZ stores the incidence-angle and zero-Doppler time cubes on their original height-above-ellipsoid and horizontal coordinates. Subsequent runs can use the validated caches without network access. [ASF GCOV guide](https://nisar-docs.asf.alaska.edu/gcov/).

An alternate `--data-dir` isolates experiments or allows a different storage volume. Run status and logs are under `data/interim/`. Catalog caches, USACE subsets, source HDF5, and Harmony download files are under `data/raw/`. Published directories are timestamped and discoverable from `data/processed/latest_lidar.json` and, after success, `data/processed/latest_comparison.json`. Each manifest lists files, hashes, sizes, inputs, time, grids and statistics. The branch includes verified handoff snapshots under `data/processed/verified/lidar/` and `data/processed/verified/comparison/`. New pipeline runs write to separate, ignored timestamped folders. A failed full run records its blocker and leaves completed LiDAR outputs accessible.

## Spatial and temporal contract

- Geographic study footprint is the supplied WGS 84 bounding box intersected with FRF y = 700–1190 m for terrain and paired products. Radar native exports use the bounding box. Spatial transforms preserve longitude/easting first. GeoJSON uses WGS 84 longitude, latitude.
- Native LiDAR COGs preserve source raster values at exact 1 m FRF posting with a rotated EPSG:6542 affine and NAVD88 (geoid12b) heights. The UTM 18N 1 m COGs are nearest-sample map derivatives, with independent raster pixel centers. Heights retain the original vertical datum in both.
- The LiDAR-only comparison uses a 10 m EPSG:32618 lattice anchored at multiples of 10 m. The full analysis adopts the June GCOV posting in UTM 18N when possible. Both native affines and their lattice residual are recorded. A mismatching October grid is sampled on the explicit reference lattice using nearest neighbor to preserve source intensities and mask codes. An explicitly anchored 10 m UTM lattice is used if June has an unsuitable CRS or posting. Grid spacing is distinct from sensor resolution.
- LiDAR sample weights are the square metres of overlap between the projected native cell quadrilaterals and each target pixel clipped to the study footprint. Coverage divides valid observed area by the full target-pixel area. At least 50% valid area is required to report a comparison elevation or change. The joint change uses the same paired native cells for both dates. The difference of two separately aggregated means can have different support. Dispersion is the area-weighted population standard deviation. Count gives the number of valid native cells with positive intersection area. The USACE scan-level QC gate requires flag 1.
- GCOV subswath-mask values 0 and 255, missing or nonpositive number of looks, and nonzero input-data exception flags invalidate radar power. Unmasked finite nonnegative power is retained in the analysis. Positive power is converted using 10 log10 for dB. Radar dB change is October minus June and represents scattering change. Terrain elevation change is October minus June in meters. Co-location alone cannot identify shoreline motion or attribute physical erosion. [ASF NISAR Cookbook](https://asfopensarlab.github.io/NISAR_Cookbook/nisar-data-access/).
- The pairing reference is the CMR granule midpoint, with start and end lag also recorded. Tide, wave swash, wet sand and beach-state changes within either interval can confound cross-sensor interpretation.
- Source co-registration flags and geolocation residuals describe different uncertainties. Absolute cross-sensor residual needs independently surveyed common targets. The pipeline applies no empirical correlation shift, filtering, or second terrain correction. Independent validation observations should be supplied as a separate dataset and held out of fitting.

## Map and model files

| Item | Format and use |
|---|---|
| `lidar_{june,october,delta_z}_native.tif` | COG, measured elevation or paired change on exact 1 m FRF cells in EPSG:6542 |
| `lidar_{june,october,delta_z}_utm_1m.tif` | COG, 1 m UTM 18N display derivatives |
| `lidar_{june,october,dz}_m.tif` and `lidar_{june,october,dz}_{std_m,sample_count,coverage,valid}.tif` | COGs on the bundle's analysis grid |
| `study_area_fraction.tif` | COG of footprint area fraction within each comparison pixel |
| `transects.geojson` and `profiles.json` | Measured joint-support cross-shore profiles and WGS 84 lines. The JSON follows the existing profile import data contract |
| `nisar_{june,october}_{HHHH,HVHV,mask,numberOfLooks,rtcGammaToSigmaFactor,inputDataExceptionMask}_native_raw.tif` | Full comparison bundle only. COG subsets on native radar grids, with optional RTC factor when provided |
| `nisar_{june,october}_{HHHH,HVHV}_native_db.tif` | Full comparison bundle only. Screened native backscatter in dB |
| `nisar_{june,october}_*.tif` without the native suffix and `nisar_{HHHH,HVHV}_change_db.tif` | Full comparison bundle only. COGs for co-registered radar power, dB, quality observations and dB changes |
| `nisar_{june,october}_radar_geometry.npz` | Original radar-grid incidence angle and zero-Doppler time by ellipsoidal height, northing and easting. Field attributes and CRS are in the manifest |
| `comparison_pixels.csv` | One row per intersecting reference-grid cell. Zero-based row/column plus UTM pixel center in meters, longitude/latitude in degrees, scan flags and one column per analysis band. Empty fields represent missing values |
| `manifest.json` | Versioned JSON contract including affine, CRS, sizes and hashes. Affine order is [a, b, c, d, e, f] as in Rasterio. Pixel centers map at (column + 0.5, row + 0.5) |
| `duck_lidar_alignment.png`, `duck_radar_lidar_alignment.png` | Coordinate and coverage plots for the LiDAR and full comparison bundles respectively |

Raster NoData is IEEE NaN. Analysis mask values are 0 or 1 where defined, with the original GCOV subswath and input-data exception codes kept in their own rasters. Mapping software may serve the GeoTIFFs through a tile service. The existing frontend can consume the measured `profiles.json` via its profile import.

## QA from the 15 November 2026 run

Both USACE slices were downloaded through OPeNDAP and validated against their actual NetCDF time coordinates. The encoded times differ from the whole-second labels by only a few microseconds. The published slices preserve the source attributes and native coordinates. The monthly file links and their cache hashes are in the LiDAR bundle manifest. Some USACE global bounding-box and coverage-time attributes are inconsistent with the actual coordinate arrays, so verification uses the arrays directly. [June OPeNDAP source](https://chldata.erdc.dren.mil/thredds/dodsC/frf/geomorphology/DEMs/duneLidarDEM/2026/FRF-geomorphology_DEMs_duneLidarDEM_202606.nc.html), [October OPeNDAP source](https://chldata.erdc.dren.mil/thredds/dodsC/frf/geomorphology/DEMs/duneLidarDEM/2026/FRF-geomorphology_DEMs_duneLidarDEM_202610.nc.html).

| Epoch | LiDAR UTC and NetCDF index | NISAR CMR interval UTC | LiDAR time minus NISAR granule midpoint |
|---|---|---|---|
| June | 19 June 00:31:04, index 111 | 18 June 23:53:35.000000–23:54:09.999342 | +37 min 11.500329 s |
| October | 16 October 23:33:04, index 362 | 16 October 23:53:31.000000–23:54:06.999342 | −20 min 44.999671 s |

The full study box is covered by both catalog footprints. CMR lists descending track 069, frame 070, product version 1.0.11 and Frequency A HH/HV for both. The archive size and source MD5 values are in the catalog manifest. Harmony delivered all five requested numerical COGs for each date. The original HDF5 reads confirmed matching HH/HV power arrays, descending left-looking geometry, and track 069 / frame 070. The two HDF5 time intervals are 2026-06-18T23:53:35.000000000Z to 23:54:09.999342105Z and 2026-10-16T23:53:31.000000000Z to 23:54:06.999342105Z. The original time precision is preserved in the output metadata. [June CMR granule G4250721321-ASF](https://cmr.earthdata.nasa.gov/search/concepts/G4250721321-ASF), [October CMR granule G4376256706-ASF](https://cmr.earthdata.nasa.gov/search/concepts/G4376256706-ASF).

| Check | Result |
|---|---:|
| Native LiDAR centers in the study footprint | 63,751 |
| Valid June / valid October native cells | 19,851 / 19,120 |
| Paired native cells | 17,466 (27.40% of study centers) |
| Native paired change median / mean | −0.269 m / −0.314 m |
| Native paired change min / max | −2.255 m / +0.886 m |
| LiDAR-only 10 m grid intersections | 1,450 |
| 10 m change cells at ≥50% paired coverage | 168 (11.59%) |
| 10 m change median / mean | −0.283 m / −0.315 m |
| 10 m change min / max | −1.209 m / +0.180 m |
| FRF transform versus file lon/lat projected to UTM | 0.0490 m RMSE, 0.0696 m maximum |
| Scan-level USACE co-registration flags | 1 (good) in both epochs |
| USACE reflector RMS, June / October | 0.0975 m / 0.0754 m |
| USACE assessment plane offsets, June / October | 0.0393 m / 0.0510 m |

The native subtraction and validity mask were checked across the full exported arrays. Nine georeferenced native pixel centers were independently mapped back to exact 1 m FRF posts and matched to source elevations. At UTM center (432375 m E, 4004825 m N), an independent polygon-intersection calculation matched 128 contributing source cells, approximately 100% paired coverage, and −0.215214 m weighted change. All raster layouts were checked as COG, and output bytes matched the manifest hashes. The CSV and all five transect profiles passed structural checks. The published NAD83(2011) to WGS 84 transformation reports 2 m accuracy. The 0.0490 m source-coordinate agreement is an internal consistency check. Absolute sensor registration error remains unmeasured.

The feasibility comparison awaits the earlier Duck report and independent validation observations. The observations show localized terrain lowering and some gains on joint bare-earth LiDAR support. These statistics describe the observed cells and cannot be extrapolated to the unobserved footprint.


### Verified numerical radar comparison

| Check | Result |
|---|---:|
| June and October Frequency A posting | 10 m north-up, EPSG:32618 |
| Maximum delivered-versus-HDF5 pixel-center residual | 0.000 m for both dates |
| June-versus-October lattice offset | 0.000 pixels in x and y |
| Radar-valid centers per polarization and date | 1,310 of 1,310 eligible centers |
| Original input-data anomaly flags at eligible centers | 0 flagged in each date |
| Jointly valid radar–LiDAR comparison cells | 168 of 1,450 cells intersecting the study footprint (11.59%) |
| Mean measured LiDAR elevation change on those cells | −0.315 m |
| Mean HH / HV scattering change over the radar-only support | +1.125 dB / +0.458 dB |
| Source geometry per epoch | 21 ellipsoidal height levels × 3 northings × 3 eastings, 500 m horizontal posting |

The 1,310 radar centers lie inside the footprint. The CSV includes 140 additional boundary cells whose footprints intersect the study area but whose centers fall outside it, so they carry no centered radar sample. Both delivered covariance arrays matched their original HDF5 windows exactly. Every valid aligned HH/HV sample was independently mapped to the original Harmony pixel center and matched the power value, with the dB and change equations verified separately. Native radar pixels were retained on their original lattice. The coarser incidence-angle and zero-Doppler time metadata retain their own axes and are not used to increase the map resolution or adjust terrain measurements.

At comparison center (432375 m E, 4004825 m N), the independent join check reproduced −0.215214 m LiDAR change, −5.538648 dB HH change and −2.733876 dB HV change. All 58 comparison file sizes and SHA-256 hashes matched the manifest. An offline replay reproduced the hashes of all 58 comparison and 26 LiDAR files. COG layouts, CSV joins, quality screening and the alignment plot were checked. The zero numerical lattice offset is a grid result. Physical radar–LiDAR registration remains unmeasured without independent surveyed control.
