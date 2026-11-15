import { BASEMAPS, type BasemapId } from '../config/basemaps';
import { ANALYSIS_CRS, DISPLAY_CRS, FRF_Y_RANGE_M } from '../config/geo';
import { useApp } from '../state/store';
import { DataStateBadge } from './DataStateBadge';

export interface HeaderProps {
  onRefreshAll: () => void;
}

export function Header({ onRefreshAll }: HeaderProps) {
  const { basemap, mode, drawer, layers, set } = useApp();

  const overallState = layers?.state ?? 'unavailable';

  return (
    <>
      <header className="top-header">
        <div className="brand">
          <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true">
            <path
              d="M3 8h11l-5 8h13l-5 8h12M3 16h3M3 24h11"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
            />
          </svg>
          <div>
            <span className="brand-title">POLTERGEIST</span>
            <small className="brand-sub">COASTAL OBSERVATION &amp; TERRAIN WORKSTATION · NASA SPACE APPS 2026</small>
          </div>
        </div>

        <div className="header-controls">
          <div className="mobile-drawer-toggles">
            <button onClick={() => set({ drawer: drawer === 'left' ? null : 'left' })}>☰ Layers</button>
            <button onClick={() => set({ drawer: drawer === 'right' ? null : 'right' })}>ⓘ Inspector</button>
          </div>

          <div className="segmented" role="group" aria-label="Map dimension mode">
            <button
              className={mode === '2d' ? 'active' : ''}
              onClick={() => set({ mode: '2d' })}
              data-testid="mode-2d"
            >
              2D MAP
            </button>
            <button
              className={mode === '3d' ? 'active' : ''}
              onClick={() => set({ mode: '3d' })}
              data-testid="mode-3d"
            >
              3D TERRAIN
            </button>
          </div>

          <label className="mono" style={{ fontSize: 11, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span className="muted">BASEMAP</span>
            <select
              value={basemap}
              onChange={(e) => set({ basemap: e.target.value as BasemapId })}
              aria-label="OpenFreeMap basemap style"
              data-testid="basemap-select"
            >
              {BASEMAPS.map((b) => (
                <option key={b.id} value={b.id}>
                  OpenFreeMap · {b.label}
                </option>
              ))}
            </select>
          </label>

          <DataStateBadge
            state={overallState}
            origin={layers?.origin}
            label={overallState === 'mock' ? 'MOCK OVERLAYS · BACKEND OFFLINE' : undefined}
          />

          <button onClick={onRefreshAll} title="Re-query FastAPI backend and live NOAA station">
            ↻ Sync API
          </button>
        </div>
      </header>

      <div className="context-bar">
        <div className="context-left">
          <span className="eyebrow">STUDY SITE</span>
          <strong>Duck FRF, North Carolina</strong>
          <span className="muted">USACE Field Research Facility · FRF y = {FRF_Y_RANGE_M[0]}–{FRF_Y_RANGE_M[1]} m</span>
        </div>
        <div className="context-right mono">
          <span>36.183704°–36.188260° N · 75.753384°–75.750335° W</span>
          <span className="context-divider" />
          <span className="muted">Analysis {ANALYSIS_CRS} · Display {DISPLAY_CRS}</span>
        </div>
      </div>
    </>
  );
}
