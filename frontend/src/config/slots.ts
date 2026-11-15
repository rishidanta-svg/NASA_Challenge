/**
 * Independent overlay slots. Each slot is filled by at most one active layer
 * descriptor from /api/layers (matched by `slot`). Slots stay visible in the
 * UI as "Awaiting data" when nothing fills them.
 */
import type { LayerGroup, Sensor } from '../api/schemas';

export type LayerClassification = 'observed' | 'estimated' | 'exploratory';

export interface SlotDef {
  id: string;
  exactDate?: boolean;
  title: string;
  group: LayerGroup;
  sensor: Sensor;
  /** Semantic epistemic badge used across layer legends and boundary labels. */
  classification?: LayerClassification;
  /** What the layer physically represents — shown in the legend. */
  meaning: string;
  /** Short plain-language explanation shown in layer inspector tooltips. */
  tooltip?: string;
  expectedUnits: string | null;
  defaultOpacity: number;
  /** Swatch colour for the layer list / vector rendering. */
  color: string;
}

export const SLOTS: SlotDef[] = [
  {
    id: 'nisar-hh-land-water-candidate',
    exactDate: true,
    title: 'Exploratory NISAR HH brightness transition',
    group: 'sensor',
    sensor: 'NISAR',
    classification: 'exploratory',
    meaning: 'Exploratory candidate; waterline comparability failed, not a validated shoreline',
    tooltip: 'Otsu threshold applied to NISAR L-band HH backscatter. Most crossings fall ~38–40 m landward of expected ocean waterlines.',
    expectedUnits: 'm',
    defaultOpacity: 1,
    color: '#d9822b',
  },
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
    id: 'physics-s2-ndwi',
    exactDate: true,
    title: 'Raw NDWI waterline',
    group: 'sensor',
    sensor: 'SENTINEL-2',
    meaning: 'Cloud-masked optical crossing at acquisition',
    expectedUnits: 'm',
    defaultOpacity: 1,
    color: '#fbc981',
  },
  {
    id: 'physics-s2-tide',
    exactDate: true,
    title: 'Tide-corrected waterline',
    group: 'sensor',
    sensor: 'SENTINEL-2',
    meaning: 'NDWI crossing normalized to Duck mean high water',
    expectedUnits: 'm',
    defaultOpacity: 1,
    color: '#88bae8',
  },
  {
    id: 'physics-s2-mndwi',
    exactDate: true,
    title: 'Raw MNDWI waterline',
    group: 'sensor',
    sensor: 'SENTINEL-2',
    meaning: 'Cloud-masked green and SWIR crossing at 20 m',
    expectedUnits: 'm',
    defaultOpacity: 1,
    color: '#cfbb87',
  },
  {
    id: 'physics-s2-setup',
    exactDate: true,
    title: 'Wave setup sensitivity',
    group: 'sensor',
    sensor: 'SENTINEL-2',
    meaning: 'Experimental tide and mean-setup comparison',
    expectedUnits: 'm',
    defaultOpacity: 1,
    color: '#dca8f0',
  },
  {
    id: 'radar-disagreement',
    title: 'Radar directional disagreement',
    group: 'sensor',
    sensor: 'OTHER',
    meaning: 'Opposite NISAR HH and Sentinel-1 VV changes across separately timed pairs',
    expectedUnits: 'flag',
    defaultOpacity: 0.65,
    color: '#ec8c7e',
  },
  {
    id: 's1-vv-change',
    title: 'Sentinel-1 VV backscatter change',
    group: 'sensor',
    sensor: 'SENTINEL-1',
    meaning: 'Repeat-pass Track 106 VV difference (Oct 16 − Jun 30, 2026)',
    expectedUnits: 'dB',
    defaultOpacity: 0.75,
    color: '#9ba9ef',
  },
  {
    id: 's1-vh-change',
    title: 'Sentinel-1 VH backscatter change',
    group: 'sensor',
    sensor: 'SENTINEL-1',
    meaning: 'Repeat-pass Track 106 VH difference (Oct 16 − Jun 30, 2026)',
    expectedUnits: 'dB',
    defaultOpacity: 0.75,
    color: '#8290db',
  },
  {
    id: 's2-ndwi-change',
    title: 'Sentinel-2 NDWI change',
    group: 'sensor',
    sensor: 'SENTINEL-2',
    meaning: 'Clear-sky optical NDWI difference (Oct 16 − Jun 18, 2026)',
    expectedUnits: 'index',
    defaultOpacity: 0.75,
    color: '#c3cf9e',
  },
  {
    id: 'all-sensor-overlap',
    title: '4-sensor joint overlap mask (168 cells)',
    group: 'measured',
    sensor: 'OTHER',
    meaning: '10 m cells where NISAR, LiDAR, S1 & S2 all have valid change',
    expectedUnits: 'flag',
    defaultOpacity: 0.75,
    color: '#5bd3a5',
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
