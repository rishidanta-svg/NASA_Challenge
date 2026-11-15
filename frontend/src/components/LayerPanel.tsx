import { useMemo } from 'react';
import type { LayerGroup } from '../api/schemas';
import { GROUP_LABEL, SLOTS } from '../config/slots';
import { demDescriptors, isMockDescriptor, resolveSlot, slotDescriptors } from '../lib/layers';
import { useApp } from '../state/store';
import { DataStateBadge } from './DataStateBadge';
import { Legend } from './Legend';
import { Timeline } from './Timeline';

const GROUPS: LayerGroup[] = ['measured', 'sensor', 'model'];

export function LayerPanel() {
  const {
    mode,
    exaggeration,
    hillshade,
    contours,
    terrainSource,
    slots,
    showStudyArea,
    showTransects,
    date,
    layers,
    transects,
    selectedTransectId,
    drawer,
    set,
    setSlot,
  } = useApp();

  const dems = useMemo(() => demDescriptors(layers?.data), [layers]);

  return (
    <aside className={`sidebar-left ${drawer === 'left' ? 'open' : ''}`} aria-label="Layers and Timeline">
      <Timeline />

      {/* Terrain & Relief section */}
      <section className="panel-section" aria-label="Terrain and Relief Controls">
        <div className="panel-heading">
          <h2>Terrain &amp; Relief</h2>
          <span className="badge badge-real">AWS TERRARIUM</span>
        </div>

        <div className="slot-card">
          <div className="slot-top">
            <label>
              <input
                type="checkbox"
                checked={hillshade.visible}
                onChange={(e) => set({ hillshade: { ...hillshade, visible: e.target.checked } })}
              />
              <span>AWS Terrain Hillshade (2D &amp; 3D)</span>
            </label>
          </div>
          {hillshade.visible && (
            <div className="slot-controls">
              <span>Intensity</span>
              <input
                type="range"
                min={0.1}
                max={1}
                step={0.05}
                value={hillshade.opacity}
                onChange={(e) => set({ hillshade: { ...hillshade, opacity: Number(e.target.value) } })}
                aria-label="Hillshade intensity"
              />
              <span>{Math.round(hillshade.opacity * 100)}%</span>
            </div>
          )}
          <div className="slot-meta">
            Regional elevation tiles (~3–10 m USGS 3DEP / NOAA source). Never equated with 1 m USACE LiDAR.
          </div>
        </div>

        <div className="slot-card">
          <div className="slot-top">
            <label>
              <input
                type="checkbox"
                checked={contours}
                onChange={(e) => set({ contours: e.target.checked })}
                data-testid="contours-toggle"
              />
              <span>Elevation contours (1–20 m)</span>
            </label>
          </div>
          <div className="slot-meta">Computed client-side from AWS Terrarium DEM tiles (z ≥ 11).</div>
        </div>

        <div className="slot-card">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
            <span style={{ fontSize: 12, fontWeight: 500 }}>3D DEM Source</span>
            <select
              value={terrainSource}
              onChange={(e) => set({ terrainSource: e.target.value })}
              aria-label="3D elevation DEM source"
              style={{ minWidth: 0, maxWidth: '72%' }}
            >
              <option value="aws">AWS Regional Terrain (Terrarium)</option>
              {dems.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.title} ({d.epoch_label})
                </option>
              ))}
              {dems.length === 0 && (
                <option value="lidar-pending" disabled>
                  USACE ~1 m LiDAR DEM (awaiting backend)
                </option>
              )}
            </select>
          </div>

          <div className="slot-controls" style={{ marginTop: 8 }}>
            <span>3D Exaggeration</span>
            <input
              type="range"
              min={1}
              max={4}
              step={0.25}
              value={exaggeration}
              onChange={(e) => set({ exaggeration: Number(e.target.value) })}
              aria-label="3D vertical exaggeration"
            />
            <span style={{ color: exaggeration !== 1 ? 'var(--gold)' : undefined }}>{exaggeration}×</span>
            {exaggeration !== 1 && (
              <button onClick={() => set({ exaggeration: 1 })} style={{ padding: '2px 5px', fontSize: 9.5 }}>
                1×
              </button>
            )}
          </div>
          <div className="slot-meta">
            {mode === '3d'
              ? '3D terrain active. Bare-earth DEMs do not capture coastal dune vegetation.'
              : 'Switch to 3D TERRAIN in the top bar to enable 3D relief.'}
          </div>
        </div>

        <div style={{ display: 'flex', gap: 10, marginTop: 6, fontSize: 11.5 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={showStudyArea}
              onChange={(e) => set({ showStudyArea: e.target.checked })}
            />
            <span>Study box &amp; FRF bounds</span>
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={showTransects}
              onChange={(e) => set({ showTransects: e.target.checked })}
            />
            <span>Transects</span>
          </label>
        </div>
      </section>

      {/* Scientific Overlay Slots */}
      <section className="panel-section" aria-label="Scientific Overlay Slots">
        <div className="panel-heading">
          <h2>Scientific Overlays</h2>
          <span className="mono muted" style={{ fontSize: 10 }}>
            {SLOTS.length} SLOTS
          </span>
        </div>

        <div className="scientific-notice" style={{ marginTop: 0, marginBottom: 10 }}>
          Radar backscatter transitions, optical waterlines, and LiDAR elevation contours measure distinct physical
          properties and are never equated.
        </div>

        {GROUPS.map((group) => (
          <div key={group}>
            <div className="slot-group-title">
              <span>{GROUP_LABEL[group]}</span>
              {group === 'model' && <span style={{ color: 'var(--purple)' }}>INFERRED · NOT MEASURED</span>}
            </div>

            {SLOTS.filter((s) => s.group === group).map((slot) => {
              const ui = slots[slot.id] ?? { visible: false, opacity: slot.defaultOpacity };
              const desc = resolveSlot(layers?.data, slot.id, date);
              const allForSlot = slotDescriptors(layers?.data, slot.id);
              const pendingReason = allForSlot.find((d) => d.status === 'unavailable')?.reason;
              const isMock = isMockDescriptor(desc);
              const available = !!desc;

              return (
                <div
                  key={slot.id}
                  className={`slot-card ${ui.visible && available ? 'active' : ''} ${!available ? 'unavailable' : ''}`}
                  data-testid={`slot-${slot.id}`}
                >
                  <div className="slot-top">
                    <label>
                      <input
                        type="checkbox"
                        checked={ui.visible}
                        disabled={!available}
                        onChange={(e) => setSlot(slot.id, { visible: e.target.checked })}
                      />
                      <span className="swatch" style={{ background: slot.color }} />
                      <span>{slot.title}</span>
                    </label>
                    <DataStateBadge
                      state={!available ? 'unavailable' : isMock ? 'mock' : 'real'}
                      inferred={slot.group === 'model' && available}
                      label={!available ? 'AWAITING' : isMock ? 'MOCK' : 'REAL'}
                    />
                  </div>

                  {available && desc ? (
                    <>
                      <div className="slot-meta">
                        <span className="mono">{desc.epoch_label}</span>
                        {desc.native_resolution_m ? ` · ${desc.native_resolution_m} m` : ''}
                        {desc.vertical_datum ? ` · ${desc.vertical_datum}` : ''}
                      </div>
                      {ui.visible && (
                        <>
                          <div className="slot-controls">
                            <span>Opacity</span>
                            <input
                              type="range"
                              min={0.1}
                              max={1}
                              step={0.05}
                              value={ui.opacity}
                              onChange={(e) => setSlot(slot.id, { opacity: Number(e.target.value) })}
                              aria-label={`${slot.title} opacity`}
                            />
                            <span>{Math.round(ui.opacity * 100)}%</span>
                          </div>
                          <Legend
                            colormap={desc.colormap}
                            units={desc.units}
                            inferred={desc.inferred}
                            meaning={slot.meaning}
                          />
                        </>
                      )}
                    </>
                  ) : (
                    <div className="slot-meta">{pendingReason ?? slot.meaning}</div>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </section>

      {/* Survey Transects */}
      <section className="panel-section" aria-label="Survey Transects">
        <div className="panel-heading">
          <h2>Shore-Normal Transects</h2>
          <DataStateBadge state={transects?.state ?? 'unavailable'} />
        </div>
        {(transects?.data ?? []).map((t) => {
          const active = t.properties.id === selectedTransectId;
          return (
            <button
              key={t.properties.id}
              className={`transect-btn ${active ? 'active' : ''}`}
              onClick={() => set({ selectedTransectId: t.properties.id, bottomOpen: true })}
              data-testid={`transect-${t.properties.id}`}
            >
              <span>⌖ {t.properties.label}</span>
              <span className="muted">{t.properties.id}</span>
            </button>
          );
        })}
      </section>
    </aside>
  );
}
