import { describe, expect, it } from 'vitest';
import { STUDY_CENTER } from '../../src/config/geo';
import { decodeTerrarium, lngLatToTilePixel, pixelSizeMeters } from '../../src/lib/terrarium';

describe('AWS Terrarium elevation utilities', () => {
  it('decodes Terrarium RGB values according to (R*256 + G + B/256) - 32768', () => {
    // Sea level (0 m) -> R=128, G=0, B=0
    expect(decodeTerrarium(128, 0, 0)).toBeCloseTo(0, 5);
    // +10.5 m -> R=128, G=10, B=128
    expect(decodeTerrarium(128, 10, 128)).toBeCloseTo(10.5, 5);
    // -5.0 m -> 32763 -> R=127, G=251, B=0
    expect(decodeTerrarium(127, 251, 0)).toBeCloseTo(-5, 5);
  });

  it('computes valid Web Mercator tile and pixel indices for Duck FRF', () => {
    const t12 = lngLatToTilePixel(STUDY_CENTER[0], STUDY_CENTER[1], 12);
    expect(t12.x).toBe(1186);
    expect(t12.y).toBe(1605);
    expect(t12.px).toBeGreaterThanOrEqual(0);
    expect(t12.px).toBeLessThan(256);
    expect(t12.py).toBeGreaterThanOrEqual(0);
    expect(t12.py).toBeLessThan(256);
  });

  it('reports ~3.9 m ground pixel size at zoom 15 for Duck latitude', () => {
    const m = pixelSizeMeters(STUDY_CENTER[1], 15);
    expect(m).toBeGreaterThan(3.5);
    expect(m).toBeLessThan(4.2);
  });
});
