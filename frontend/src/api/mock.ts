/**
 * MOCK data provider — used only when the FastAPI backend is unreachable or
 * an endpoint is not implemented yet.
 *
 * Everything here is SYNTHETIC. Geometry is placed in the real FRF frame so
 * layers line up with the study area, but no value is an observation. Every
 * descriptor carries provenance.source = MOCK_SOURCE, and raster images carry
 * a burned-in "MOCK" watermark so screenshots cannot be mistaken for data.
 */
import { FRF_Y_RANGE_M } from '../config/geo';
import { frfAlongshoreLine, frfCrossShoreLine, frfRectCorners } from '../lib/frf';
import type {
  Analysis,
  BoundaryPick,
  LayerDescriptor,
  Profile,
  TerrainChange,
  TransectDetail,
  TransectSummary,
} from './schemas';

export const MOCK_SOURCE = 'MOCK — synthetic placeholder, not an observation';
export const MOCK_PREFIX = 'mock://';

/** FRF extent of mock rasters (m). */
export const MOCK_RASTER_FRF = { x0: 0, x1: 250, y0: FRF_Y_RANGE_M[0], y1: FRF_Y_RANGE_M[1] } as const;
export const MOCK_TRANSECT_Y = [700, 800, 900, 1000, 1100, 1190] as const;
const TRANSECT_X: [number, number] = [0, 250];

// ---------------- synthetic fields (FRF x,y in metres) ----------------
const g = (x: number, mu: number, s: number) => Math.exp(-(((x - mu) / s) ** 2));

export function mockDz(x: number, y: number): number {
  const v = Math.sin(y / 70) * 0.25 + Math.cos(y / 130) * 0.15;
  return -1.1 * g(x, 105 + 8 * Math.sin(y / 90), 22) * (0.8 + v) - 0.45 * g(x, 58, 9) + 0.35 * g(x, 150, 18);
}
export function mockModelDz(x: number, y: number): number {
  return mockDz(x, y) * 0.85 + 0.12 * Math.sin(x / 30 + y / 200);
}
export function mockModelSigma(x: number, y: number): number {
  return 0.08 + 0.35 * (1 - g(x, 90, 70)) + 0.05 * Math.abs(Math.sin(y / 110));
}

function profileZ(x: number, y: number, oct: boolean): number {
  const crest = 6.2 + 0.5 * Math.sin(y / 150);
  const dune = crest * g(x, 32, 16);
  const beach = 2.2 - x * 0.022;
  const z = Math.max(dune, beach) + 0.15 * Math.sin(x / 9 + y);
  return oct ? z + mockDz(x, y) : z;
}

const radarX = (y: number) => 56 + 4 * Math.sin(y / 60);
const opticalX = (y: number, oct: boolean) => (oct ? 98 : 108) + 6 * Math.sin(y / 90);

// ---------------- colormaps ----------------
export const DZ_COLORMAP = {
  type: 'diverging' as const,
  min: -1.5,
  max: 1.5,
  stops: [
    [-1.5, '#8c2d04'],
    [-0.75, '#e08a5a'],
    [-0.1, '#f2e6d8'],
    [0.1, '#e3eef0'],
    [0.75, '#5fb3c4'],
    [1.5, '#0f5e7a'],
  ] as [number, string][],
};
export const SIGMA_COLORMAP = {
  type: 'sequential' as const,
  min: 0,
  max: 0.6,
  stops: [
    [0, '#1b1530'],
    [0.2, '#5b3a8a'],
    [0.4, '#b07bc9'],
    [0.6, '#f1d8f5'],
  ] as [number, string][],
};

// ---------------- descriptors ----------------
const corners = frfRectCorners(MOCK_RASTER_FRF.x0, MOCK_RASTER_FRF.x1, MOCK_RASTER_FRF.y0, MOCK_RASTER_FRF.y1);
const prov = { source: MOCK_SOURCE, product_id: null, processing: 'Generated in browser from analytic functions in FRF coordinates' };

function unavailable(slot: string, title: string, group: LayerDescriptor['group'], sensor: LayerDescriptor['sensor'], units: string | null): LayerDescriptor {
  return {
    id: `${slot}-pending`,
    slot,
    title,
    group,
    sensor,
    kind: 'raster_xyz',
    units,
    epoch_label: '—',
    native_crs: 'EPSG:32618',
    inferred: group === 'model',
    status: 'unavailable',
    reason: 'Awaiting processed product from the data agent',
    provenance: { source: 'Not yet delivered' },
  };
}

export function mockLayers(): LayerDescriptor[] {
  return [
    {
      id: 'mock-lidar-dz',
      slot: 'lidar-dz',
      title: 'LiDAR Δz (Oct − Jun 2026)',
      group: 'measured',
      sensor: 'LIDAR',
      kind: 'image',
      url: `${MOCK_PREFIX}lidar-dz`,
      coordinates: corners,
      units: 'm',
      quantity: 'Elevation change (later − earlier)',
      colormap: DZ_COLORMAP,
      acquired_at: null,
      epoch_label: 'Oct − Jun 2026 (mock epochs)',
      reference_date: null,
      native_crs: 'EPSG:32618',
      native_resolution_m: 1,
      vertical_datum: 'NAVD88 (mock)',
      inferred: false,
      status: 'available',
      provenance: prov,
    },
    unavailable('nisar-hh', 'NISAR GCOV · HH', 'sensor', 'NISAR', 'dB'),
    unavailable('nisar-hv', 'NISAR GCOV · HV', 'sensor', 'NISAR', 'dB'),
    ...(['june', 'october'] as const).map(
      (ep): LayerDescriptor => ({
        id: `mock-nisar-boundary-${ep}`,
        slot: 'nisar-boundary',
        title: `NISAR radar transition · ${ep === 'june' ? 'Jun' : 'Oct'}`,
        group: 'sensor',
        sensor: 'NISAR',
        kind: 'geojson',
        url: `${MOCK_PREFIX}nisar-boundary/${ep}`,
        units: null,
        acquired_at: null,
        epoch_label: `${ep === 'june' ? 'June' : 'October'} 2026 (mock epoch)`,
        reference_date: ep === 'june' ? '2026-06-15' : '2026-10-15',
        native_crs: 'EPSG:32618',
        inferred: false,
        status: 'available',
        provenance: prov,
      }),
    ),
    unavailable('s1-vv', 'Sentinel-1 · VV', 'sensor', 'SENTINEL-1', 'dB'),
    unavailable('s1-vh', 'Sentinel-1 · VH', 'sensor', 'SENTINEL-1', 'dB'),
    unavailable('s2-index', 'Sentinel-2 · NDWI', 'sensor', 'SENTINEL-2', 'index'),
    ...(['june', 'october'] as const).map(
      (ep): LayerDescriptor => ({
        id: `mock-s2-boundary-${ep}`,
        slot: 's2-boundary',
        title: `Sentinel-2 optical waterline · ${ep === 'june' ? 'Jun' : 'Oct'}`,
        group: 'sensor',
        sensor: 'SENTINEL-2',
        kind: 'geojson',
        url: `${MOCK_PREFIX}s2-boundary/${ep}`,
        units: null,
        acquired_at: null,
        epoch_label: `${ep === 'june' ? 'June' : 'October'} 2026 (mock epoch)`,
        reference_date: ep === 'june' ? '2026-06-15' : '2026-10-15',
        native_crs: 'EPSG:32618',
        inferred: false,
        status: 'available',
        provenance: prov,
      }),
    ),
    {
      id: 'mock-model-dz',
      slot: 'model-dz',
      title: 'Model-inferred Δz',
      group: 'model',
      sensor: 'MODEL',
      kind: 'image',
      url: `${MOCK_PREFIX}model-dz`,
      coordinates: corners,
      units: 'm',
      quantity: 'Inferred elevation change',
      colormap: DZ_COLORMAP,
      acquired_at: null,
      epoch_label: 'Oct − Jun 2026 (mock)',
      reference_date: null,
      native_crs: 'EPSG:32618',
      native_resolution_m: 10,
      vertical_datum: 'NAVD88 (mock)',
      inferred: true,
      status: 'available',
      provenance: prov,
    },
    {
      id: 'mock-model-sigma',
      slot: 'model-sigma',
      title: 'Model uncertainty (1σ)',
      group: 'model',
      sensor: 'MODEL',
      kind: 'image',
      url: `${MOCK_PREFIX}model-sigma`,
      coordinates: corners,
      units: 'm',
      quantity: '1σ uncertainty of inferred Δz',
      colormap: SIGMA_COLORMAP,
      acquired_at: null,
      epoch_label: 'Oct − Jun 2026 (mock)',
      reference_date: null,
      native_crs: 'EPSG:32618',
      native_resolution_m: 10,
      vertical_datum: null,
      inferred: true,
      status: 'available',
      provenance: prov,
    },
  ];
}

export function mockTerrainChange(): TerrainChange {
  const layer = mockLayers().find((l) => l.slot === 'lidar-dz')!;
  return {
    layer,
    epochs: [
      { label: 'June 2026 (mock)', survey_start: '2026-06-15T00:00:00Z', product_id: null },
      { label: 'October 2026 (mock)', survey_start: '2026-10-15T00:00:00Z', product_id: null },
    ],
    vertical_datum: 'NAVD88 (mock)',
    units: 'm',
    uncertainty_m: null,
    stats: null,
  };
}

// ---------------- transects ----------------
export function mockTransectSummaries(): TransectSummary[] {
  return MOCK_TRANSECT_Y.map((y) => ({
    type: 'Feature',
    geometry: { type: 'LineString', coordinates: frfCrossShoreLine(y, TRANSECT_X[0], TRANSECT_X[1]) },
    properties: {
      id: `FRF-Y${y}`,
      label: `FRF y = ${y} m`,
      frf_y_m: y,
      x_reference: 'FRF cross-shore x (m); line starts at FRF x = 0 m',
    },
  }));
}

export function mockTransectDetail(id: string): TransectDetail | null {
  const s = mockTransectSummaries().find((t) => t.properties.id === id);
  if (!s) return null;
  const y = s.properties.frf_y_m!;
  const xs = Array.from({ length: 126 }, (_, i) => TRANSECT_X[0] + i * 2);
  const mk = (oct: boolean): Profile => ({
    epoch_label: oct ? 'October 2026 (mock)' : 'June 2026 (mock)',
    acquired_at: null,
    source: MOCK_SOURCE,
    vertical_datum: 'NAVD88 (mock)',
    units: 'm',
    points: xs.map((x) => ({ x_m: x, z_m: +profileZ(x, y, oct).toFixed(3) })),
  });
  const june = mk(false);
  const oct = mk(true);
  const contour = (p: Profile, level: number) => {
    for (let i = p.points.length - 1; i > 0; i--) {
      const a = p.points[i - 1]!;
      const b = p.points[i]!;
      if ((a.z_m - level) * (b.z_m - level) <= 0 && a.z_m !== b.z_m)
        return a.x_m + ((level - a.z_m) / (b.z_m - a.z_m)) * (b.x_m - a.x_m);
    }
    return null;
  };
  const boundaries: BoundaryPick[] = [];
  for (const [ep, isOct, prof] of [
    ['June 2026 (mock)', false, june],
    ['October 2026 (mock)', true, oct],
  ] as const) {
    boundaries.push({ type: 'radar', sensor: 'NISAR', definition: 'HH/HV backscatter transition (mock)', epoch_label: ep, acquired_at: null, x_m: +radarX(y).toFixed(1), uncertainty_m: 10 });
    boundaries.push({ type: 'optical', sensor: 'SENTINEL-2', definition: 'NDWI waterline (mock)', epoch_label: ep, acquired_at: null, x_m: +opticalX(y, isOct).toFixed(1), uncertainty_m: 10 });
    const c = contour(prof, 1);
    if (c !== null) boundaries.push({ type: 'terrain', sensor: 'LIDAR', definition: 'z = 1.0 m contour (mock datum)', epoch_label: ep, acquired_at: null, x_m: +c.toFixed(1), uncertainty_m: 1 });
  }
  return { ...s, profiles: [june, oct], boundaries };
}

export function mockAnalysis(id: string): Analysis | null {
  const d = mockTransectDetail(id);
  if (!d) return null;
  const y = d.properties.frf_y_m!;
  const june = d.profiles[0]!;
  const wlJun = +opticalX(y, false).toFixed(2);
  const wlOct = +opticalX(y, true).toFixed(2);
  const dtJun = +radarX(y).toFixed(2);
  const dtOct = +(radarX(y) - 2.4).toFixed(2);
  return {
    transect_id: id,
    frf_y_m: y,
    x_origin_frf_m: 0,
    x_reference: 'MOCK FRF cross-shore x (m); line starts at FRF x = 0 m',
    analysis_crs: 'EPSG:32618',
    model_name: 'MOCK feature-separated boundary reconstruction',
    model_version: 'mock-0',
    state_scope: 'observed boundary features; not full terrain or bathymetry',
    inferred: true,
    units: 'm',
    uncertainty_method: 'MOCK — illustrative only',
    inputs: ['MOCK Sentinel-2 NDWI', 'MOCK Sentinel-1 VV/VH'],
    epochs: [
      {
        date: '2026-06',
        epoch_label: 'June 2026 (mock)',
        waterline: {
          x_frf_m: wlJun,
          x_m: wlJun,
          cv_rmse_m: 3.02,
          source: 'MOCK Sentinel-2 NDWI',
          status: 'mock estimate',
          acquired_at: null,
        },
        dunetoe: {
          accepted_x_frf_m: dtJun,
          accepted_x_m: dtJun,
          bayes_map_x_frf_m: dtJun,
          bayes_map_x_m: dtJun,
          bayes_median_x_frf_m: dtJun,
          bayes_median_x_m: dtJun,
          ci90_low_frf_m: +(dtJun - 9.5).toFixed(2),
          ci90_low_m: +(dtJun - 9.5).toFixed(2),
          ci90_high_frf_m: +(dtJun + 9.5).toFixed(2),
          ci90_high_m: +(dtJun + 9.5).toFixed(2),
          posterior_sd_m: 6.4,
          vv_vh_disagreement_m: 4.0,
          vv_vh_disagreement_limit_m: 29.8,
          cv_rmse_conservative_m: 11.0,
          radar_vv_x_frf_m: +(dtJun - 2).toFixed(2),
          radar_vv_x_m: +(dtJun - 2).toFixed(2),
          radar_vh_x_frf_m: +(dtJun + 2).toFixed(2),
          radar_vh_x_m: +(dtJun + 2).toFixed(2),
          source: 'MOCK Bayesian fusion',
          status: 'accepted: mock',
          acquired_at: null,
        },
        validation_lidar: {
          wetdry_x_frf_m: +(wlJun - 1.2).toFixed(2),
          wetdry_x_m: +(wlJun - 1.2).toFixed(2),
          dunetoe_x_frf_m: +(dtJun + 1.5).toFixed(2),
          dunetoe_x_m: +(dtJun + 1.5).toFixed(2),
          contour_1p5m_x_frf_m: +(wlJun - 5.0).toFixed(2),
          contour_1p5m_x_m: +(wlJun - 5.0).toFixed(2),
          usage: 'validation-only; mock',
        },
      },
      {
        date: '2026-10',
        epoch_label: 'October 2026 (mock)',
        waterline: {
          x_frf_m: wlOct,
          x_m: wlOct,
          cv_rmse_m: 8.49,
          source: 'MOCK Sentinel-2 NDWI',
          status: 'mock estimate',
          acquired_at: null,
        },
        dunetoe: {
          accepted_x_frf_m: dtOct,
          accepted_x_m: dtOct,
          bayes_map_x_frf_m: dtOct,
          bayes_map_x_m: dtOct,
          bayes_median_x_frf_m: dtOct,
          bayes_median_x_m: dtOct,
          ci90_low_frf_m: +(dtOct - 5.5).toFixed(2),
          ci90_low_m: +(dtOct - 5.5).toFixed(2),
          ci90_high_frf_m: +(dtOct + 5.5).toFixed(2),
          ci90_high_m: +(dtOct + 5.5).toFixed(2),
          posterior_sd_m: 3.8,
          vv_vh_disagreement_m: 2.0,
          vv_vh_disagreement_limit_m: 15.0,
          cv_rmse_conservative_m: 4.3,
          radar_vv_x_frf_m: +(dtOct - 1).toFixed(2),
          radar_vv_x_m: +(dtOct - 1).toFixed(2),
          radar_vh_x_frf_m: +(dtOct + 1).toFixed(2),
          radar_vh_x_m: +(dtOct + 1).toFixed(2),
          source: 'MOCK Bayesian fusion',
          status: 'accepted: mock',
          acquired_at: null,
        },
        validation_lidar: {
          wetdry_x_frf_m: +(wlOct + 7.0).toFixed(2),
          wetdry_x_m: +(wlOct + 7.0).toFixed(2),
          dunetoe_x_frf_m: +(dtOct + 1.0).toFixed(2),
          dunetoe_x_m: +(dtOct + 1.0).toFixed(2),
          contour_1p5m_x_frf_m: +(wlOct - 3.0).toFixed(2),
          contour_1p5m_x_m: +(wlOct - 3.0).toFixed(2),
          usage: 'validation-only; mock',
        },
      },
    ],
    october_minus_june: {
      waterline_shift_m: +(wlOct - wlJun).toFixed(2),
      dunetoe_shift_m: +(dtOct - dtJun).toFixed(2),
    },
    skill: null,
    physics_model: {
      status: 'available',
      target_epoch_label: 'October 2026 (mock)',
      vertical_datum: 'NAVD88 (mock)',
      points: june.points.map((p) => ({
        x_m: p.x_m,
        z_m: +(p.z_m + mockModelDz(p.x_m, y)).toFixed(3),
        sigma_m: +mockModelSigma(p.x_m, y).toFixed(3),
      })),
    },
  };
}

// ---------------- mock:// resolvers (browser only) ----------------
export function mockGeoJson(path: string): GeoJSON.FeatureCollection {
  const [slot, ep] = path.replace(MOCK_PREFIX, '').split('/');
  const oct = ep === 'october';
  const [y0, y1] = FRF_Y_RANGE_M;
  const coords =
    slot === 'nisar-boundary' ? frfAlongshoreLine(radarX, y0, y1) : frfAlongshoreLine((y) => opticalX(y, oct), y0, y1);
  return {
    type: 'FeatureCollection',
    features: [{ type: 'Feature', properties: { mock: true, slot, epoch: ep }, geometry: { type: 'LineString', coordinates: coords } }],
  };
}

function hexToRgb(h: string): [number, number, number] {
  const n = parseInt(h.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export function colorAt(stops: [number, string][], v: number): [number, number, number] {
  if (v <= stops[0]![0]) return hexToRgb(stops[0]![1]);
  for (let i = 1; i < stops.length; i++) {
    const [b, cb] = stops[i]!;
    const [a, ca] = stops[i - 1]!;
    if (v <= b) {
      const t = (v - a) / (b - a);
      const A = hexToRgb(ca);
      const B = hexToRgb(cb);
      return [0, 1, 2].map((k) => Math.round(A[k]! + (B[k]! - A[k]!) * t)) as [number, number, number];
    }
  }
  return hexToRgb(stops[stops.length - 1]![1]);
}

const imageCache = new Map<string, string>();

/** Render a mock raster to a PNG data URL. Rows: north (y1) → south (y0); cols: x0 → x1. */
export function mockImageDataUrl(path: string): string {
  const hit = imageCache.get(path);
  if (hit) return hit;
  const slot = path.replace(MOCK_PREFIX, '');
  const { x0, x1, y0, y1 } = MOCK_RASTER_FRF;
  const res = slot === 'lidar-dz' ? 1 : 2;
  const W = Math.round((x1 - x0) / res);
  const H = Math.round((y1 - y0) / res);
  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d')!;
  const img = ctx.createImageData(W, H);
  const fn = slot === 'model-sigma' ? mockModelSigma : slot === 'model-dz' ? mockModelDz : mockDz;
  const cmap = slot === 'model-sigma' ? SIGMA_COLORMAP : DZ_COLORMAP;
  for (let r = 0; r < H; r++) {
    const y = y1 - (r + 0.5) * res;
    for (let c = 0; c < W; c++) {
      const x = x0 + (c + 0.5) * res;
      const v = fn(x, y);
      const [R, G, B] = colorAt(cmap.stops, v);
      const i = (r * W + c) * 4;
      img.data[i] = R;
      img.data[i + 1] = G;
      img.data[i + 2] = B;
      img.data[i + 3] = slot !== 'model-sigma' && Math.abs(v) < 0.05 ? 60 : 235;
    }
  }
  ctx.putImageData(img, 0, 0);
  // Burned-in watermark.
  ctx.save();
  ctx.fillStyle = 'rgba(255,255,255,0.55)';
  ctx.strokeStyle = 'rgba(0,0,0,0.35)';
  ctx.font = `bold ${Math.round(W / 7)}px sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  for (let k = 0; k < 4; k++) {
    const yy = (H * (k + 0.5)) / 4;
    ctx.save();
    ctx.translate(W / 2, yy);
    ctx.rotate(-Math.PI / 2.4);
    ctx.strokeText('MOCK', 0, 0);
    ctx.fillText('MOCK', 0, 0);
    ctx.restore();
  }
  ctx.restore();
  const url = canvas.toDataURL('image/png');
  imageCache.set(path, url);
  return url;
}
