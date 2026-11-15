import { useEffect, useMemo, useRef } from 'react';
import maplibregl, { type Map as MLMap, type MapMouseEvent } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { BASEMAPS, basemapUrl } from '../config/basemaps';
import { ANALYSIS_CRS, DISPLAY_CRS, REGIONAL_VIEW, STUDY_BBOX } from '../config/geo';
import { SLOTS } from '../config/slots';
import { lngLatToFrf, lngLatToUtm18N } from '../lib/frf';
import { demDescriptors, resolveSlot } from '../lib/layers';
import {
  flyToDuck,
  flyToRegional,
  flyToStudyArea,
  registerMap,
  resetCamera,
  setBearing,
  setPitch,
  syncSecondary,
  zoomBy,
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
    camera,
    cursor,
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
    }),
    [ctxPrimary, resolvedCompare],
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
      center: REGIONAL_VIEW.center,
      zoom: REGIONAL_VIEW.zoom,
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

    map.on('load', () => {
      syncScientific(map, ctxPrimaryRef.current);
      syncCam();
      // Smoothly frame the Duck FRF study area after initial regional context load
      map.fitBounds(STUDY_BBOX, { padding: 65, duration: 1500 });
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
      markerRef.current = new maplibregl.Marker({ color: '#65dfce' });
    }
    markerRef.current.setLngLat([inspected.lng, inspected.lat]).addTo(map);
  }, [inspected]);

  const activeCoord = cursor ?? inspected;
  const coordInfo = useMemo(() => {
    if (!activeCoord) return null;
    const [utmE, utmN] = lngLatToUtm18N(activeCoord.lng, activeCoord.lat);
    const [frfX, frfY] = lngLatToFrf(activeCoord.lng, activeCoord.lat);
    return {
      lng: activeCoord.lng,
      lat: activeCoord.lat,
      utmE,
      utmN,
      frfX,
      frfY,
      pinned: !cursor && !!inspected,
    };
  }, [activeCoord, cursor, inspected]);

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

      {/* Top HUD: navigation + camera controls in a single wrapping flex bar */}
      <div className="map-hud-top-left">
        <div className="map-pill">
          <strong style={{ color: 'var(--cyan)' }}>DUCK FRF</strong>
          <span className="muted">·</span>
          <span>{date}</span>
          <span className="muted">·</span>
          <span>{mode.toUpperCase()}</span>
          {mode === '3d' && (
            <span style={{ color: exaggeration !== 1 ? 'var(--gold)' : 'var(--muted)' }}>
              ({exaggeration}× vert · {terrainDem ? 'USACE LiDAR ~1 m' : 'AWS regional DEM'})
            </span>
          )}
        </div>
        <button className="map-pill" onClick={flyToStudyArea} title="Fit study area (FRF y = 700–1190 m)">
          ⌖ Study Area
        </button>
        <button className="map-pill" onClick={flyToDuck} title="Zoom to Duck FRF facility & pier">
          ◈ Duck Pier
        </button>
        <button className="map-pill" onClick={flyToRegional} title="Zoom out to regional Outer Banks coastline">
          ⛶ Regional Coast
        </button>

        <div className="map-hud-camera" aria-label="Camera controls">
          <span>Z {camera.zoom.toFixed(1)}</span>
          <span className="muted">|</span>
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            Tilt
            <input
              type="range"
              min={0}
              max={75}
              step={1}
              value={camera.pitch}
              onChange={(e) => setPitch(Number(e.target.value))}
              style={{ width: 58, accentColor: 'var(--cyan)' }}
              aria-label="Camera tilt degrees"
            />
            <span>{camera.pitch}°</span>
          </label>
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            Rot
            <input
              type="range"
              min={-180}
              max={180}
              step={1}
              value={camera.bearing}
              onChange={(e) => setBearing(Number(e.target.value))}
              style={{ width: 58, accentColor: 'var(--cyan)' }}
              aria-label="Camera rotation degrees"
            />
            <span>{camera.bearing}°</span>
          </label>
          <button onClick={() => zoomBy(1)} title="Zoom in" style={{ padding: '2px 7px' }}>
            +
          </button>
          <button onClick={() => zoomBy(-1)} title="Zoom out" style={{ padding: '2px 7px' }}>
            −
          </button>
          <button onClick={resetCamera} title="Reset north-up 2D camera on study area" style={{ padding: '2px 7px' }}>
            ↺ Reset
          </button>
        </div>
      </div>

      {/* Bottom-left coordinate & CRS readout */}
      <div className="map-hud-bottom-left">
        {contours && (
          <div className="coord-bar" style={{ color: 'var(--gold)' }}>
            Contours derived from AWS regional terrain (~3–10 m source), not 1 m USACE LiDAR.
          </div>
        )}
        <div className="coord-bar" data-testid="coord-readout">
          {coordInfo ? (
            <>
              <span>
                <strong>{coordInfo.pinned ? 'PIN' : 'CURSOR'} WGS84:</strong> {coordInfo.lat.toFixed(6)}° N,{' '}
                {coordInfo.lng.toFixed(6)}° W
              </span>
              <span>
                <strong>UTM 18N ({ANALYSIS_CRS}):</strong> {coordInfo.utmE.toFixed(1)} E, {coordInfo.utmN.toFixed(1)} N m
              </span>
              <span>
                <strong>FRF:</strong> x={coordInfo.frfX.toFixed(1)} m, y={coordInfo.frfY.toFixed(1)} m
              </span>
            </>
          ) : (
            <span>
              <strong>STUDY BBOX:</strong> 36.183704°–36.188260° N, −75.753384° to −75.750335° W · Display {DISPLAY_CRS} ·
              Analysis {ANALYSIS_CRS}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
