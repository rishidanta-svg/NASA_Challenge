/**
 * Geographic configuration for the Duck FRF study area.
 *
 * Every constant here is a declared project parameter or a published
 * reference value; nothing is estimated. Display is Web Mercator (EPSG:3857,
 * MapLibre default). Analysis CRS for backend products is UTM 18N.
 */

/** Study-area bounds as given in the project brief (WGS84 degrees). */
export const STUDY_BOUNDS = {
  west: -75.753384,
  south: 36.18370,
  east: -75.750335,
  north: 36.18826,
} as const;

export const STUDY_BBOX: [number, number, number, number] = [
  STUDY_BOUNDS.west,
  STUDY_BOUNDS.south,
  STUDY_BOUNDS.east,
  STUDY_BOUNDS.north,
];

export const STUDY_CENTER: [number, number] = [
  (STUDY_BOUNDS.west + STUDY_BOUNDS.east) / 2,
  (STUDY_BOUNDS.south + STUDY_BOUNDS.north) / 2,
];

/** Alongshore extent of the study reach in the FRF local coordinate system (m). */
export const FRF_Y_RANGE_M = [700, 1190] as const;

export const ANALYSIS_CRS = 'EPSG:32618'; // WGS 84 / UTM zone 18N
export const DISPLAY_CRS = 'EPSG:3857'; // Web Mercator

/** Regional view used on first load: northern Outer Banks around Duck. */
export const REGIONAL_VIEW = {
  center: [-75.76, 36.17] as [number, number],
  zoom: 10.6,
};

/** Analysis period for seasonal comparison. */
export const ANALYSIS_PERIOD = {
  start: '2026-06-01T00:00:00Z',
  end: '2026-10-31T23:59:59Z',
} as const;

/** NOAA CO-OPS station 8651370 "Duck, NC" (published station metadata). */
export const NOAA_DUCK_STATION = {
  id: '8651370',
  name: 'Duck, NC',
  lat: 36.1833,
  lon: -75.7467,
  url: 'https://tidesandcurrents.noaa.gov/stationhome.html?id=8651370',
} as const;
