import { useEffect, useMemo, useRef } from 'react';
import maplibregl, { type Map as MLMap, type MapMouseEvent } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { BASEMAPS, basemapUrl } from '../config/basemaps';
import { REGIONAL_VIEW, STUDY_BBOX } from '../config/geo';
import { SLOTS } from '../config/slots';
import { demDescriptors, resolveSlot } from '../lib/layers';
import {
  flyToStudyArea,
  registerMap,
  resetCamera,
  syncSecondary,
} from './registry';
import { ID, INTERACTIVE_LAYERS, resetTracking, syncScientific, type SyncContext } from './scientific';
import { useApp } from '../state/store';

export function MapView() {
  const primaryRef = useRef<HTMLDivElement | null>(null);
  const secondaryRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MLMap | null>(null);
  const compareMapRef = useRef<MLMap | null>(null);
  const markerRef = useRef<maplibregl.Marker | null>(null);
  const styleUrlRef = useRef<string>('');
  const compareStyleUrlRef = useRef<string>('');

  const {
    basemap,
    mode,
    exaggeration,
    hillshade,
    contours,
    terrainSource,
    slots,
    showTransects,
    showStudyArea,
    date,
    compare,
    compareDate,
    swipe,
    selectedTransectId,
    inspected,
    studyArea,
    layers,
    transects,
    set,
    pushMapError,
  } = useApp();

  const tone = useMemo(
    () => BASEMAPS.find((b) => b.id === basemap)?.tone ?? 'standard',
    [basemap],
  );

  const dems = useMemo(() => demDescriptors(layers?.data), [layers]);
  const terrainDem = useMemo(
    () => (terrainSource === 'aws' ? null : dems.find((d) => d.id === terrainSource) ?? null),
    [terrainSource, dems],
  );

  const resolvedPrimary = useMemo(
    () => Object.fromEntries(SLOTS.map((s) => [s.id, resolveSlot(layers?.data, s.id, date)])),
    [layers, date],
  );

  const resolvedCompare = useMemo(
    () => Object.fromEntries(SLOTS.map((s) => [s.id, resolveSlot(layers?.data, s.id, compareDate)])),
    [layers, compareDate],
  );

  const ctxPrimary: SyncContext = useMemo(
    () => ({
      tone,
      mode,
      exaggeration,
      hillshade,
      contours,
      terrainDem,
      resolved: resolvedPrimary,
      slots,
      studyArea: studyArea?.data ?? null,
      transects: transects?.data ?? null,
      showTransects,
      showStudyArea,
      selectedTransectId,
    }),
    [
      tone,
      mode,
      exaggeration,
      hillshade,
      contours,
      terrainDem,
      resolvedPrimary,
      slots,
      studyArea,
      transects,
      showTransects,
      showStudyArea,
      selectedTransectId,
    ],
  );

  const ctxCompare: SyncContext = useMemo(
    () => ({
      ...ctxPrimary,
      resolved: resolvedCompare,
      terrainDem: terrainSource === 'aws' ? null : resolveSlot(dems, 'lidar-dem', compareDate),
    }),
    [ctxPrimary, resolvedCompare, terrainSource, dems, compareDate],
  );

  const ctxPrimaryRef = useRef(ctxPrimary);
  ctxPrimaryRef.current = ctxPrimary;
  const ctxCompareRef = useRef(ctxCompare);
  ctxCompareRef.current = ctxCompare;

  // Initialize primary MapLibre instance
  useEffect(() => {
    if (!primaryRef.current || mapRef.current) return;
    const initialStyle = basemapUrl(basemap);
    styleUrlRef.current = initialStyle;

    const map = new maplibregl.Map({
      container: primaryRef.current,
      style: initialStyle,
      bounds: STUDY_BBOX,
      fitBoundsOptions: { padding: {left: primaryRef.current.clientWidth > 850 ? 390 : 36,right:36,top:80,bottom:80} },
      pitch: 0,
      bearing: 0,
      maxPitch: 82,
      attributionControl: false,
    });
    mapRef.current = map;
    registerMap('primary', map);

    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-right');
    map.addControl(new maplibregl.ScaleControl({ maxWidth: 140, unit: 'metric' }), 'bottom-right');
    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right');

    const syncCam = () => {
      set({
        camera: {
          zoom: +map.getZoom().toFixed(2),
          pitch: Math.round(map.getPitch()),
          bearing: Math.round(map.getBearing()),
        },
      });
      syncSecondary();
    };

    syncCam();
    map.on('load', () => {
      syncScientific(map, ctxPrimaryRef.current);
      syncCam();
    });

    map.on('style.load', () => {
      resetTracking(map);
      syncScientific(map, ctxPrimaryRef.current);
    });

    map.on('move', syncCam);

    map.on('mousemove', (e: MapMouseEvent) => {
      set({ cursor: { lng: e.lngLat.lng, lat: e.lngLat.lat } });
      const hits = map.getLayer(ID.transectHit)
        ? map.queryRenderedFeatures(e.point, { layers: [...INTERACTIVE_LAYERS] })
        : [];
      map.getCanvas().style.cursor = hits.length > 0 ? 'pointer' : '';
    });

    map.on('mouseout', () => set({ cursor: null }));

    map.on('click', (e: MapMouseEvent) => {
      const hits = map.getLayer(ID.transectHit)
        ? map.queryRenderedFeatures(e.point, { layers: [...INTERACTIVE_LAYERS] })
        : [];
      const hitId = hits[0]?.properties?.id;
      if (typeof hitId === 'string' && hitId) {
        set({ selectedTransectId: hitId, bottomOpen: true });
        return;
      }
      set({ inspected: { lng: e.lngLat.lng, lat: e.lngLat.lat } });
    });

    map.on('error', (ev) => {
      const msg = ev?.error?.message;
      if (msg && !msg.includes('AbortError')) pushMapError(msg);
    });

    return () => {
      markerRef.current?.remove();
      markerRef.current = null;
      registerMap('primary', null);
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Initialize / teardown secondary compare map
  useEffect(() => {
    if (!compare || !secondaryRef.current) {
      if (compareMapRef.current) {
        registerMap('secondary', null);
        compareMapRef.current.remove();
        compareMapRef.current = null;
      }
      return;
    }
    if (compareMapRef.current) return;
    const style = basemapUrl(basemap);
    compareStyleUrlRef.current = style;
    const p = mapRef.current;
    const m2 = new maplibregl.Map({
      container: secondaryRef.current,
      style,
      center: p ? p.getCenter() : REGIONAL_VIEW.center,
      zoom: p ? p.getZoom() : REGIONAL_VIEW.zoom,
      bearing: p ? p.getBearing() : 0,
      pitch: p ? p.getPitch() : 0,
      interactive: false,
      attributionControl: false,
    });
    compareMapRef.current = m2;
    registerMap('secondary', m2);
    m2.on('load', () => syncScientific(m2, ctxCompareRef.current));
    m2.on('style.load', () => {
      resetTracking(m2);
      syncScientific(m2, ctxCompareRef.current);
    });
    return () => {
      registerMap('secondary', null);
      m2.remove();
      compareMapRef.current = null;
    };
  }, [compare, basemap]);

  // Switch basemap style while preserving overlays
  useEffect(() => {
    const url = basemapUrl(basemap);
    if (mapRef.current && styleUrlRef.current !== url) {
      styleUrlRef.current = url;
      mapRef.current.setStyle(url);
    }
    if (compareMapRef.current && compareStyleUrlRef.current !== url) {
      compareStyleUrlRef.current = url;
      compareMapRef.current.setStyle(url);
    }
  }, [basemap]);

  // Sync scientific layers on state changes
  useEffect(() => {
    if (mapRef.current) syncScientific(mapRef.current, ctxPrimary);
  }, [ctxPrimary]);

  useEffect(() => {
    if (compareMapRef.current) syncScientific(compareMapRef.current, ctxCompare);
  }, [ctxCompare]);

  // Smooth camera transition when toggling 2D <-> 3D
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (mode === '3d' && map.getPitch() < 15) {
      map.easeTo({ pitch: 58, bearing: -18, duration: 900 });
    } else if (mode === '2d' && map.getPitch() > 0) {
      map.easeTo({ pitch: 0, bearing: 0, duration: 700 });
    }
  }, [mode]);

  // Clicked location marker
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (!inspected) {
      markerRef.current?.remove();
      markerRef.current = null;
      return;
    }
    if (!markerRef.current) {
      markerRef.current = new maplibregl.Marker({ color: '#333333' });
    }
    markerRef.current.setLngLat([inspected.lng, inspected.lat]).addTo(map);
  }, [inspected]);


  return (
    <div className="map-stage" data-testid="map-stage">
      <div ref={primaryRef} className="map-canvas-wrap" />
      {compare && (
        <>
          <div
            ref={secondaryRef}
            className="map-secondary-wrap"
            style={{ clipPath: `inset(0 0 0 ${(swipe * 100).toFixed(1)}%)` }}
          />
          <div
            className="swipe-handle"
            role="slider"
            tabIndex={0}
            aria-label="Survey comparison divider"
            aria-valuemin={5}
            aria-valuemax={95}
            aria-valuenow={Math.round(swipe*100)}
            onKeyDown={e => {
              if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
                e.preventDefault();set({swipe:Math.max(.05,Math.min(.95,swipe+(e.key === 'ArrowLeft' ? -.05 : .05)))});
              }
            }}
            style={{ left: `${(swipe * 100).toFixed(1)}%` }}
            onPointerDown={(e) => {
              e.preventDefault();
              const target = e.currentTarget;
              target.setPointerCapture(e.pointerId);
              const parent = target.parentElement;
              const onMove = (ev: PointerEvent) => {
                if (!parent) return;
                const r = parent.getBoundingClientRect();
                const ratio = Math.min(0.95, Math.max(0.05, (ev.clientX - r.left) / r.width));
                set({ swipe: ratio });
              };
              const onUp = () => {
                window.removeEventListener('pointermove', onMove);
                window.removeEventListener('pointerup', onUp);
              };
              window.addEventListener('pointermove', onMove);
              window.addEventListener('pointerup', onUp);
            }}
          >
            <span className="swipe-tag">
              {date} ◀ ▶ {compareDate}
            </span>
          </div>
        </>
      )}

      {slots['nisar-hh-land-water-candidate']?.visible && resolvedPrimary['nisar-hh-land-water-candidate'] && <div className="product-notice">Exploratory NISAR transition · not a validated shoreline</div>}
      <div className="earth-map-controls" aria-label="Map view controls">
        <div className="view-mode" role="group" aria-label="Map dimension mode">
          <button aria-pressed={mode === '2d'} onClick={() => set({mode:'2d'})} data-testid="mode-2d">2D</button>
          <button aria-pressed={mode === '3d'} onClick={() => set({mode:'3d'})} data-testid="mode-3d">3D</button>
        </div>
        <button onClick={flyToStudyArea} title="Return to study area" aria-label="Return to study area">⌖</button>
        <button onClick={resetCamera} title="Reset map, north up" aria-label="Reset map">N ↑</button>
      </div>
      {mode === '3d' && <div className="terrain-caption">{terrainDem ? 'Surveyed beach terrain' : 'Regional terrain'} · {exaggeration === 1 ? 'true-scale height' : `height enhanced ×${exaggeration}`}</div>}

    </div>
  );
}
