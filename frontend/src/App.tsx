import { useCallback, useEffect, useState } from 'react';
import { getAcquisitions, getCoastalEvidence, getLayers, getStudyArea, getTerrainChange, getTransects } from './api/client';
import { clearCache } from './api/http';
import type { CoastalEvidence } from './api/schemas';
import { BoundaryWorkspace } from './components/BoundaryWorkspace';
import { CrossSection } from './components/CrossSection';
import { Icon } from './components/Icon';
import { Legend } from './components/Legend';
import { MapTools } from './components/MapTools';
import { slotById } from './config/slots';
import { lngLatToFrf, lngLatToUtm18N } from './lib/frf';
import { resolveSlot } from './lib/layers';
import { MapView } from './map/MapView';
import { flyToStudyArea } from './map/registry';
import { useApp } from './state/store';

type Panel = 'overview' | 'layers' | 'compare' | 'findings' | 'about' | null;

export function App() {
  const [panel, setPanel] = useState<Panel>('overview');
  const [coastal, setCoastal] = useState<CoastalEvidence | null>(null);
  const set = useApp((s) => s.set);
  const { bottomOpen, layers, date, slots, inspected, transects, cursor } = useApp();

  function open(next: Panel) {
    setPanel(next);
    set({ compare: next === 'compare' });
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

  const loadAll = useCallback(
    async (force = false) => {
      if (force) clearCache('api:');
      await Promise.all([
        getStudyArea().then((studyArea) => set({ studyArea })),
        getLayers().then((layers) => set({ layers })),
        getAcquisitions().then((acquisitions) => set({ acquisitions })),
        getTerrainChange().then((terrainChange) => set({ terrainChange })),
        getCoastalEvidence().then((res) => {
          if (res.data) setCoastal(res.data);
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

  const mhwRaw = coastal?.validation.targets.fixed_mhw_contour?.raw_vs_tide.methods?.raw?.rmse_m;
  const mhwTide = coastal?.validation.targets.fixed_mhw_contour?.raw_vs_tide.methods?.tide?.rmse_m;
  const mhwRed = (coastal?.validation.targets.fixed_mhw_contour?.raw_vs_tide as { rmse_reduction_percent?: Record<string, number> } | undefined)
    ?.rmse_reduction_percent?.tide;
  const lidarMean = coastal?.terrain?.mean_m;

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
          <span className="project-label">Duck, North Carolina · FRF 700–1190 m</span>
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

      <main className="map-workspace" aria-label="Coastal map">
        <MapView />

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
          <aside className={`tool-panel ${panel === 'findings' ? 'wide-panel' : ''}`} aria-label={`${panel} panel`}>
            <div className="panel-toolbar">
              <span>
                {
                  (
                    {
                      overview: 'Study area',
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
            {panel === 'overview' ? (
              <div className="panel-content">
                <div className="location-label">
                  <Icon name="pin" size={15} /> USACE Field Research Facility · Duck, NC
                </div>
                <h1>Duck coastline</h1>
                <p className="intro">Multi-sensor observation study integrating LiDAR elevation truth, optical waterlines, SAR backscatter, and coastal tide/wave telemetry (June–October 2026).</p>
                <div className="study-facts">
                  <span>
                    <strong className="num">500 m</strong>Study reach
                  </span>
                  <span>
                    <strong className="num">2 epochs</strong>June & October
                  </span>
                  <span>
                    <strong className="num">4 sensors</strong>10 m grid
                  </span>
                </div>

                {(mhwRed != null || lidarMean != null) && (
                  <div className="explore-verified-box">
                    <div className="panel-heading">
                      <span className="eyebrow">Verified Result Snapshot</span>
                      <button type="button" className="inline-link" onClick={() => open('findings')}>
                        Full analysis →
                      </button>
                    </div>
                    {mhwRed != null && mhwRaw != null && mhwTide != null && (
                      <p className="slot-meta" style={{ marginTop: 6, marginBottom: 4 }}>
                        <strong className="num">−{mhwRed.toFixed(1)}%</strong> Sentinel-2 shoreline RMSE via NOAA tide correction (
                        <span className="num">{mhwRaw.toFixed(2)} → {mhwTide.toFixed(2)} m</span> across 36 October LiDAR MHW positions).
                      </p>
                    )}
                    {lidarMean != null && (
                      <p className="slot-meta" style={{ margin: 0 }}>
                        <strong className="num">{lidarMean.toFixed(2)} m</strong> mean October−June beach Δz across{' '}
                        <span className="num">{coastal?.terrain?.native_paired_cells?.toLocaleString() ?? '17,466'}</span> paired 1 m USACE LiDAR cells.
                      </p>
                    )}
                  </div>
                )}

                <p className="section-label">Integrated data sources</p>
                <div className="sensor-pills-grid">
                  <div className="sensor-pill">
                    <strong>USACE LiDAR</strong>
                    <small>m NAVD88 · Reference</small>
                  </div>
                  <div className="sensor-pill">
                    <strong>Sentinel-2</strong>
                    <small>NDWI / MNDWI · Tide-adjusted</small>
                  </div>
                  <div className="sensor-pill">
                    <strong>Sentinel-1 C-SAR</strong>
                    <small>VV / VH dB · Track 106</small>
                  </div>
                  <div className="sensor-pill">
                    <strong>NISAR L-SAR</strong>
                    <small>HH / HV dB · Exploratory</small>
                  </div>
                </div>

                <p className="section-label">Start exploring</p>
                <button className="action-row" onClick={() => open('layers')}>
                  <Icon name="layers" />
                  <span>
                    <strong>See coastal change</strong>
                    <small>Switch between LiDAR Δz, Sentinel-1/2, and exploratory NISAR layers</small>
                  </span>
                  <Icon name="arrow" size={16} />
                </button>
                <button className="action-row" onClick={() => open('compare')}>
                  <Icon name="compare" />
                  <span>
                    <strong>Compare two observations</strong>
                    <small>Swipe between June and October surveys with aligned acquisition timing</small>
                  </span>
                  <Icon name="arrow" size={16} />
                </button>
                <button
                  className="action-row"
                  onClick={() => {
                    open('findings');
                    set({ bottomOpen: false });
                  }}
                >
                  <Icon name="chart" />
                  <span>
                    <strong>Understand the findings</strong>
                    <small>Tide correction verification (−49.7%), environmental state & limits</small>
                  </span>
                  <Icon name="arrow" size={16} />
                </button>
                <div className="quiet-note">
                  Retrospective coastal research platform. Observed values, conditional estimates, and exploratory radar diagnostics are strictly distinguished.
                </div>
              </div>
            ) : panel === 'findings' ? (
              <BoundaryWorkspace />
            ) : (
              <MapTools panel={panel} onRefresh={() => void loadAll(true)} />
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
                <small>WGS84</small>
                <span>{inspected.lat.toFixed(5)}°N, {Math.abs(inspected.lng).toFixed(5)}°W</span>
              </div>
              {inspUtm && (
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
                  Open {nearestTransect.properties.id} profile
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
              <span>{activeDesc.sensor} · {activeDesc.epoch_label ?? 'Oct − Jun 2026'}</span>
              {activeDesc.units && <span>Units: {activeDesc.units}</span>}
            </div>
            <Legend colormap={activeDesc.colormap} units={activeDesc.units} inferred={activeDesc.inferred} meaning={activeDef?.meaning} />
          </div>
        )}

        <div className="map-bottom-bar">
          <span>{layers?.state === 'real' ? 'Study data connected' : 'Study data unavailable'}</span>
          <span>June – October 2026</span>
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
