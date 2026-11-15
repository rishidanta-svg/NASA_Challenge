import { describe, expect, it } from 'vitest';
import { mockLayers } from '../../src/api/mock';
import { noaaNumber, noaaTimeToIso } from '../../src/api/noaa';
import { isMockDescriptor, resolveSlot } from '../../src/lib/layers';

describe('Slot resolution and NOAA parsing helpers', () => {
  it('resolves time-dependent slots to the nearest epoch and leaves awaiting slots null', () => {
    const layers = mockLayers();
    const junRadar = resolveSlot(layers, 'nisar-boundary', '2026-06-20');
    expect(junRadar?.id).toBe('mock-nisar-boundary-june');
    expect(isMockDescriptor(junRadar)).toBe(true);

    const octRadar = resolveSlot(layers, 'nisar-boundary', '2026-10-02');
    expect(octRadar?.id).toBe('mock-nisar-boundary-october');

    // Unpopulated sensor slot stays null ("Awaiting data")
    expect(resolveSlot(layers, 'nisar-hh', '2026-06-20')).toBeNull();
  });

  it('parses NOAA GMT timestamps to ISO-8601 UTC and never coerces missing values to 0', () => {
    expect(noaaTimeToIso('2026-11-15 04:54')).toBe('2026-11-15T04:54:00Z');
    expect(noaaTimeToIso('')).toBeNull();
    expect(noaaTimeToIso(undefined)).toBeNull();

    expect(noaaNumber('0.342')).toBeCloseTo(0.342, 5);
    expect(noaaNumber('-0.419')).toBeCloseTo(-0.419, 5);
    expect(noaaNumber('')).toBeNull();
    expect(noaaNumber('   ')).toBeNull();
    expect(noaaNumber(undefined)).toBeNull();
  });
});
