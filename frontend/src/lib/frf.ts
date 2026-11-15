/**
 * Coordinate transforms between WGS84, UTM 18N (analysis CRS), NC State Plane
 * (NAD83, metres) and the USACE FRF local coordinate system.
 *
 * FRF definition (USACE Field Research Facility, Duck NC): origin at NC State
 * Plane E=901951.6805 m, N=274093.1562 m; +x points offshore along the pier,
 * +y alongshore toward the north. The FRF +y axis is rotated
 * (90 − 69.974707831)° counter-clockwise from State Plane grid north
 * (constants as used in USACE CHL getdatatestbed geoprocess.FRF2ncsp).
 *
 * Verified in tests/unit/frf.test.ts: NOAA station 8651370 (on the FRF pier)
 * maps to y ≈ 517 m (pier centreline ≈ 515 m), and the FRF y = 700–1190 m
 * reach falls within the study bounding box.
 */
import proj4 from 'proj4';

proj4.defs(
  'EPSG:3358',
  '+proj=lcc +lat_1=36.16666666666666 +lat_2=34.33333333333334 +lat_0=33.75 +lon_0=-79 ' +
    '+x_0=609601.22 +y_0=0 +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs',
);
proj4.defs('EPSG:32618', '+proj=utm +zone=18 +datum=WGS84 +units=m +no_defs');

export const FRF_ORIGIN_NCSP = { E: 901951.6805, N: 274093.1562 } as const;
export const FRF_ROTATION_RAD = ((90 - 69.974707831) * Math.PI) / 180;

const COS = Math.cos(FRF_ROTATION_RAD);
const SIN = Math.sin(FRF_ROTATION_RAD);

export type LngLat = [number, number];

export function frfToNcsp(x: number, y: number): [number, number] {
  return [FRF_ORIGIN_NCSP.E + x * COS - y * SIN, FRF_ORIGIN_NCSP.N + x * SIN + y * COS];
}

export function ncspToFrf(E: number, N: number): [number, number] {
  const dE = E - FRF_ORIGIN_NCSP.E;
  const dN = N - FRF_ORIGIN_NCSP.N;
  return [dE * COS + dN * SIN, -dE * SIN + dN * COS];
}

export function frfToLngLat(x: number, y: number): LngLat {
  const [E, N] = frfToNcsp(x, y);
  const [lng, lat] = proj4('EPSG:3358', 'EPSG:4326', [E, N]);
  return [lng!, lat!] as LngLat;
}

export function lngLatToFrf(lng: number, lat: number): [number, number] {
  const [E, N] = proj4('EPSG:4326', 'EPSG:3358', [lng, lat]);
  return ncspToFrf(E!, N!);
}

export function lngLatToUtm18N(lng: number, lat: number): [number, number] {
  const [E, N] = proj4('EPSG:4326', 'EPSG:32618', [lng, lat]);
  return [E!, N!];
}

export function utm18NToLngLat(E: number, N: number): LngLat {
  const [lng, lat] = proj4('EPSG:32618', 'EPSG:4326', [E, N]);
  return [lng!, lat!] as LngLat;
}

/** Shore-normal line at a fixed FRF y between two cross-shore positions. */
export function frfCrossShoreLine(y: number, x0: number, x1: number, steps = 2): LngLat[] {
  const out: LngLat[] = [];
  for (let i = 0; i <= steps; i++) out.push(frfToLngLat(x0 + ((x1 - x0) * i) / steps, y));
  return out;
}

/** Alongshore polyline x = f(y) sampled in FRF and converted to lng/lat. */
export function frfAlongshoreLine(fn: (y: number) => number, y0: number, y1: number, step = 10): LngLat[] {
  const out: LngLat[] = [];
  for (let y = y0; y <= y1 + 1e-9; y += step) out.push(frfToLngLat(fn(y), y));
  return out;
}

/** Corner coordinates (TL, TR, BR, BL as seen with north up) of an FRF rectangle for MapLibre image sources. */
export function frfRectCorners(x0: number, x1: number, y0: number, y1: number): [LngLat, LngLat, LngLat, LngLat] {
  // In the image, rows run from y1 (top, north) to y0 (bottom); columns from x0 (left, landward) to x1 (right, offshore).
  return [frfToLngLat(x0, y1), frfToLngLat(x1, y1), frfToLngLat(x1, y0), frfToLngLat(x0, y0)];
}
