/**
 * Independent overlay slots. Each slot is filled by at most one active layer
 * descriptor from /api/layers (matched by `slot`). Slots stay visible in the
 * UI as "Awaiting data" when nothing fills them.
 */
import type { LayerGroup, Sensor } from '../api/schemas';

export interface SlotDef {
  id: string;
  title: string;
  group: LayerGroup;
  sensor: Sensor;
  /** What the layer physically represents — shown in the legend. */
  meaning: string;
  expectedUnits: string | null;
  defaultOpacity: number;
  /** Swatch colour for the layer list / vector rendering. */
  color: string;
}

export const SLOTS: SlotDef[] = [
  {
    id: 'lidar-dz',
    title: 'LiDAR elevation change',
    group: 'measured',
    sensor: 'LIDAR',
    meaning: 'Measured bare-earth Δz between survey epochs',
    expectedUnits: 'm',
    defaultOpacity: 0.8,
    color: '#db9d82',
  },
  {
    id: 'nisar-hh',
    title: 'NISAR GCOV · HH',
    group: 'sensor',
    sensor: 'NISAR',
    meaning: 'L-band backscatter, HH polarisation',
    expectedUnits: 'dB',
    defaultOpacity: 0.75,
    color: '#65dfce',
  },
  {
    id: 'nisar-hv',
    title: 'NISAR GCOV · HV',
    group: 'sensor',
    sensor: 'NISAR',
    meaning: 'L-band backscatter, HV polarisation',
    expectedUnits: 'dB',
    defaultOpacity: 0.75,
    color: '#4fbfae',
  },
  {
    id: 'lidar-elevation',
    title: 'LiDAR elevation',
    group: 'measured',
    sensor: 'LIDAR',
    meaning: 'Bare-earth elevation in NAVD88',
    expectedUnits: 'm',
    defaultOpacity: 0.75,
    color: '#db9d82',
  },
  {
    id: 'nisar-hh-change',
    title: 'NISAR HH backscatter change',
    group: 'sensor',
    sensor: 'NISAR',
    meaning: 'October minus June radar scattering',
    expectedUnits: 'dB',
    defaultOpacity: 0.75,
    color: '#65dfce',
  },
  {
    id: 'nisar-hv-change',
    title: 'NISAR HV backscatter change',
    group: 'sensor',
    sensor: 'NISAR',
    meaning: 'October minus June radar scattering',
    expectedUnits: 'dB',
    defaultOpacity: 0.75,
    color: '#4fbfae',
  },
  {
    id: 'lidar-coverage',
    title: 'Paired LiDAR coverage',
    group: 'measured',
    sensor: 'LIDAR',
    meaning: 'Fraction of each 10 m cell with both surveys',
    expectedUnits: 'fraction',
    defaultOpacity: 0.75,
    color: '#77ddd0',
  },
  {
    id: 'nisar-quality',
    title: 'NISAR valid-data mask',
    group: 'sensor',
    sensor: 'NISAR',
    meaning: 'Quality-screened GCOV support',
    expectedUnits: 'flag',
    defaultOpacity: 0.75,
    color: '#5bd3a5',
  },
  {
    id: 'nisar-boundary',
    title: 'NISAR radar transition',
    group: 'sensor',
    sensor: 'NISAR',
    meaning: 'Radar backscatter transition — not a shoreline or erosion line',
    expectedUnits: null,
    defaultOpacity: 1,
    color: '#65dfce',
  },
  {
    id: 's1-vv',
    title: 'Sentinel-1 · VV',
    group: 'sensor',
    sensor: 'SENTINEL-1',
    meaning: 'C-band backscatter, VV polarisation',
    expectedUnits: 'dB',
    defaultOpacity: 0.75,
    color: '#9ba9ef',
  },
  {
    id: 's1-vh',
    title: 'Sentinel-1 · VH',
    group: 'sensor',
    sensor: 'SENTINEL-1',
    meaning: 'C-band backscatter, VH polarisation',
    expectedUnits: 'dB',
    defaultOpacity: 0.75,
    color: '#8290db',
  },
  {
    id: 's2-index',
    title: 'Sentinel-2 · water/vegetation index',
    group: 'sensor',
    sensor: 'SENTINEL-2',
    meaning: 'Spectral index from surface reflectance (e.g. NDWI)',
    expectedUnits: 'index',
    defaultOpacity: 0.75,
    color: '#c3cf9e',
  },
  {
    id: 's2-boundary',
    title: 'Sentinel-2 optical waterline',
    group: 'sensor',
    sensor: 'SENTINEL-2',
    meaning: 'Instantaneous optical water/land edge at acquisition time',
    expectedUnits: null,
    defaultOpacity: 1,
    color: '#edbf7c',
  },
  {
    id: 'model-dz',
    title: 'Model-inferred elevation change',
    group: 'model',
    sensor: 'MODEL',
    meaning: 'Physics-informed model estimate — not a measurement',
    expectedUnits: 'm',
    defaultOpacity: 0.8,
    color: '#d58bd8',
  },
  {
    id: 'model-sigma',
    title: 'Model uncertainty (1σ)',
    group: 'model',
    sensor: 'MODEL',
    meaning: 'One-standard-deviation uncertainty of the model estimate',
    expectedUnits: 'm',
    defaultOpacity: 0.7,
    color: '#b07bc9',
  },
];

export const GROUP_LABEL: Record<LayerGroup, string> = {
  measured: 'Measured',
  sensor: 'Satellite sensors',
  model: 'Model-inferred',
  reference: 'Reference',
};

export function slotById(id: string): SlotDef | undefined {
  return SLOTS.find((s) => s.id === id);
}
