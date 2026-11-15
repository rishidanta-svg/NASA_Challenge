/**
 * Idempotent synchronisation of POLTERGEIST scientific sources/layers onto a
 * MapLibre map. Called on every relevant state change and after every
 * basemap style load (setStyle wipes custom layers), so overlays survive
 * basemap switching.
 */
import maplibregl, { type Map as MLMap, type GeoJSONSource } from 'maplibre-gl';
import mlcontour from 'maplibre-contour';
import type { FeatureCollection } from 'geojson';
import { apiUrl } from '../api/client';
import { mockGeoJson, mockImageDataUrl, MOCK_PREFIX } from '../api/mock';
import type { LayerDescriptor, StudyArea, TransectSummary } from '../api/schemas';
import { FRF_Y_RANGE_M } from '../config/geo';
import { SLOTS, type SlotDef } from '../config/slots';
import { frfCrossShoreLine } from '../lib/frf';
import { isMockDescriptor } from '../lib/layers';
import { AWS_TERRAIN_ATTRIBUTION, AWS_TERRARIUM_MAXZOOM, AWS_TERRARIUM_URL } from '../lib/terrarium';
import type { MapMode, SlotUiState } from '../state/store';

export const ID = {
  demHill: 'plg-dem-hillshade',
  demTerrain: 'plg-dem-terrain',
  hillshade: 'plg-hillshade',
  hillshadeLidar: 'plg-hillshade-lidar',
  contours: 'plg-contours',
  contourLine: 'plg-contour-line',
  contourLabel: 'plg-contour-label',
  study: 'plg-study',
  studyFill: 'plg-study-fill',
  studyLine: 'plg-study-line',
  frfRef: 'plg-frf-ref',
  frfRefLine: 'plg-frf-ref-line',
  frfRefLabel: 'plg-frf-ref-label',
  transects: 'plg-transects',
  transectLine: 'plg-transect-line',
  transectHit: 'plg-transect-hit',
  transectLabelSrc: 'plg-transect-labels',
  transectLabel: 'plg-transect-label',
} as const;

export const FONT = ['Noto Sans Regular'];

export interface SyncContext {
  tone: 'standard' | 'light' | 'dark';
  mode: MapMode;
  exaggeration: number;
  hillshade: SlotUiState;
  contours: boolean;
  terrainDem: LayerDescriptor | null; // null → AWS
  resolved: Record<string, LayerDescriptor | null>;
  slots: Record<string, SlotUiState>;
  studyArea: StudyArea | null;
  transects: TransectSummary[] | null;
  showTransects: boolean;
  showStudyArea: boolean;
  selectedTransectId: string | null;
}

// ---------------- contour protocol (singleton) ----------------
let demSource: InstanceType<typeof mlcontour.DemSource> | null = null;
function contourTilesUrl(): string {
  if (!demSource) {
    demSource = new mlcontour.DemSource({ url: AWS_TERRARIUM_URL, encoding: 'terrarium', maxzoom: AWS_TERRARIUM_MAXZOOM, worker: true });
    demSource.setupMaplibre(maplibregl);
  }
  return demSource.contourProtocolUrl({
    multiplier: 1,
    // [minor, major] interval in metres, by zoom
    thresholds: { 11: [20, 100], 12: [10, 50], 13: [5, 25], 14: [2, 10], 15: [1, 5] },
    elevationKey: 'ele',
    levelKey: 'level',
    contourLayer: 'contours',
  });
}

// ---------------- helpers ----------------
const tracked = new WeakMap<MLMap, Map<string, string>>();
function trackedFor(map: MLMap): Map<string, string> {
  let t = tracked.get(map);
  if (!t) tracked.set(map, (t = new Map()));
  return t;
}
/** Must be called on every style.load: the new style has none of our sources. */
export function resetTracking(map: MLMap): void {
  tracked.delete(map);
}

function firstSymbolId(map: MLMap): string | undefined {
  return map.getStyle().layers?.find((l) => l.type === 'symbol' && !l.id.startsWith('plg-'))?.id;
}

function setVis(map: MLMap, id: string, on: boolean) {
  if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
}

function removeLayers(map: MLMap, ids: string[]) {
  for (const id of ids) if (map.getLayer(id)) map.removeLayer(id);
}

function setGeoJson(map: MLMap, id: string, data: FeatureCollection) {
  const src = map.getSource(id) as GeoJSONSource | undefined;
  if (src) src.setData(data);
  else map.addSource(id, { type: 'geojson', data });
}

const resolveUrl = (u: string) => (u.startsWith(MOCK_PREFIX) ? u : apiUrl(u));

// ---------------- terrain ----------------
function syncTerrain(map: MLMap, ctx: SyncContext, before: string | undefined) {
  const awsSpec = {
    type: 'raster-dem' as const,
    tiles: [AWS_TERRARIUM_URL],
    encoding: 'terrarium' as const,
    tileSize: 256,
    maxzoom: AWS_TERRARIUM_MAXZOOM,
    attribution: AWS_TERRAIN_ATTRIBUTION,
  };
  // Separate sources for hillshade and terrain (recommended by MapLibre to avoid tile-size contention).
  if (!map.getSource(ID.demHill)) map.addSource(ID.demHill, awsSpec);
  if (!map.getSource(ID.demTerrain)) map.addSource(ID.demTerrain, awsSpec);

  const shadow = ctx.tone === 'light' ? '#5c5c5c' : '#04080c';
  if (!map.getLayer(ID.hillshade)) {
    map.addLayer(
      {
        id: ID.hillshade,
        type: 'hillshade',
        source: ID.demHill,
        paint: {
          'hillshade-exaggeration': ctx.hillshade.opacity,
          'hillshade-shadow-color': shadow,
          'hillshade-highlight-color': '#ffffff',
          'hillshade-accent-color': shadow,
          'hillshade-illumination-anchor': 'map',
        },
      },
      before,
    );
  }
  map.setPaintProperty(ID.hillshade, 'hillshade-exaggeration', ctx.hillshade.opacity);
  setVis(map, ID.hillshade, ctx.hillshade.visible);

  // Optional high-resolution DEM (LiDAR raster_dem from the data agent).
  const t = trackedFor(map);
  const lidarId = ctx.terrainDem ? `plg-dem-${ctx.terrainDem.id}` : null;
  const prev = t.get('__dem');
  if (prev && prev !== lidarId) {
    if (map.getTerrain()?.source === prev) map.setTerrain(null);
    removeLayers(map, [ID.hillshadeLidar]);
    if (map.getSource(prev)) map.removeSource(prev);
    t.delete('__dem');
  }
  if (ctx.terrainDem && lidarId && !map.getSource(lidarId)) {
    const d = ctx.terrainDem;
    map.addSource(lidarId, {
      type: 'raster-dem',
      tiles: (d.tiles ?? []).map(resolveUrl),
      encoding: d.encoding ?? 'terrarium',
      tileSize: d.tile_size ?? 256,
      ...(d.bounds ? { bounds: d.bounds } : {}),
      ...(d.minzoom != null ? { minzoom: d.minzoom } : {}),
      ...(d.maxzoom != null ? { maxzoom: d.maxzoom } : {}),
      attribution: d.provenance.source,
    });
    map.addLayer(
      {
        id: ID.hillshadeLidar,
        type: 'hillshade',
        source: lidarId,
        paint: { 'hillshade-exaggeration': 0.5, 'hillshade-shadow-color': shadow, 'hillshade-illumination-anchor': 'map' },
      },
      before,
    );
    t.set('__dem', lidarId);
  }
  if (map.getLayer(ID.hillshadeLidar)) setVis(map, ID.hillshadeLidar, ctx.hillshade.visible);

  const want = ctx.mode === '3d' ? (lidarId ?? ID.demTerrain) : null;
  const cur = map.getTerrain();
  if (!want) {
    if (cur) map.setTerrain(null);
  } else if (!cur || cur.source !== want || cur.exaggeration !== ctx.exaggeration) {
    map.setTerrain({ source: want, exaggeration: ctx.exaggeration });
  }
}

function syncContours(map: MLMap, ctx: SyncContext, before: string | undefined) {
  if (!ctx.contours) {
    setVis(map, ID.contourLine, false);
    setVis(map, ID.contourLabel, false);
    return;
  }
  if (!map.getSource(ID.contours)) {
    map.addSource(ID.contours, {
      type: 'vector',
      tiles: [contourTilesUrl()],
      maxzoom: AWS_TERRARIUM_MAXZOOM,
      attribution: AWS_TERRAIN_ATTRIBUTION,
    });
  }
  const color = ctx.tone === 'light' ? '#6b4f2f' : '#e7d9b8';
  if (!map.getLayer(ID.contourLine)) {
    map.addLayer(
      {
        id: ID.contourLine,
        type: 'line',
        source: ID.contours,
        'source-layer': 'contours',
        minzoom: 11,
        paint: {
          'line-color': color,
          'line-opacity': ['match', ['get', 'level'], 1, 0.75, 0.35],
          'line-width': ['match', ['get', 'level'], 1, 1.1, 0.5],
        },
      },
      before,
    );
    map.addLayer({
      id: ID.contourLabel,
      type: 'symbol',
      source: ID.contours,
      'source-layer': 'contours',
      minzoom: 13,
      filter: ['>', ['get', 'level'], 0],
      layout: {
        'symbol-placement': 'line',
        'text-field': ['concat', ['number-format', ['get', 'ele'], {}], ' m'],
        'text-font': FONT,
        'text-size': 10,
      },
      paint: { 'text-color': color, 'text-halo-color': ctx.tone === 'light' ? '#ffffff' : '#0b1118', 'text-halo-width': 1.2 },
    });
  }
  setVis(map, ID.contourLine, true);
  setVis(map, ID.contourLabel, true);
}

// ---------------- reference layers ----------------
function syncReference(map: MLMap, ctx: SyncContext) {
  if (ctx.studyArea) {
    setGeoJson(map, ID.study, { type: 'FeatureCollection', features: [ctx.studyArea as GeoJSON.Feature] });
    if (!map.getLayer(ID.studyFill)) {
      map.addLayer({ id: ID.studyFill, type: 'fill', source: ID.study, paint: { 'fill-color': '#65dfce', 'fill-opacity': 0.06 } });
      map.addLayer({
        id: ID.studyLine,
        type: 'line',
        source: ID.study,
        paint: { 'line-color': '#65dfce', 'line-width': 2, 'line-dasharray': [3, 2] },
      });
    }
    setVis(map, ID.studyFill, ctx.showStudyArea);
    setVis(map, ID.studyLine, ctx.showStudyArea);
  }

  if (!map.getSource(ID.frfRef)) {
    const features: GeoJSON.Feature[] = FRF_Y_RANGE_M.map((y) => ({
      type: 'Feature',
      properties: { label: `FRF y = ${y} m` },
      geometry: { type: 'LineString', coordinates: frfCrossShoreLine(y, -60, 320) },
    }));
    map.addSource(ID.frfRef, { type: 'geojson', data: { type: 'FeatureCollection', features } });
    map.addLayer({
      id: ID.frfRefLine,
      type: 'line',
      source: ID.frfRef,
      minzoom: 13,
      paint: { 'line-color': '#edbf7c', 'line-width': 1.2, 'line-dasharray': [1, 2] },
    });
    map.addLayer({
      id: ID.frfRefLabel,
      type: 'symbol',
      source: ID.frfRef,
      minzoom: 15,
      layout: { 'symbol-placement': 'line', 'text-field': ['get', 'label'], 'text-font': FONT, 'text-size': 10, 'text-offset': [0, -0.8] },
      paint: { 'text-color': '#edbf7c', 'text-halo-color': '#0b1118', 'text-halo-width': 1.4 },
    });
  }
  setVis(map, ID.frfRefLine, ctx.showStudyArea);
  setVis(map, ID.frfRefLabel, ctx.showStudyArea);

  if (ctx.transects) {
    const sel = ctx.selectedTransectId ?? '';
    setGeoJson(map, ID.transects, {
      type: 'FeatureCollection',
      features: ctx.transects.map((t) => ({ ...t, properties: { ...t.properties } }) as GeoJSON.Feature),
    });
    setGeoJson(map, ID.transectLabelSrc, {
      type: 'FeatureCollection',
      features: ctx.transects.map((t) => ({
        type: 'Feature',
        properties: { id: t.properties.id, label: t.properties.id },
        geometry: { type: 'Point', coordinates: t.geometry.coordinates[0]! },
      })),
    });
    if (!map.getLayer(ID.transectLine)) {
      map.addLayer({
        id: ID.transectLine,
        type: 'line',
        source: ID.transects,
        minzoom: 13,
        layout: { 'line-cap': 'round' },
        paint: { 'line-color': '#c9e0d2', 'line-width': 1.4, 'line-opacity': 0.85 },
      });
      map.addLayer({
        id: ID.transectHit,
        type: 'line',
        source: ID.transects,
        minzoom: 13,
        paint: { 'line-color': '#000000', 'line-width': 16, 'line-opacity': 0 },
      });
      map.addLayer({
        id: ID.transectLabel,
        type: 'symbol',
        source: ID.transectLabelSrc,
        minzoom: 15,
        layout: { 'text-field': ['get', 'label'], 'text-font': FONT, 'text-size': 10, 'text-anchor': 'right', 'text-offset': [-0.6, 0] },
        paint: { 'text-color': '#c9e0d2', 'text-halo-color': '#0b1118', 'text-halo-width': 1.4 },
      });
    }
    map.setPaintProperty(ID.transectLine, 'line-color', ['case', ['==', ['get', 'id'], sel], '#7ff5de', '#c9e0d2']);
    map.setPaintProperty(ID.transectLine, 'line-width', ['case', ['==', ['get', 'id'], sel], 3.2, 1.4]);
    map.setPaintProperty(ID.transectLabel, 'text-color', ['case', ['==', ['get', 'id'], sel], '#7ff5de', '#c9e0d2']);
    for (const id of [ID.transectLine, ID.transectHit, ID.transectLabel]) setVis(map, id, ctx.showTransects);
  }
}

// ---------------- overlay slots ----------------
function slotIds(slot: string) {
  const src = `plg-slot-${slot}`;
  return { src, raster: `${src}-raster`, line: `${src}-line`, fill: `${src}-fill` };
}

function syncSlot(map: MLMap, def: SlotDef, desc: LayerDescriptor | null, ui: SlotUiState, rasterBefore: string | undefined, vectorBefore: string | undefined) {
  const t = trackedFor(map);
  const ids = slotIds(def.id);
  if (t.get(def.id) !== (desc?.id ?? undefined)) {
    removeLayers(map, [ids.raster, ids.line, ids.fill]);
    if (map.getSource(ids.src)) map.removeSource(ids.src);
    t.delete(def.id);
  }
  if (!desc) return;
  const mock = isMockDescriptor(desc);
  const dashed = desc.inferred || mock;

  if (!map.getSource(ids.src)) {
    if (desc.kind === 'raster_xyz') {
      map.addSource(ids.src, {
        type: 'raster',
        tiles: (desc.tiles ?? []).map(resolveUrl),
        tileSize: desc.tile_size ?? 256,
        ...(desc.bounds ? { bounds: desc.bounds } : {}),
        ...(desc.minzoom != null ? { minzoom: desc.minzoom } : {}),
        ...(desc.maxzoom != null ? { maxzoom: desc.maxzoom } : {}),
        attribution: desc.provenance.source,
      });
      map.addLayer({ id: ids.raster, type: 'raster', source: ids.src, paint: { 'raster-resampling': 'nearest' } }, rasterBefore);
    } else if (desc.kind === 'image') {
      const url = desc.url!.startsWith(MOCK_PREFIX) ? mockImageDataUrl(desc.url!) : apiUrl(desc.url!);
      map.addSource(ids.src, { type: 'image', url, coordinates: desc.coordinates! });
      map.addLayer({ id: ids.raster, type: 'raster', source: ids.src, paint: { 'raster-resampling': 'nearest', 'raster-fade-duration': 0 } }, rasterBefore);
    } else if (desc.kind === 'geojson') {
      const data = desc.url!.startsWith(MOCK_PREFIX) ? mockGeoJson(desc.url!) : apiUrl(desc.url!);
      map.addSource(ids.src, { type: 'geojson', data, attribution: desc.provenance.source });
      map.addLayer(
        {
          id: ids.fill,
          type: 'fill',
          source: ids.src,
          filter: ['==', ['geometry-type'], 'Polygon'],
          paint: { 'fill-color': def.color, 'fill-opacity': 0.25 },
        },
        vectorBefore,
      );
      map.addLayer(
        {
          id: ids.line,
          type: 'line',
          source: ids.src,
          filter: ['in', ['geometry-type'], ['literal', ['LineString', 'MultiLineString', 'Polygon', 'MultiPolygon']]],
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: { 'line-color': def.color, 'line-width': 2.4, ...(dashed ? { 'line-dasharray': [2, 1.5] } : {}) },
        },
        vectorBefore,
      );
    }
    // raster_dem descriptors are handled as terrain sources, not overlays.
    t.set(def.id, desc.id);
  }
  if (map.getLayer(ids.raster)) {
    map.setPaintProperty(ids.raster, 'raster-opacity', ui.opacity);
    setVis(map, ids.raster, ui.visible);
  }
  if (map.getLayer(ids.line)) {
    map.setPaintProperty(ids.line, 'line-opacity', ui.opacity);
    setVis(map, ids.line, ui.visible);
  }
  if (map.getLayer(ids.fill)) {
    map.setPaintProperty(ids.fill, 'fill-opacity', ui.opacity * 0.3);
    setVis(map, ids.fill, ui.visible);
  }
}

// ---------------- entry point ----------------
export function syncScientific(map: MLMap, ctx: SyncContext): void {
  if (!map.isStyleLoaded() && !map.getStyle()?.layers?.length) return;
  const symbolBefore = firstSymbolId(map);
  syncTerrain(map, ctx, symbolBefore);
  syncContours(map, ctx, symbolBefore);
  syncReference(map, ctx);
  const vectorBefore = map.getLayer(ID.studyFill) ? ID.studyFill : undefined;
  for (const def of SLOTS) {
    const ui = ctx.slots[def.id] ?? { visible: false, opacity: def.defaultOpacity };
    syncSlot(map, def, ctx.resolved[def.id] ?? null, ui, symbolBefore, vectorBefore);
  }
  try {
    map.setSky({
      'sky-color': '#0b1118',
      'horizon-color': '#1d3646',
      'fog-color': '#0e1720',
      'sky-horizon-blend': 0.6,
      'horizon-fog-blend': 0.6,
      'fog-ground-blend': 0.85,
    });
  } catch {
    /* sky unsupported in this style/version */
  }
}

export const INTERACTIVE_LAYERS = [ID.transectHit];
