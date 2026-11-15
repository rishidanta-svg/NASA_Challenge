import { useEffect, useState } from 'react';
import { getTransect, type Sourced } from '../api/client';
import type { TransectDetail } from '../api/schemas';
import { useApp } from '../state/store';

const MHW_NAVD88_M = 0.359;

export function CrossSection() {
  const { selectedTransectId, bottomOpen, set } = useApp();
  const [detail, setDetail] = useState<Sourced<TransectDetail> | null>(null);
  const [guides, setGuides] = useState(false);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    setDetail(null);
    if (selectedTransectId) {
      void getTransect(selectedTransectId).then((r) => {
        if (active) setDetail(r);
      });
    }
    return () => {
      active = false;
    };
  }, [selectedTransectId]);

  const t = detail?.data;
  const j = t?.profiles[0];
  const o = t?.profiles[1];
  const points = [...(j?.points ?? []), ...(o?.points ?? [])];
  const xmin = points.length ? Math.min(...points.map((p) => p.x_m)) : 0;
  const xmax = points.length ? Math.max(...points.map((p) => p.x_m)) : 200;
  const zmin = points.length ? Math.floor(Math.min(...points.map((p) => p.z_m))) - 1 : 0;
  const zmax = points.length ? Math.ceil(Math.max(...points.map((p) => p.z_m))) + 1 : 8;
  const W = 760;
  const H = 172;
  const left = 46;
  const right = 14;
  const top = 12;
  const bottom = 26;
  const sx = (x: number) => left + ((x - xmin) / (xmax - xmin || 1)) * (W - left - right);
  const sy = (z: number) => top + ((zmax - z) / (zmax - zmin || 1)) * (H - top - bottom);
  const path = (ps: { x_m: number; z_m: number }[]) =>
    ps.map((p, i) => `${i === 0 || p.x_m - ps[i - 1]!.x_m > 1.01 ? 'M' : 'L'}${sx(p.x_m)},${sy(p.z_m)}`).join(' ');

  function near<T extends { x_m: number }>(ps: T[] | undefined) {
    if (hover === null || !ps?.length) return null;
    const p = ps.reduce((a, b) => (Math.abs(a.x_m - hover) < Math.abs(b.x_m - hover) ? a : b));
    return Math.abs(p.x_m - hover) <= 0.51 ? p : null;
  }

  const hj = near(j?.points);
  const ho = near(o?.points);
  const change = near(t?.measured_change?.change_profile);
  const xOrigin = t?.properties.x_origin_frf_m ?? 0;

  return (
    <section className="cross-section-dock" aria-label="Measured beach profile" data-testid="cross-section">
      <div className="cross-section-header">
        <strong>Measured beach profile · {t?.properties.label ?? 'Loading…'}</strong>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span className="muted num">NAVD88 (geoid12b)</span>
          {!!t?.boundaries.length && (
            <label style={{ fontSize: 11, display: 'inline-flex', alignItems: 'center', gap: 5 }}>
              <input type="checkbox" checked={guides} onChange={(e) => setGuides(e.target.checked)} />
              Sensor markers
            </label>
          )}
          <button aria-label="Close beach profile" onClick={() => set({ bottomOpen: !bottomOpen, showTransects: false })}>
            Close
          </button>
        </div>
      </div>
      {j && o ? (
        <div className="cross-section-body">
          <div className="chart-svg-wrap">
            <svg
              viewBox={`0 0 ${W} ${H}`}
              width="100%"
              height="100%"
              role="img"
              aria-label="Measured June and October beach heights"
              onPointerMove={(e) => {
                const b = e.currentTarget.getBoundingClientRect();
                setHover(
                  Math.max(
                    xmin,
                    Math.min(xmax, xmin + (((((e.clientX - b.left) / b.width) * W - left) / (W - left - right)) * (xmax - xmin))),
                  ),
                );
              }}
              onPointerLeave={() => setHover(null)}
            >
              {[0, 0.25, 0.5, 0.75, 1].map((f) => {
                const z = zmin + (zmax - zmin) * f;
                const x = xmin + (xmax - xmin) * f;
                return (
                  <g key={f}>
                    <line x1={left} x2={W - right} y1={sy(z)} y2={sy(z)} stroke="#e6e8e0" />
                    <text x={left - 6} y={sy(z) + 3} textAnchor="end" fontSize="9" fill="#6b7064">
                      {z.toFixed(1)} m
                    </text>
                    <text x={sx(x)} y={H - 6} textAnchor="middle" fontSize="9" fill="#6b7064">
                      {x.toFixed(0)} m
                    </text>
                  </g>
                );
              })}
              {MHW_NAVD88_M >= zmin && MHW_NAVD88_M <= zmax && (
                <g>
                  <line x1={left} x2={W - right} y1={sy(MHW_NAVD88_M)} y2={sy(MHW_NAVD88_M)} stroke="#4c84a8" strokeDasharray="3 3" strokeWidth="1" />
                  <text x={W - right - 2} y={sy(MHW_NAVD88_M) - 3} textAnchor="end" fontSize="8.5" fill="#21577a">
                    NOAA MHW {MHW_NAVD88_M.toFixed(3)} m
                  </text>
                </g>
              )}
              {guides &&
                t?.boundaries
                  .filter((b) => b.x_m >= xmin && b.x_m <= xmax)
                  .map((b, i) => {
                    const color = b.type === 'optical' ? '#21577a' : b.type === 'terrain' ? '#1e6049' : '#9c6224';
                    const dash = b.type === 'radar' ? '1.5 2.5' : b.type === 'terrain' ? undefined : '4 2.5';
                    return (
                      <line
                        key={i}
                        x1={sx(b.x_m)}
                        x2={sx(b.x_m)}
                        y1={top}
                        y2={H - bottom}
                        stroke={color}
                        strokeWidth="1.25"
                        strokeDasharray={dash}
                      >
                        <title>
                          {b.sensor} · {b.definition} · {b.acquired_at ?? 'undated'} · {b.x_frf_m?.toFixed(1) ?? '—'} m FRF
                        </title>
                      </line>
                    );
                  })}
              <path d={path(j.points)} fill="none" stroke="#22251f" strokeWidth="2" />
              <path d={path(o.points)} fill="none" stroke="#858a7e" strokeWidth="2" strokeDasharray="5 3" />
              {hover !== null && <line x1={sx(hover)} x2={sx(hover)} y1={top} y2={H - bottom} stroke="#2f342b" strokeWidth="1" />}
            </svg>
          </div>
          <div className="slot-card">
            <div style={{ fontWeight: 500 }}>━ June · ┄ October</div>
            <p className="slot-meta num">
              {j.acquired_at?.slice(0, 10)} / {o.acquired_at?.slice(0, 10)}
              <br />
              {j.vertical_datum}
            </p>
            {hover === null ? (
              <p className="slot-meta">Hover profile for paired LiDAR heights (x in FRF m = x_m + {xOrigin} m).</p>
            ) : (
              <p className="slot-meta num">
                x: {hover.toFixed(1)} m ({(hover + xOrigin).toFixed(1)} m FRF)
                <br />
                Jun z: {hj ? `${hj.z_m.toFixed(2)} m` : 'No return'}
                <br />
                Oct z: {ho ? `${ho.z_m.toFixed(2)} m` : 'No return'}
                <br />
                Δz (Oct−Jun): {change ? `${change.dz_m >= 0 ? '+' : ''}${change.dz_m.toFixed(2)} m` : 'No paired return'}
              </p>
            )}
          </div>
        </div>
      ) : (
        <p className="slot-meta" role="status" style={{ padding: 14 }}>
          {detail?.reason ?? 'Loading measured profile…'}
        </p>
      )}
    </section>
  );
}
