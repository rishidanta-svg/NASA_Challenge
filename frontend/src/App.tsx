import { lazy, Suspense, useCallback, useEffect, useState } from 'react';
import { getAcquisitions, getCoastalEvidence, getLayers, getStudyArea, getTerrainChange, getTransects } from './api/client';
import { clearCache } from './api/http';
import type { CoastalEvidence } from './api/schemas';
import { BoundaryWorkspace } from './components/BoundaryWorkspace';
import { CrossSection } from './components/CrossSection';
import { GuidedTour } from './components/GuidedTour';
import { Icon } from './components/Icon';
import { Legend } from './components/Legend';
import { StudyOverview } from './components/StudyOverview';
import { MapTools } from './components/MapTools';
import { slotById } from './config/slots';
import { lngLatToFrf, lngLatToUtm18N } from './lib/frf';
import { resolveSlot } from './lib/layers';
import { MapBoundary } from './components/MapBoundary';
const MapView=lazy(()=>import('./map/MapView').then(module=>({default:module.MapView})));
import { flyToStudyArea } from './map/registry';
import { useApp } from './state/store';

type Panel = 'overview' | 'tour' | 'layers' | 'compare' | 'findings' | 'about' | null;

export function App() {
  const [panel, setPanel] = useState<Panel>('overview');
  const [refreshing, setRefreshing] = useState(false);
  const [revision,setRevision] = useState(0);
  const [coastal, setCoastal] = useState<CoastalEvidence | null>(null);
  const set = useApp((s) => s.set);
  const { bottomOpen, layers, date, slots, inspected, transects, cursor } = useApp();

  function open(next: Panel) {
    setPanel(next);
    set({ compare: next === 'compare',inspected:null,bottomOpen:false });
    if (next === 'compare') {
      const state = useApp.getState();
      Object.keys(state.slots).forEach((id) => state.setSlot(id, { visible: id === 'lidar-elevation' }));
      set({
        date: '2026-06-18',
        compareDate: '2026-10-16',
        terrainSource: state.terrainSource === 'aws' ? 'aws' : 'lidar-dem-june',
      });
    }
  }

  function showMapLayer(slotId: string, nextDate?: string, openProfile = false) {
    const state = useApp.getState();
    Object.keys(state.slots).forEach((id) => state.setSlot(id, { visible: id === slotId }));
    state.setSlot(slotId, { visible: true });
    set({
      compare: false,
      showStudyArea: true,
      ...(nextDate ? { date: nextDate } : {}),
      ...(openProfile ? { showTransects: true, bottomOpen: true } : {}),
    });
    setPanel(openProfile ? null : 'layers');
    flyToStudyArea();
  }

  const loadAll = useCallback(
    async (force = false) => {
      if (force) {clearCache('api:');setRefreshing(true);setCoastal(null);setRevision(v=>v+1);}
      await Promise.all([
        getStudyArea().then((studyArea) => set({ studyArea })),
        getLayers().then((layers) => set({ layers })),
        getAcquisitions().then((acquisitions) => set({ acquisitions })),
        getTerrainChange().then((terrainChange) => set({ terrainChange })),
        getCoastalEvidence().then((res) => {
          setCoastal(res.data);
        }),
        getTransects().then((transects) => {
          const selected = useApp.getState().selectedTransectId;
          const features = transects.data ?? [];
          const selectedTransectId = features.some((feature) => feature.properties.id === selected)
            ? selected
            : features[2]?.properties.id ?? features[0]?.properties.id ?? null;
          set({ transects, selectedTransectId });
        }),
      ]);
      setRefreshing(false);
    },
    [set],
  );

  useEffect(() => {
    void loadAll(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    function escape(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setPanel(null);
        set({ compare: false, bottomOpen: false, inspected: null });
      }
    }
    window.addEventListener('keydown', escape);
    return () => window.removeEventListener('keydown', escape);
  }, [set]);

  const activeSlotId = Object.keys(slots).find((id) => slots[id]?.visible) ?? 'none';
  const activeDesc = activeSlotId !== 'none' ? resolveSlot(layers?.data, activeSlotId, date) : null;
  const activeDef = activeSlotId !== 'none' ? slotById(activeSlotId) : undefined;
  const activeClass =
    activeDef?.classification ??
    (activeSlotId === 'nisar-boundary' || activeSlotId === 'nisar-hh-land-water-candidate'
      ? 'exploratory'
      : activeDesc?.inferred || activeSlotId === 'physics-s2-tide' || activeSlotId === 'physics-s2-setup' || activeSlotId.startsWith('model-')
        ? 'estimated'
        : 'observed');

  const inspUtm = inspected ? lngLatToUtm18N(inspected.lng, inspected.lat) : null;
  const inspFrf = inspected ? lngLatToFrf(inspected.lng, inspected.lat) : null;
  const nearestTransect =
    inspFrf && transects?.data?.length
      ? transects.data.reduce((best, t) =>
          Math.abs((t.properties.frf_y_m ?? 0) - inspFrf[1]) < Math.abs((best.properties.frf_y_m ?? 0) - inspFrf[1]) ? t : best,
        )
      : null;

  return (
    <div className="earth-app">
      <header className="app-header">
        <a
          className="wordmark"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            open('overview');
          }}
        >
          poltergeist<span>Coastal observatory</span>
        </a>
        <div className="header-meta" aria-label="Study metadata">
          <span className="project-label">Duck, North Carolina</span>
          <span className="header-period num">Jun–Oct 2026</span>
          {activeDesc && (
            <button type="button" className="header-layer-pill" onClick={() => open('layers')} title="Click to manage active map layer">
              <span>{activeDesc.title}</span>
              {activeDesc.units && <span className="num muted">({activeDesc.units})</span>}
            </button>
          )}
        </div>
        <button className="header-info" onClick={() => open('about')}>
          About this project <Icon name="info" size={16} />
        </button>
      </header>

      <nav className="tool-rail" aria-label="Main navigation">
        {(
          [
            ['overview', 'globe', 'Explore'],
            ['tour', 'tour', 'Guided Tour'],
            ['layers', 'layers', 'Layers'],
            ['compare', 'compare', 'Compare'],
            ['findings', 'chart', 'Findings'],
            ['about', 'info', 'About'],
          ] as const
        ).map(([id, icon, label]) => (
          <button
            key={id}
            className={panel === id ? 'selected' : ''}
            aria-pressed={panel === id}
            onClick={() => open(panel === id ? null : id)}
            title={label}
          >
            <Icon name={icon} />
            <span>{label}</span>
          </button>
        ))}
      </nav>

      <main id="coastal-workspace" className="map-workspace" aria-label="Coastal map">
        {layers?.state === 'unavailable' && <div className="connection-notice" role="status"><strong>Study data could not be loaded.</strong><span>The background map is still available.</span><button disabled={refreshing} onClick={()=>void loadAll(true)}>{refreshing?'Retrying…':'Retry connection'}</button><details><summary>Details</summary>{layers.reason}</details></div>}

        <MapBoundary><Suspense fallback={<div className="map-loading" role="status">Loading coastal map…</div>}><MapView /></Suspense></MapBoundary>

        <button
          className="location-search"
          onClick={() => {
            flyToStudyArea();
            open('overview');
          }}
          aria-label="Go to Duck study area"
        >
          <Icon name="search" size={18} />
          <span>Duck, North Carolina</span>
          <span className="search-meta num">36.186°N, 75.752°W</span>
        </button>

        {panel && (
          <aside className={`tool-panel ${panel === 'findings' ? 'wide-panel' : ''} ${panel === 'tour' ? 'tour-shell' : ''}`} aria-label={`${panel} panel`}>
            <div className="panel-toolbar">
              <span>
                {
                  (
                    {
                      overview: 'Study area',
                      tour: 'Guided Tour · Duck Investigation',
                      layers: 'Map layers',
                      compare: 'Compare observations',
                      findings: 'Coastal findings',
                      about: 'About Poltergeist',
                    } as const
                  )[panel]
                }
              </span>
              <button className="icon-button" aria-label="Close panel" onClick={() => open(null)}>
                <Icon name="close" size={18} />
              </button>
            </div>
            {panel === 'tour' ? (
              <GuidedTour onExplore={() => open(null)} onNavigatePanel={(next) => open(next)} />
            ) : panel === 'overview' ? (
              <StudyOverview coastal={coastal} open={open} />
            ) : panel === 'findings' ? (
              <BoundaryWorkspace key={revision} onShowMapLayer={showMapLayer} onStartTour={() => open('tour')} />
            ) : (
              <MapTools key={`${panel}-${revision}`} panel={panel} onRefresh={() => void loadAll(true)} />
            )}
          </aside>
        )}

        {inspected && panel !== 'findings' && (
          <aside className="location-inspector-card" aria-label="Clicked coordinate inspector">
            <div className="panel-heading">
              <h2 style={{ margin: 0, fontSize: 13 }}>Location Inspector</h2>
              <button className="icon-button" aria-label="Close inspector" onClick={() => set({ inspected: null })}>
                <Icon name="close" size={15} />
              </button>
            </div>
            <div className="inspector-coords num">
              <div>
                <small>Location</small>
                <span>{inspected.lat.toFixed(5)}°N, {Math.abs(inspected.lng).toFixed(5)}°W</span>
              </div>
              <details><summary>Survey coordinates</summary>{inspUtm && (
                <div>
                  <small>UTM 18N (EPSG:32618)</small>
                  <span>E {inspUtm[0].toFixed(1)} m · N {inspUtm[1].toFixed(1)} m</span>
                </div>
              )}
              {inspFrf && (
                <div>
                  <small>USACE FRF local</small>
                  <span>x {inspFrf[0].toFixed(1)} m cross-shore · y {inspFrf[1].toFixed(1)} m alongshore</span>
                </div>
              )}
              </details>
            </div>
            {activeDesc && (
              <div className="inspector-layer-box">
                <div className="panel-heading">
                  <small className="eyebrow">Active layer</small>
                  <span className={`badge badge-${activeClass}`}>
                    {activeClass === 'observed' ? 'Observed' : activeClass === 'estimated' ? 'Estimated' : 'Exploratory'}
                  </span>
                </div>
                <strong style={{ fontSize: 11.5 }}>{activeDesc.title}</strong>
                <div className="slot-meta num" style={{ marginTop: 2 }}>
                  Units: {activeDesc.units ?? '—'} · {activeDesc.acquired_at?.slice(0, 10) ?? activeDesc.epoch_label ?? 'Paired'}
                </div>
              </div>
            )}
            {nearestTransect && (
              <div className="inspector-actions">
                <button
                  type="button"
                  onClick={() =>
                    set({
                      selectedTransectId: nearestTransect.properties.id,
                      showTransects: true,
                      bottomOpen: true,
                    })
                  }
                >
                  Open nearest beach profile
                </button>
                <button
                  type="button"
                  onClick={() => {
                    set({ selectedTransectId: nearestTransect.properties.id });
                    open('findings');
                  }}
                >
                  Findings →
                </button>
              </div>
            )}
          </aside>
        )}

        {activeDesc && panel !== 'layers' && panel !== 'compare' && (
          <div className="floating-map-legend" aria-label="Active map layer legend">
            <div className="panel-heading" style={{ gap: 8, marginBottom: 4 }}>
              <strong style={{ fontSize: 11 }}>{activeDesc.title}</strong>
              <span className={`badge badge-${activeClass}`}>
                {activeClass === 'observed' ? 'Observed' : activeClass === 'estimated' ? 'Estimated' : 'Exploratory'}
              </span>
            </div>
            <div className="active-legend-meta muted num">
              <span>{activeDesc.sensor} · {activeDesc.acquired_at?.slice(0, 10) ?? activeDesc.epoch_label ?? 'Jun & Oct 2026'}</span>
              {activeDesc.units && <span>Units: {activeDesc.units}</span>}
            </div>
            <Legend colormap={activeDesc.colormap} units={activeDesc.units} inferred={activeDesc.inferred} meaning={activeDef?.meaning} />
            {(activeDef?.tooltip || activeDesc.reason || activeDesc.acquired_at || activeDesc.provenance?.processing) && (
              <details className="legend-notes">
                <summary>Observation notes &amp; limits</summary>
                <div className="legend-notes-body">
                  {activeDesc.acquired_at && (
                    <div className="num">Acquisition UTC: {activeDesc.acquired_at.slice(0, 19).replace('T', ' ')}Z</div>
                  )}
                  {activeDesc.native_resolution_m != null && (
                    <div className="num">
                      Native resolution: {activeDesc.native_resolution_m} m{activeDesc.vertical_datum ? ` · Datum: ${activeDesc.vertical_datum}` : ''}
                    </div>
                  )}
                  {activeDef?.tooltip && <div>{activeDef.tooltip}</div>}
                  {activeDesc.reason && <div className="muted">{activeDesc.reason}</div>}
                  {activeDesc.provenance?.processing && <div className="muted">Processing: {activeDesc.provenance.processing}</div>}
                </div>
              </details>
            )}
          </div>
        )}

        <div className="map-bottom-bar">
          <span>{refreshing || !layers ? 'Connecting to study data…' : layers.state === 'real' ? 'Study data connected' : 'Study data unavailable'}</span>
          <span>Background imagery is not survey-dated</span>
          {cursor && (
            <span className="num">
              {cursor.lat.toFixed(4)}°N, {Math.abs(cursor.lng).toFixed(4)}°W
            </span>
          )}
          <button onClick={() => open('about')}>Data sources</button>
        </div>

        {bottomOpen && (
          <div className="profile-overlay">
            <CrossSection />
          </div>
        )}
      </main>
    </div>
  );
}
