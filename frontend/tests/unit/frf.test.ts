import { describe, expect, it } from 'vitest';
import { FRF_Y_RANGE_M, NOAA_DUCK_STATION, STUDY_BOUNDS } from '../../src/config/geo';
import {
  frfToLngLat,
  frfToNcsp,
  lngLatToFrf,
  lngLatToUtm18N,
  ncspToFrf,
  utm18NToLngLat,
} from '../../src/lib/frf';

describe('FRF / NCSP / WGS84 / UTM18N coordinate transforms', () => {
  it('round-trips FRF <-> NC State Plane (EPSG:3358) to sub-millimetre accuracy', () => {
    for (const [x, y] of [
      [0, 0],
      [120, 700],
      [250, 950],
      [80, 1190],
    ] as const) {
      const [E, N] = frfToNcsp(x, y);
      const [rx, ry] = ncspToFrf(E, N);
      expect(rx).toBeCloseTo(x, 6);
      expect(ry).toBeCloseTo(y, 6);
    }
  });

  it('round-trips FRF <-> WGS84 (EPSG:4326) within 1 cm', () => {
    for (const [x, y] of [
      [50, 700],
      [100, 945],
      [150, 1190],
    ] as const) {
      const [lng, lat] = frfToLngLat(x, y);
      const [rx, ry] = lngLatToFrf(lng, lat);
      expect(rx).toBeCloseTo(x, 2);
      expect(ry).toBeCloseTo(y, 2);
    }
  });

  it('round-trips WGS84 <-> UTM Zone 18N (EPSG:32618)', () => {
    const lng = -75.7518;
    const lat = 36.186;
    const [E, N] = lngLatToUtm18N(lng, lat);
    expect(E).toBeGreaterThan(430_000);
    expect(E).toBeLessThan(435_000);
    expect(N).toBeGreaterThan(4_004_000);
    expect(N).toBeLessThan(4_006_000);
    const [rLng, rLat] = utm18NToLngLat(E, N);
    expect(rLng).toBeCloseTo(lng, 6);
    expect(rLat).toBeCloseTo(lat, 6);
  });

  it('maps NOAA station 8651370 onto the FRF pier alignment (y ≈ 515–520 m)', () => {
    const [x, y] = lngLatToFrf(NOAA_DUCK_STATION.lon, NOAA_DUCK_STATION.lat);
    expect(x).toBeGreaterThan(400);
    expect(x).toBeLessThan(560);
    expect(y).toBeGreaterThan(505);
    expect(y).toBeLessThan(530);
  });

  it('places the FRF y = 700–1190 m beach/foreshore corridor inside the Duck study bbox', () => {
    const [yMin, yMax] = FRF_Y_RANGE_M;
    for (const y of [yMin + 30, 850, 1000, yMax - 30]) {
      const [lng, lat] = frfToLngLat(100, y);
      expect(lng).toBeGreaterThanOrEqual(STUDY_BOUNDS.west);
      expect(lng).toBeLessThanOrEqual(STUDY_BOUNDS.east);
      expect(lat).toBeGreaterThanOrEqual(STUDY_BOUNDS.south);
      expect(lat).toBeLessThanOrEqual(STUDY_BOUNDS.north);
    }
  });
});
