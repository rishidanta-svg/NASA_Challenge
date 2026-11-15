import { useEffect, useState } from 'react';
import { getAnalysis, getTransect, type Sourced } from '../api/client';
import type { Analysis, Profile, TransectDetail } from '../api/schemas';
import { useApp } from '../state/store';
import { DataStateBadge } from './DataStateBadge';

export function CrossSection() {
  const { selectedTransectId, bottomOpen, set } = useApp();
  const [detail, setDetail] = useState<Sourced<TransectDetail> | null>(null);
  const [analysis, setAnalysis] = useState<Sourced<Analysis> | null>(null);
  const [showModel, setShowModel] = useState(true);
  const [showGuides, setShowGuides] = useState(true);
  const [hoverX, setHoverX] = useState<number | null>(null);

  useEffect(() => {
    if (!selectedTransectId) return;
    let cancelled = false;
    setDetail(null);
    setAnalysis(null);
    void getTransect(selectedTransectId).then((result) => {
      if (!cancelled) setDetail(result);
    });
    void getAnalysis(selectedTransectId).then((result) => {
      if (!cancelled) setAnalysis(result);
    });
    return () => {
      cancelled = true;
    };
  }, [selectedTransectId]);

  const t = detail?.data;
  const a = analysis?.data;
  const june: Profile | undefined = t?.profiles[0];
  const october: Profile | undefined = t?.profiles[1];
  const xOrigin = t?.properties.x_origin_frf_m ?? a?.x_origin_frf_m ?? 0;
  const modelPoints = a?.physics_model?.status === 'available' ? a.physics_model.points : [];
  const octAnalysis = a?.epochs.find((e) => e.date === '2026-10') ?? a?.epochs[a.epochs.length - 1];
  const junAnalysis = a?.epochs.find((e) => e.date === '2026-06') ?? a?.epochs[0];

  const W = 760;
  const H = 155;
  const pad = { l: 44, r: 16, t: 16, b: 24 };

  const allPts = [...(june?.points ?? []), ...(october?.points ?? [])];
  const xMin = allPts.length ? Math.min(...allPts.map((p) => p.x_m)) : 0;
  const xMax = allPts.length ? Math.max(...allPts.map((p) => p.x_m)) : 250;
  const zMin = allPts.length ? Math.floor(Math.min(...allPts.map((p) => p.z_m)) - 1) : -3;
  const zMax = allPts.length ? Math.ceil(Math.max(...allPts.map((p) => p.z_m)) + 1) : 8;

  const sx = (x: number) => pad.l + ((x - xMin) / (xMax - xMin || 1)) * (W - pad.l - pad.r);
  const sy = (z: number) => pad.t + ((zMax - z) / (zMax - zMin || 1)) * (H - pad.t - pad.b);

  const linePath = (pts: { x_m: number; z_m: number }[], maxStep = Infinity) =>
    pts.map((p, i) => `${i === 0 || p.x_m - pts[i - 1]!.x_m > maxStep ? 'M' : 'L'}${sx(p.x_m).toFixed(1)},${sy(p.z_m).toFixed(1)}`).join(' ');

  const modelBandPath = () => {
    if (!modelPoints.length) return '';
    const upper = modelPoints.map((p, i) => `${i === 0 ? 'M' : 'L'}${sx(p.x_m).toFixed(1)},${sy(p.z_m + p.sigma_m).toFixed(1)}`);
    const lower = [...modelPoints]
      .reverse()
      .map((p) => `L${sx(p.x_m).toFixed(1)},${sy(p.z_m - p.sigma_m).toFixed(1)}`);
    return `${upper.join(' ')} ${lower.join(' ')} Z`;
  };

  const nearest = <T extends { x_m: number }>(pts: T[] | undefined, x: number): T | null => {
    if (!pts?.length) return null;
    return pts.reduce((best, p) => (Math.abs(p.x_m - x) < Math.abs(best.x_m - x) ? p : best));
  };

  const hJune = hoverX !== null ? nearest(june?.points, hoverX) : null;
  const hOct = hoverX !== null ? nearest(october?.points, hoverX) : null;
  const hMod = hoverX !== null ? nearest(modelPoints, hoverX) : null;

  return (
    <section
      className={`cross-section-dock ${bottomOpen ? '' : 'collapsed'}`}
      aria-label="Elevation Cross-Section Panel"
      data-testid="cross-section"
    >
      <div className="cross-section-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span className="eyebrow">CROSS-SHORE ELEVATION PROFILE</span>
          <strong>{t ? `${t.properties.label} (${t.properties.id})` : 'No transect selected'}</strong>
          {detail && <DataStateBadge state={detail.state} />}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 11.5 }}>
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: 5, cursor: 'pointer' }}>
            <input type="checkbox" checked={showGuides} onChange={(e) => setShowGuides(e.target.checked)} />
            <span>Sensor boundaries</span>
          </label>
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: 5, cursor: 'pointer' }}>
            <input type="checkbox" checked={showModel} onChange={(e) => setShowModel(e.target.checked)} />
            <span style={{ color: 'var(--purple)' }}>Bayesian state / CI90 (inferred)</span>
          </label>
          <button
            onClick={() => set({ bottomOpen: !bottomOpen })}
            style={{ padding: '2px 8px', fontSize: 10.5 }}
            aria-label={bottomOpen ? 'Collapse profile dock' : 'Expand profile dock'}
          >
            {bottomOpen ? '▼ Hide' : '▲ Expand'}
          </button>
        </div>
      </div>

      {bottomOpen && t && june && october && (
        <div className="cross-section-body">
          <div className="chart-svg-wrap">
            <svg
              viewBox={`0 0 ${W} ${H}`}
              width="100%"
              height="100%"
              preserveAspectRatio="none"
              role="img"
              aria-label={`Cross-shore elevation profile for ${t.properties.label}`}
              onPointerMove={(e) => {
                const r = e.currentTarget.getBoundingClientRect();
                const px = ((e.clientX - r.left) / r.width) * W;
                const x = xMin + ((px - pad.l) / (W - pad.l - pad.r)) * (xMax - xMin);
                setHoverX(Math.max(xMin, Math.min(xMax, x)));
              }}
              onPointerLeave={() => setHoverX(null)}
            >
              {/* Horizontal z grid lines */}
              {[0, 0.25, 0.5, 0.75, 1].map((f) => {
                const z = zMin + (zMax - zMin) * f;
                const y = sy(z);
                return (
                  <g key={f}>
                    <line
                      x1={pad.l}
                      y1={y}
                      x2={W - pad.r}
                      y2={y}
                      stroke="#223241"
                      strokeDasharray={Math.abs(z) < 0.01 ? undefined : '2 4'}
                    />
                    <text x={pad.l - 6} y={y + 3} textAnchor="end" fill="#8b9eaf" fontSize="9" fontFamily="monospace">
                      {z.toFixed(1)}m
                    </text>
                  </g>
                );
              })}

              {/* X-axis distance ticks */}
              {[0, 50, 100, 150, 200, 250].map((x) => (
                <text
                  key={x}
                  x={sx(x)}
                  y={H - 6}
                  textAnchor="middle"
                  fill="#8b9eaf"
                  fontSize="9"
                  fontFamily="monospace"
                >
                  {x} m
                </text>
              ))}

              {/* Separate sensor boundary guides */}
              {showGuides &&
                t.boundaries
                  .filter((b) => b.x_m >= xMin - 5 && b.x_m <= xMax + 5)
                  .map((b, idx) => {
                    const x = sx(b.x_m);
                    const col = b.type === 'radar' ? '#65dfce' : b.type === 'optical' ? '#edbf7c' : '#db9d82';
                    return (
                      <g key={`${b.type}-${b.sensor}-${b.epoch_label}-${idx}`}>
                        <line
                          x1={x}
                          y1={pad.t}
                          x2={x}
                          y2={H - pad.b}
                          stroke={col}
                          strokeOpacity={0.45}
                          strokeDasharray="3 3"
                        />
                        <text x={x + 3} y={pad.t + 9 + (idx % 6) * 11} fill={col} fontSize="7.5" fontFamily="monospace">
                          {b.sensor} ({b.epoch_label.slice(0, 3)})
                        </text>
                      </g>
                    );
                  })}

              {/* Bayesian reconstructed horizontal boundary intervals (90% CI) + accepted dune-toe / waterline */}
              {showModel &&
                [junAnalysis, octAnalysis].filter(Boolean).map((ep, idx) => {
                  if (!ep) return null;
                  const dt = ep.dunetoe;
                  const ciLow = dt.ci90_low_m;
                  const ciHigh = dt.ci90_high_m;
                  const acc = dt.accepted_x_m;
                  const labelTag = ep.date === '2026-06' ? 'Jun' : 'Oct';
                  return (
                    <g key={`bayes-${ep.date}`}>
                      {ciLow !== null && ciHigh !== null && (
                        <rect
                          x={sx(Math.max(xMin, ciLow))}
                          y={pad.t}
                          width={Math.max(2, sx(Math.min(xMax, ciHigh)) - sx(Math.max(xMin, ciLow)))}
                          height={H - pad.t - pad.b}
                          fill="rgba(213, 139, 216, 0.12)"
                        />
                      )}
                      {acc !== null && (
                        <>
                          <line
                            x1={sx(acc)}
                            y1={pad.t}
                            x2={sx(acc)}
                            y2={H - pad.b}
                            stroke="#d58bd8"
                            strokeWidth="1.6"
                            strokeDasharray="5 2"
                          />
                          <text
                            x={sx(acc) + 3}
                            y={H - pad.b - 6 - idx * 11}
                            fill="#d58bd8"
                            fontSize="8"
                            fontFamily="monospace"
                          >
                            Bayes Dune ({labelTag})
                          </text>
                        </>
                      )}
                    </g>
                  );
                })}

              {/* Optional vertical physics-model 1σ uncertainty band + curve when Physics V1 profile is provided */}
              {showModel && modelPoints.length >= 2 && (
                <>
                  <path d={modelBandPath()} fill="rgba(213, 139, 216, 0.18)" />
                  <path
                    d={linePath(modelPoints)}
                    fill="none"
                    stroke="#d58bd8"
                    strokeWidth="1.6"
                    strokeDasharray="4 3"
                  />
                </>
              )}

              {/* Measured / primary epoch curves */}
              <path d={linePath(june.points, 1.01)} fill="none" stroke="#65dfce" strokeWidth="2" />
              <path d={linePath(october.points, 1.01)} fill="none" stroke="#edbf7c" strokeWidth="2" />

              {hoverX !== null && (
                <line
                  x1={sx(hoverX)}
                  y1={pad.t}
                  x2={sx(hoverX)}
                  y2={H - pad.b}
                  stroke="#e5edf3"
                  strokeOpacity={0.6}
                />
              )}
            </svg>
          </div>

          <div className="slot-card" style={{ margin: 0, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
            <div>
              <div style={{ display: 'flex', gap: 10, fontSize: 11, fontFamily: 'var(--font-mono)', flexWrap: 'wrap' }}>
                <span style={{ color: '#65dfce' }}>━ June LiDAR</span>
                <span style={{ color: '#edbf7c' }}>━ Oct LiDAR</span>
                {showModel && <span style={{ color: '#d58bd8' }}>┅ Bayes Dune (90% CI)</span>}
              </div>
              <div className="mono" style={{ fontSize: 11, marginTop: 8, lineHeight: 1.5 }}>
                {hoverX !== null && hJune && hOct ? (
                  <>
                    <div>
                      Along transect = {hJune.x_m.toFixed(1)} m (FRF x = {(hJune.x_m + xOrigin).toFixed(1)} m)
                    </div>
                    <div>
                      June z = {hJune.z_m.toFixed(2)} m · Oct z = {hOct.z_m.toFixed(2)} m (Δz ={' '}
                      {(hOct.z_m - hJune.z_m).toFixed(2)} m)
                    </div>
                    {showModel && hMod && (
                      <div style={{ color: 'var(--purple)' }}>
                        Model z = {hMod.z_m.toFixed(2)} ± {hMod.sigma_m.toFixed(2)} m
                      </div>
                    )}
                  </>
                ) : octAnalysis ? (
                  <>
                    <div>
                      <strong>Oct S2 Waterline:</strong> FRF x = {octAnalysis.waterline.x_frf_m?.toFixed(1) ?? '—'} m (±
                      {octAnalysis.waterline.cv_rmse_m?.toFixed(1) ?? '—'} m)
                    </div>
                    <div style={{ color: 'var(--purple)' }}>
                      <strong>Oct Bayes Dune:</strong>{' '}
                      {octAnalysis.dunetoe.accepted_x_frf_m !== null
                        ? `FRF x = ${octAnalysis.dunetoe.accepted_x_frf_m.toFixed(1)} m (90% CI ${octAnalysis.dunetoe.ci90_low_frf_m?.toFixed(1)}–${octAnalysis.dunetoe.ci90_high_frf_m?.toFixed(1)} m)`
                        : `Withheld (${octAnalysis.dunetoe.status})`}
                    </div>
                  </>
                ) : (
                  <span className="muted">Hover across the cross-section to inspect x/z values and uncertainty.</span>
                )}
              </div>
            </div>
            <div className="slot-meta">
              Datum: {june.vertical_datum} · Units: {june.units} · {t.properties.x_reference}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
