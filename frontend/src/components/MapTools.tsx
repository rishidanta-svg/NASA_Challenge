import { useEffect, useState } from 'react';
import { getCoastalEvidence, type Sourced } from '../api/client';
import type { CoastalEvidence, LayerDescriptor } from '../api/schemas';
import { BASEMAPS, type BasemapId } from '../config/basemaps';
import { type LayerClassification, slotById } from '../config/slots';
import { resolveSlot } from '../lib/layers';
import { useApp } from '../state/store';
import { EnvironmentPanel } from './EnvironmentPanel';
import { Legend } from './Legend';

const overlays = [
  { id: 'none', name: 'No overlay', description: 'Unobstructed coastal imagery baseline.' },
  { id: 'lidar-dz', name: 'Ground level change', description: 'Measured USACE LiDAR Δz (October − June 2026, m NAVD88).' },
  { id: 'lidar-elevation', name: 'Beach elevation', description: 'Measured bare-earth surface height above NAVD88 (m).' },
  { id: 'physics-s2-tide', name: 'Tide-adjusted waterline', description: 'Sentinel-2 optical edge normalized to MHW (0.359 m); conditional on beach slope.' },
  { id: 'nisar-hh', name: 'Radar observation', description: 'Exploratory NISAR L-band HH backscatter (dB). Not an erosion or confirmed shoreline map.' },
];

const dates = [
  ['2026-06-18', 'June 2026 epoch'],
  ['2026-10-16', 'October 2026 epoch'],
];

interface SensorCatalogGroup {
  id: string;
  label: string;
  subtitle: string;
  tooltip: string;
  slotIds: string[];
}

const SENSOR_GROUPS: SensorCatalogGroup[] = [
  {
    id: 'lidar',
    label: 'USACE LiDAR · Elevation Reference',
    subtitle: 'Independent 1 m ground truth (NAVD88)',
    tooltip: 'Field Research Facility dune LiDAR surveys (Jun 19 & Oct 16, 2026) in metres NAVD88 (geoid12b); coregistration QC flag = 1.',
    slotIds: ['lidar-dz', 'lidar-elevation', 'lidar-coverage'],
  },
  {
    id: 's2',
    label: 'Sentinel-2 · Optical (NDWI / MNDWI)',
    subtitle: 'Waterlines, indices & tide correction',
    tooltip: 'NDWI uses green & NIR (10 m); MNDWI uses green & SWIR (20 m). Tide correction projects waterline elevation differences using surveyed slope.',
    slotIds: ['s2-index', 's2-ndwi-change', 's2-boundary', 'physics-s2-ndwi', 'physics-s2-mndwi', 'physics-s2-tide', 'physics-s2-setup'],
  },
  {
    id: 's1',
    label: 'Sentinel-1 · C-band SAR',
    subtitle: 'Track 106 VV / VH backscatter (dB)',
    tooltip: '5.4 GHz C-band dual-pol (VV, VH) RTC gamma-zero in dB. Repeats Track 106 Ascending; June acquisition follows NISAR by ~11.96 days.',
    slotIds: ['s1-vv', 's1-vh', 's1-vv-change', 's1-vh-change', 'radar-disagreement'],
  },
  {
    id: 'nisar',
    label: 'NASA–ISRO NISAR · L-band SAR',
    subtitle: 'Track 69 HH / HV backscatter (Exploratory)',
    tooltip: '1.26 GHz L-band provisional GCOV (HH, HV in dB, 10 m posting). HH transition is exploratory and failed ocean waterline comparability.',
    slotIds: ['nisar-hh', 'nisar-hv', 'nisar-hh-change', 'nisar-hv-change', 'nisar-quality', 'nisar-boundary', 'nisar-hh-land-water-candidate'],
  },
  {
    id: 'joint',
    label: 'Joint Support & Experimental Model',
    subtitle: '4-sensor mask & withheld terrain model',
    tooltip: 'Joint valid 10 m overlap across all 4 sensors (168 cells). Ridge terrain models remain withheld from operational deployment.',
    slotIds: ['all-sensor-overlap', 'model-dz', 'model-sigma'],
  },
];

function classifyDescriptor(slotId: string, desc: LayerDescriptor | null): LayerClassification {
  const def = slotById(slotId);
  if (def?.classification) return def.classification;
  if (slotId === 'nisar-boundary' || slotId === 'nisar-hh-land-water-candidate') return 'exploratory';
  if (desc?.inferred || slotId === 'physics-s2-tide' || slotId === 'physics-s2-setup' || slotId.startsWith('model-')) return 'estimated';
  return 'observed';
}

function classBadgeText(c: LayerClassification): string {
  return c === 'exploratory' ? 'Exploratory' : c === 'estimated' ? 'Conditional estimate' : 'Observed';
}

export function MapTools({ panel, onRefresh }: { panel: 'layers' | 'compare' | 'about'; onRefresh: () => void }) {
  const { basemap, date, compareDate, slots, layers, transects, selectedTransectId, terrainSource, mode, bottomOpen, exaggeration, set, setSlot } = useApp();
  const [coastal, setCoastal] = useState<Sourced<CoastalEvidence> | null>(null);
  const selected = Object.keys(slots).find((id) => slots[id]?.visible) ?? 'none';
  const active = resolveSlot(layers?.data, selected, date);
  const activeDef = selected !== 'none' ? slotById(selected) : undefined;
  const activeClass = active ? classifyDescriptor(selected, active) : null;

  useEffect(() => {
    if (panel !== 'compare') return;
    let mounted = true;
    void getCoastalEvidence().then((res) => {
      if (mounted) setCoastal(res);
    });
    return () => {
      mounted = false;
    };
  }, [panel]);

  function choose(id: string) {
    Object.keys(slots).forEach((key) => setSlot(key, { visible: key === id }));
  }

  function changeDate(value: string) {
    set({
      date: value,
      terrainSource: terrainSource === 'aws' ? 'aws' : `lidar-dem-${value.startsWith('2026-06') ? 'june' : 'october'}`,
    });
  }

  if (panel === 'about') {
    return (
      <div className="panel-content about-content">
        <span className="eyebrow">NASA Space Apps 2026 · Coastal Remote Sensing</span>
        <h1>About POLTERGEIST</h1>
        <p>
          Poltergeist integrates airborne topographic LiDAR, L-band and C-band synthetic aperture radar (SAR), multispectral optical imagery, and coastal tide/wave records across a verified 500 m research reach at Duck, North Carolina.
        </p>

        <div className="sensor-meta-grid">
          <div className="meta-chip">
            <span className="eyebrow">Analysis CRS</span>
            <strong className="num">EPSG:32618 (UTM 18N)</strong>
          </div>
          <div className="meta-chip">
            <span className="eyebrow">Vertical Datum</span>
            <strong className="num">NAVD88 (geoid12b)</strong>
          </div>
          <div className="meta-chip">
            <span className="eyebrow">FRF Alongshore</span>
            <strong className="num">y = 700–1190 m</strong>
          </div>
          <div className="meta-chip">
            <span className="eyebrow">Tide Reference</span>
            <strong className="num">MHW 0.359 m · MLLW</strong>
          </div>
        </div>

        <details open>
          <summary>Primary sensors & reference datasets</summary>
          <p>
            <strong>USACE FRF Dune LiDAR (Independent reference):</strong> 1 m bare-earth elevation (m NAVD88) collected Jun 19 and Oct 16, 2026 (17,466 paired cells; coregistration QC flag = 1).
          </p>
          <p>
            <strong>NASA–ISRO NISAR (L-band SAR):</strong> Track 69 Descending L2 GCOV provisional V1 (HH & HV gamma-zero dB, 10 m posting). Treated strictly as exploratory for waterline and elevation inference.
          </p>
          <p>
            <strong>Copernicus Sentinel-1 (C-band SAR):</strong> Track 106 Ascending RTC (VV & VH gamma-zero dB). June overpass follows NISAR by ~11.96 days, separating timing and radar frequency.
          </p>
          <p>
            <strong>Copernicus Sentinel-2 (Optical L2A):</strong> NDWI (10 m) and MNDWI (20 m) waterlines paired with NOAA gauge and LiDAR slope.
          </p>
        </details>

        <details>
          <summary>Environmental observations & scope limits</summary>
          <p>
            Tide water level (m MLLW), predictions, wave height/period/direction (17 m and 26 m arrays), wind speed/gusts, and rainfall are matched from NOAA CO-OPS station 8651370 and USACE FRF sensors within strict acquisition windows.
          </p>
          <p>
            Esri background satellite imagery provides geographic context only and does not reflect 2026 survey dates. This platform is a retrospective scientific workspace and not a hazard warning service.
          </p>
        </details>

        <details>
          <summary>Map navigation & 3D controls</summary>
          <p>
            Drag to pan, scroll or tap + / − to zoom. Switch to 3D mode and hold Ctrl while dragging to pitch or rotate; press N to reset north. Click anywhere along the beach to open the Location Inspector in local FRF, UTM 18N, and WGS84 coordinates.
          </p>
        </details>

        <details>
          <summary>Live NOAA Duck Station (8651370) conditions</summary>
          <p>Live station telemetry is separate from the June–October 2026 study acquisitions.</p>
          <EnvironmentPanel />
        </details>

        <button className="full-button" onClick={onRefresh}>
          Refresh study data
        </button>
        <a
          className="text-link"
          href="https://earth.google.com/web/@36.186,-75.752,0a,1500d,35y,0h,60t,0r"
          target="_blank"
          rel="noopener noreferrer"
        >
          Open this location in Google Earth ↗
        </a>
        <div className="quiet-note">NASA Space Apps 2026 research prototype. Independent scientific measurements, estimates, and exploratory products are labeled separately.</div>
      </div>
    );
  }

  const cData = coastal?.data;

  return (
    <div className="panel-content">
      <div className="panel-heading" style={{ marginBottom: 4 }}>
        <span className="eyebrow">{panel === 'compare' ? 'Dual-epoch comparator' : 'Data layers & units'}</span>
        {activeClass && <span className={`badge badge-${activeClass}`}>{classBadgeText(activeClass)}</span>}
      </div>
      <h1>{panel === 'compare' ? 'What changed?' : 'Choose what to see'}</h1>
      <p className="intro">
        {panel === 'compare'
          ? 'Drag the divider across the map to inspect temporal shifts across optical, radar, and LiDAR products.'
          : 'Select a core overlay or expand any of the four primary sensor groups below.'}
      </p>

      {panel === 'compare' && (
        <>
          <div className="comparison-dates">
            <label>
              Left side
              <select aria-label="Left comparison survey" value={date} onChange={(e) => changeDate(e.target.value)}>
                {dates.map(([v, n]) => (
                  <option value={v} key={v}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Right side
              <select aria-label="Right comparison survey" value={compareDate} onChange={(e) => set({ compareDate: e.target.value })}>
                {dates.map(([v, n]) => (
                  <option value={v} key={v}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {date === compareDate && (
            <p role="status" className="quality-note" style={{ marginBlock: 10 }}>
              Both sides show the same epoch. Choose different epochs to compare changes.
            </p>
          )}
          <button className="full-button" onClick={() => choose('lidar-elevation')}>
            Compare surveyed beach elevations
          </button>

          {cData?.radar_disagreement && (
            <div className="compare-meta-card">
              <div className="panel-heading">
                <strong>Acquisition timing alignment</strong>
                <span className="badge">4 sensors</span>
              </div>
              <p className="slot-meta" style={{ marginTop: 6 }}>
                <strong>USACE LiDAR:</strong> Jun 19 00:31Z → Oct 16 23:33Z (m NAVD88)
                <br />
                <strong>Sentinel-2 & NISAR:</strong> Jun 18 → Oct 16, 2026 (~7.8 h intra-day gap)
                <br />
                <strong>Sentinel-1 C-SAR:</strong> Jun 30 → Oct 16, 2026 (Jun lags NISAR by{' '}
                <span className="num">
                  {cData.radar_disagreement.s1_minus_nisar_seconds
                    ? `${(cData.radar_disagreement.s1_minus_nisar_seconds.june / 86400).toFixed(2)} d`
                    : 'Not available'}
                </span>
                )
              </p>
              <p className="slot-meta muted" style={{ marginBottom: 0 }}>
                Opposite ΔHH vs ΔVV signs occur in{' '}
                <span className="num">
                  {cData.radar_disagreement.opposite_strict_cells ?? '—'}/{cData.radar_disagreement.strict_overlap_cells ?? '—'}
                </span>{' '}
                strict cells — timing and frequency effects are coupled.
              </p>
            </div>
          )}
        </>
      )}

      <fieldset className="layer-choices">
        <legend>Map overlay</legend>
        {overlays.map((o) => {
          const desc = o.id === 'none' ? null : resolveSlot(layers?.data, o.id, date);
          const available = o.id === 'none' || !!desc;
          const cls = o.id === 'none' ? null : classifyDescriptor(o.id, desc);
          return (
            <label key={o.id} className={`layer-choice ${selected === o.id ? 'active' : ''}`}>
              <input type="radio" name="overlay" value={o.id} disabled={!available} checked={selected === o.id} onChange={() => choose(o.id)} />
              <span style={{ flex: 1, minWidth: 0 }}>
                <span className="layer-row-title">
                  <strong>{o.name}</strong>
                  {cls && <span className={`badge badge-${cls}`}>{cls === 'observed' ? 'Obs' : cls === 'estimated' ? 'Est' : 'Exp'}</span>}
                </span>
                <small>{available ? o.description : 'This layer is unavailable for this date.'}</small>
              </span>
            </label>
          );
        })}
      </fieldset>

      {selected === 'nisar-hh-land-water-candidate' && (
        <p className="quality-note exploratory-note">
          <strong>Exploratory boundary warning:</strong> NISAR HH Otsu brightness transition failed optical/tide waterline comparability (~38–40 m median offset); not a validated shoreline.
        </p>
      )}
      {selected === 'nisar-boundary' && (
        <p className="quality-note exploratory-note">
          <strong>Exploratory radar line:</strong> Radar backscatter boundary shown for cross-sensor inspection only; do not interpret as erosion or MHW shoreline.
        </p>
      )}

      {active && (
        <div className="active-legend">
          <div className="panel-heading" style={{ gap: 6, marginBottom: 4 }}>
            <strong style={{ fontSize: 11.5 }}>{active.title}</strong>
            {activeClass && <span className={`badge badge-${activeClass}`}>{classBadgeText(activeClass)}</span>}
          </div>
          <div className="active-legend-meta muted num">
            <span>{active.sensor} · {active.epoch_label ?? 'Paired interval'}</span>
            {active.acquired_at && (
              <time dateTime={active.acquired_at}>
                {new Date(active.acquired_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })}
              </time>
            )}
          </div>
          <Legend colormap={active.colormap} units={active.units} inferred={active.inferred} meaning={active.quantity ?? activeDef?.meaning ?? ''} />
          {activeDef?.tooltip && <p className="slot-meta tooltip-copy">{activeDef.tooltip}</p>}
          {active.units && (
            <div className="active-legend-meta muted num" style={{ marginTop: 6 }}>
              <span>Units: {active.units}</span>
              {active.native_resolution_m != null && <span>Grid: {active.native_resolution_m} m</span>}
            </div>
          )}
          <div className="opacity-control">
            <label htmlFor="active-layer-opacity">
              Layer opacity <span className="num">{Math.round((slots[selected]?.opacity ?? activeDef?.defaultOpacity ?? 0.75) * 100)}%</span>
            </label>
            <input
              id="active-layer-opacity"
              type="range"
              min={0.2}
              max={1}
              step={0.05}
              value={slots[selected]?.opacity ?? activeDef?.defaultOpacity ?? 0.75}
              onChange={(e) => setSlot(selected, { opacity: Number(e.target.value) })}
            />
          </div>
        </div>
      )}

      {panel === 'layers' && (
        <label className="field-label">
          Observation epoch
          <select aria-label="Survey observation" value={date} onChange={(e) => changeDate(e.target.value)}>
            {dates.map(([v, n]) => (
              <option value={v} key={v}>
                {n}
              </option>
            ))}
          </select>
        </label>
      )}

      {panel === 'layers' && (
        <div className="sensor-catalog" aria-label="Sensor layer catalog">
          <p className="eyebrow" style={{ marginBottom: 8 }}>
            All sensor & analysis layers ({layers?.data?.filter((l) => l.status === 'available').length ?? 0} descriptors)
          </p>
          {SENSOR_GROUPS.map((grp) => {
            const hasActive = grp.slotIds.includes(selected);
            return (
              <details key={grp.id} className="sensor-group" open={hasActive || grp.id === 's2' || grp.id === 'nisar'}>
                <summary>
                  <span>
                    <strong>{grp.label}</strong>
                    <small className="group-sub">{grp.subtitle}</small>
                  </span>
                  {hasActive && <span className="badge badge-observed">Active</span>}
                </summary>
                <p className="group-tooltip" title={grp.tooltip}>
                  {grp.tooltip}
                </p>
                <div className="worldview-list">
                  {grp.slotIds.map((slotId) => {
                    const def = slotById(slotId);
                    const desc = resolveSlot(layers?.data, slotId, date);
                    const isSelected = selected === slotId;
                    const cls = classifyDescriptor(slotId, desc);
                    const unit = desc?.units ?? def?.expectedUnits ?? '—';
                    return (
                      <button
                        key={slotId}
                        type="button"
                        disabled={!desc}
                        className={`worldview-row ${isSelected ? 'active' : ''}`}
                        onClick={() => choose(slotId)}
                        title={desc?.quantity ?? def?.meaning}
                      >
                        <span className="swatch-dot" style={{ background: def?.color ?? '#777' }} aria-hidden="true" />
                        <span className="worldview-row-main">
                          <strong>{def?.title ?? desc?.title ?? slotId}</strong>
                          <small className="num">
                            {unit} · {desc?.reference_date ?? (desc?.epoch_label || 'Multi-epoch')}
                          </small>
                        </span>
                        <span className={`badge badge-${cls}`}>{cls === 'observed' ? 'Obs' : cls === 'estimated' ? 'Est' : 'Exp'}</span>
                      </button>
                    );
                  })}
                </div>
              </details>
            );
          })}
        </div>
      )}

      <details>
        <summary>Beach profiles (USACE transects)</summary>
        <p>Inspect June & October elevation profiles (m NAVD88), NOAA MHW line, and sensor markers along any FRF transect.</p>
        <label className="field-label">
          Profile location
          <select
            aria-label="Profile location"
            value={selectedTransectId ?? ''}
            onChange={(e) => set({ selectedTransectId: e.target.value, showTransects: true, bottomOpen: true })}
          >
            {(transects?.data ?? []).map((t, i) => (
              <option key={t.properties.id} value={t.properties.id}>
                Section {i + 1} · {t.properties.frf_y_m} m along coast
              </option>
            ))}
          </select>
        </label>
        <button className="full-button" disabled={!selectedTransectId} onClick={() => set({ bottomOpen: !bottomOpen, showTransects: !bottomOpen })}>
          {bottomOpen ? 'Hide profile' : 'Show profile on map'}
        </button>
      </details>

      <details>
        <summary>Map appearance & terrain</summary>
        <label className="field-label">
          Background
          <select aria-label="Map background" value={basemap} onChange={(e) => set({ basemap: e.target.value as BasemapId })}>
            {BASEMAPS.filter((b) => ['satellite', 'positron'].includes(b.id)).map((b) => (
              <option key={b.id} value={b.id}>
                {b.id === 'positron' ? 'Street map' : b.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field-label">
          Terrain source
          <select aria-label="Terrain source" value={terrainSource} onChange={(e) => set({ terrainSource: e.target.value })}>
            <option value="aws">Regional terrain</option>
            {(layers?.data ?? [])
              .filter((l) => l.kind === 'raster_dem')
              .map((l) => (
                <option key={l.id} value={l.id}>
                  {l.epoch_label} beach survey
                </option>
              ))}
          </select>
        </label>
        {mode === '3d' && (
          <label className="field-label">
            Terrain height
            <select aria-label="Terrain height" value={exaggeration} onChange={(e) => set({ exaggeration: Number(e.target.value) })}>
              <option value={1}>True scale (1×)</option>
              <option value={2}>Enhanced (2×)</option>
            </select>
          </label>
        )}
      </details>

      <div className="quiet-note">The satellite background is orientation context only. Scientific overlays update by acquisition date and sensor.</div>
    </div>
  );
}
