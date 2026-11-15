import { describe, expect, it } from 'vitest';
import { configStudyArea } from '../../src/api/client';
import { mockAnalysis, mockLayers, mockTerrainChange, mockTransectDetail } from '../../src/api/mock';
import {
  AnalysisSchema,
  LayerDescriptorSchema,
  LayerListSchema,
  ProfileSchema,
  StudyAreaSchema,
  TerrainChangeSchema,
  TransectDetailSchema,
} from '../../src/api/schemas';

describe('FastAPI Zod contract schemas', () => {
  it('validates the configured study area and all mock fallbacks against the strict schemas', () => {
    expect(StudyAreaSchema.safeParse(configStudyArea()).success).toBe(true);
    expect(LayerListSchema.safeParse(mockLayers()).success).toBe(true);
    expect(TerrainChangeSchema.safeParse(mockTerrainChange()).success).toBe(true);

    const detail = mockTransectDetail('FRF-Y900');
    expect(detail).not.toBeNull();
    expect(TransectDetailSchema.safeParse(detail).success).toBe(true);

    const analysis = mockAnalysis('FRF-Y900');
    expect(analysis).not.toBeNull();
    expect(AnalysisSchema.safeParse(analysis).success).toBe(true);
  });

  it('rejects profiles with non-increasing cross-shore x_m coordinates', () => {
    const badProfile = {
      epoch_label: 'June 2026',
      acquired_at: '2026-06-15T00:00:00Z',
      source: 'USACE LiDAR',
      vertical_datum: 'NAVD88',
      units: 'm',
      points: [
        { x_m: 0, z_m: 4 },
        { x_m: 20, z_m: 3 },
        { x_m: 15, z_m: 2 },
      ],
    };
    expect(ProfileSchema.safeParse(badProfile).success).toBe(false);
  });

  it('rejects model layers that do not set inferred=true or measured layers that set inferred=true', () => {
    const base = mockLayers().find((l) => l.slot === 'model-dz')!;
    expect(LayerDescriptorSchema.safeParse({ ...base, inferred: false }).success).toBe(false);

    const measured = mockLayers().find((l) => l.slot === 'lidar-dz')!;
    expect(LayerDescriptorSchema.safeParse({ ...measured, inferred: true }).success).toBe(false);
  });
});
