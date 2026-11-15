import { create } from 'zustand';
import type { Sourced } from '../api/client';
import type { Acquisition, LayerDescriptor, StudyArea, TerrainChange, TransectSummary } from '../api/schemas';
import { DEFAULT_BASEMAP, type BasemapId } from '../config/basemaps';
import { SLOTS } from '../config/slots';

export type MapMode = '2d' | '3d';
export type DrawerId = 'left' | 'right' | null;

export interface SlotUiState {
  visible: boolean;
  opacity: number;
}

export interface CameraState {
  zoom: number;
  pitch: number;
  bearing: number;
}

export interface AppState {
  // Map display
  basemap: BasemapId;
  mode: MapMode;
  exaggeration: number;
  hillshade: SlotUiState;
  contours: boolean;
  /** 'aws' or the id of a raster_dem LayerDescriptor (e.g. LiDAR epoch). */
  terrainSource: string;
  slots: Record<string, SlotUiState>;
  showTransects: boolean;
  showStudyArea: boolean;
  camera: CameraState;
  cursor: { lng: number; lat: number } | null;
  mapErrors: string[];

  // Timeline
  date: string;
  compare: boolean;
  compareDate: string;
  swipe: number;

  // Selection
  selectedTransectId: string | null;
  inspected: { lng: number; lat: number } | null;

  // Data
  studyArea: Sourced<StudyArea> | null;
  layers: Sourced<LayerDescriptor[]> | null;
  acquisitions: Sourced<Acquisition[]> | null;
  transects: Sourced<TransectSummary[]> | null;
  terrainChange: Sourced<TerrainChange> | null;

  // Layout
  drawer: DrawerId;
  bottomOpen: boolean;

  set: (p: Partial<AppState>) => void;
  setSlot: (id: string, p: Partial<SlotUiState>) => void;
  pushMapError: (msg: string) => void;
}

const initialSlots = Object.fromEntries(
  SLOTS.map((s) => [s.id, { visible: false, opacity: s.defaultOpacity }]),
);

export const useApp = create<AppState>((set) => ({
  basemap: DEFAULT_BASEMAP,
  mode: '2d',
  exaggeration: 1,
  hillshade: { visible: false, opacity: 0.45 },
  contours: false,
  terrainSource: 'lidar-dem-june',
  slots: initialSlots,
  showTransects: false,
  showStudyArea: true,
  camera: { zoom: 0, pitch: 0, bearing: 0 },
  cursor: null,
  mapErrors: [],

  date: '2026-06-18',
  compare: false,
  compareDate: '2026-10-16',
  swipe: 0.5,

  selectedTransectId: null,
  inspected: null,

  studyArea: null,
  layers: null,
  acquisitions: null,
  transects: null,
  terrainChange: null,

  drawer: null,
  bottomOpen: false,

  set: (p) => set(p),
  setSlot: (id, p) => set((s) => ({ slots: { ...s.slots, [id]: { ...s.slots[id]!, ...p } } })),
  pushMapError: (msg) =>
    set((s) => (s.mapErrors.includes(msg) ? s : { mapErrors: [...s.mapErrors.slice(-4), msg] })),
}));
