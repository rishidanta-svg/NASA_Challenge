# Project context: NASA Space Apps Challenge 2026 ("Dancing with the SARs")

> Handoff file from an earlier Claude session. Put it in the project repo root as `CLAUDE.md` so Claude Code loads it automatically.

## Status and deadline
- **Event:** NASA International Space Apps Challenge 2026. The team is in India.
- **Final submission is due by midnight on 15 Nov 2026.** Confirm the exact timezone on the submission page; it may not be IST.
- **Challenge:** **#5 "Dancing with the SARs"** (Intermediate/Advanced, Earth Science). We first chose #8 (MODIS/VIIRS hotspot harmonization) and then switched. **Submit under #5.**
- **Brief, #5:** build an interactive application that uses NASA-ISRO **NISAR** radar data to track and visualise one or more types of surface change. Pick a study area, download NISAR data (optionally with optical or GIS layers), and present the findings interactively. Hypothesise the physical drivers, discuss which polarizations show the change, and suggest future NISAR applications. The desired result is open source, user friendly, and gives actionable insight to a broad audience.
- **Judging criteria:** Influence/Impact, Creativity, Validity, Relevance, Presentation (no published weights). Local judges nominate teams for global judging, which includes the categories Best Use of Data and Local Impact.

## Team
- Five members: one who knows Java, three who know Python, all strong on logic. **No formal remote-sensing background.** Everyone must be able to explain the findings in their own words.
- Available tools: Claude, Gemini, ChatGPT.
- Stack: Python with Streamlit and Plotly (FastAPI with Leaflet is an option). Deploy on Streamlit Community Cloud, shipping **small preprocessed files only**.

## The project
**The question:** when several Earth-observation sensors disagree about a changing coastline, which features does each one actually detect, what really changed, and how confident should we be?

**Study site:** Duck, North Carolina, at the USACE Field Research Facility (FRF). It has hourly tower lidar, and NISAR acquisitions within about **37 min (June)** and **21 min (October 2026)** of lidar reference times.

**Datasets:** NISAR L-band (GCOV; GSLC still being investigated), Sentinel-1 C-band, Sentinel-2 L2A (NDVI, NDWI, MNDWI), FRF lidar DEMs (ground truth), NOAA tides (station 8651370), FRF/CDIP waves (17 m buoy, CDIP 433 / NDBC 44056; 26 m buoy, CDIP 430 / NDBC 44100), FRF met data (NDBC FRFN7), and the September nor'easter.

**Preliminary findings:**
1. LiDAR differencing from June to October shows real **beach lowering**: a median of about **−0.27 m** across common cells, and about **4,607 m²** of detectable lowering in the baseline scenario.
2. NISAR's dominant radar edge barely moved (about 0 m). It appears to follow the upper-beach **dune or vegetation transition, not the waterline**.
3. NISAR HH backscatter did **not** reliably track the measured lowering (ρ ≈ 0.07). The contrast is sensitive to spatial averaging and geolocation shifts, and HV gave no consistent support. We **cannot** claim radar detected the erosion.
4. Sentinel-1 independently sees a strong boundary near the NISAR feature (x ≈ 60 m), so it is a persistent feature, not a NISAR artefact.
5. The Sentinel-2 NDWI water boundary moved from x ≈ 98 m to 86 m (about 12 m), but this is **not verified erosion**: tide, swash, mixed pixels and resolution could explain it.
6. During the September nor'easter, significant wave height at the 17 m buoy reached about 4.29 m, and swash reached the upper beach. The storm is a **plausible contributor** to the lowering, but its share is not quantified.

**Project stages:**
1. Erosion detector: **not demonstrated.**
2. Multisensor discrepancy analysis: **supported. This is the product we are submitting.**
3. Physically informed coastal reconstruction or fusion: **proposed future work only. Do not claim it.**

The app must not merge physically different features (waterline, vegetation boundary, dune crest, beach profile) into one "perfect" coastline.

## What we're building today (priority order)
1. **Cross-section view (the main screen)** along one FRF profile, x running cross-shore:
   - June and October lidar profiles, with the lowering shaded.
   - The NISAR dominant edge (~60 m) and the Sentinel-1 boundary.
   - The Sentinel-2 NDWI boundary at 98 m then 86 m, flagged as unverified.
   - The weak radar transition at about 80–85 m, marked unresolved.
2. **Map panel:** site, toggleable sensor layers, elevation-change overlay.
3. **Timeline:** acquisitions, tide levels, wave heights, the nor'easter peak.
4. **"What each sensor actually sees" table:** feature detected, confidence, caveats.
5. **"Can we trust this boundary?" panel:** each claim tagged as supported, plausible, or not demonstrated.
6. **Project page, demo video and slides.** Plain-English explanations for every term; include a "where this could be wrong" slide.

**Pitch:** "When satellites disagree about a changing coastline, which one should you believe? At Duck, NC, LiDAR confirmed the beach dropped about 27 cm after a nor'easter. NISAR's strongest radar edge didn't move, because it's tracking the dune, not the water. Our tool shows what each sensor really sees, and how confident to be." Local angle: NISAR is an ISRO–NASA mission, and the method could apply to eroding Indian coasts such as Odisha, Kerala and Puducherry, presented as future work.

## Risks to manage (must fix)
- Submit under challenge #5, not #8.
- Cite every dataset with its granule or product ID, acquisition time in UTC, URL and access date, in a citation table in the repo and on the project page.
- **Detection limits:** state the NISAR pixel spacing ("didn't move" means no change larger than one pixel). Sentinel-2 NDWI bands are 10 m and MNDWI uses the 20 m SWIR band, so the 12 m shift is about one pixel.
- **Lidar uncertainty:** filter with `coregQCFlag`, and report the RMS error threshold (e.g. under 0.1 m for flag 1) next to the −0.27 m figure.
- **Define x:** it is the FRF local cross-shore coordinate, rotated about 69.97° from NC State Plane NAD83(2011). Elevations are in NAVD88. Show a labelled diagram.
- Say "beach lowering" or "elevation change", not "erosion", unless material loss is shown. Do not make causal storm claims.
- Lead with what we found, not with what failed. Keep the name honest: a sensor-disagreement explainer, not a "reconstruction system".
- **No third-party images** (an earlier draft had Realtor.com and news-site photos). Use our own plots only, follow NASA logo rules, and disclose AI use.
- Treat this as a single-site case study and explain how the method could transfer to other sites.
- Keep a recorded backup demo in case the live app fails. Make the repo public and check every link before submitting.

## Data access (verified 15 Nov 2026)
- **Accounts:** NASA Earthdata Login (NISAR, and Sentinel-1 via ASF) and a Copernicus Data Space account (Sentinel-2).
- **NISAR:** ASF (https://nisar-docs.asf.alaska.edu/access-overview). Use Vertex, `asf_search` (`dataset="NISAR"`), `earthaccess`, or S3. Files are HDF5. Cookbook: https://asfopensarlab.github.io/NISAR_Cookbook/notebooks/search-download-nisar-gcov-asf-search
- **Sentinel-1:** `asf_search` with `platform=SENTINEL1`, or the Copernicus Data Space STAC API. Prefer RTC products.
- **Sentinel-2:** Copernicus Data Space STAC (https://documentation.dataspace.copernicus.eu/APIs/STAC.html), L2A.
- **FRF lidar:** THREDDS catalogue http://chlthredds.erdc.dren.mil/thredds/catalog/frf/catalog.html, then `geomorphology/DEMs/` (monthly NetCDF, hourly grids). Open with `xarray.open_dataset(opendap_url)`. Variables: elevation, xFRF, yFRF, coregQCFlag.
- **Tides:** `https://api.tidesandcurrents.noaa.gov/api/prod/datagetter` with `station=8651370`, `product=water_level`, `datum=NAVD`, `units=metric`, `time_zone=gmt`.
- **Waves:** CDIP 433 (17 m) and 430 (26 m), or FRF THREDDS `frf/oceanography/waves/waverider-17m`. Also IOOS ERDDAP.
- **Met:** SECOORA ERDDAP `mil_army_usace_frfn7`. Backup: NC CLOUDS station DUKN7.

## Working rules for Claude in this repo
- Don't invent numbers. Every figure in the app or pitch must come from code or data in this repo.
- Keep claims at the level of evidence above: supported, plausible, or not demonstrated.
- Prefer simple, working, validated features over ambitious unfinished ones. Feature freeze comes well before the deadline.
