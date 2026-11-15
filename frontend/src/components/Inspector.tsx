import { useEffect, useState } from 'react';
import { getAnalysis, getTransect, type Sourced } from '../api/client';
import type { Analysis, TransectDetail } from '../api/schemas';
import { ANALYSIS_CRS, STUDY_BOUNDS } from '../config/geo';
import { lngLatToFrf, lngLatToUtm18N } from '../lib/frf';
import { sampleAwsElevation, type TerrainSample } from '../lib/terrarium';
import { flyToLngLat } from '../map/registry';
import { useApp } from '../state/store';
import { DataStateBadge } from './DataStateBadge';
import { CoastalEvidence } from './CoastalEvidence';
import { EnvironmentPanel } from './EnvironmentPanel';

export function Inspector() {
  const { selectedTransectId, inspected, terrainChange, drawer, mapErrors, set } = useApp();
  const [transect, setTransect] = useState<Sourced<TransectDetail> | null>(null);
  const [analysis, setAnalysis] = useState<Sourced<Analysis> | null>(null);
  const [awsSample, setAwsSample] = useState<TerrainSample | null>(null);
  const [awsError, setAwsError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedTransectId) {
      setTransect(null);
      setAnalysis(null);
      return;
    }
    let cancelled = false;
    setTransect(null);
    setAnalysis(null);
    void getTransect(selectedTransectId).then((result) => {
      if (!cancelled) setTransect(result);
    });
    void getAnalysis(selectedTransectId).then((result) => {
      if (!cancelled) setAnalysis(result);
    });
    return () => {
      cancelled = true;
    };
  }, [selectedTransectId]);

  useEffect(() => {
    if (!inspected) {
      setAwsSample(null);
      setAwsError(null);
      return;
    }
    let cancelled = false;
    setAwsSample(null);
    setAwsError(null);
    sampleAwsElevation(inspected.lng, inspected.lat)
      .then((s) => {
        if (!cancelled) setAwsSample(s);
      })
      .catch((err) => {
        if (!cancelled) setAwsError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [inspected]);

  const pointCoords = inspected
    ? (() => {
        const [utmE, utmN] = lngLatToUtm18N(inspected.lng, inspected.lat);
        const [frfX, frfY] = lngLatToFrf(inspected.lng, inspected.lat);
        const inside =
          inspected.lng >= STUDY_BOUNDS.west &&
          inspected.lng <= STUDY_BOUNDS.east &&
          inspected.lat >= STUDY_BOUNDS.south &&
          inspected.lat <= STUDY_BOUNDS.north;
        return { utmE, utmN, frfX, frfY, inside };
      })()
    : null;

  const tData = transect?.data;
  const aData = analysis?.data;

  return (
    <aside className={`sidebar-right ${drawer === 'right' ? 'open' : ''}`} aria-label="Location and Sensor Inspector">
      {/* Clicked Point Inspection */}
      <section className="panel-section">
        <div className="panel-heading">
          <h2>Location Inspector</h2>
          {inspected && (
            <div style={{ display: 'flex', gap: 5 }}>
              <button
                onClick={() => flyToLngLat(inspected.lng, inspected.lat, 17)}
                style={{ padding: '2px 7px', fontSize: 10 }}
              >
                Zoom to pin
              </button>
              <button onClick={() => set({ inspected: null })} style={{ padding: '2px 7px', fontSize: 10 }}>
                Clear
              </button>
            </div>
          )}
        </div>

        {!inspected || !pointCoords ? (
          <div className="slot-meta">
            Click anywhere on the coastal map to inspect coordinates in WGS84, {ANALYSIS_CRS}, and local FRF metres, and
            sample regional elevation.
          </div>
        ) : (
          <>
            <div className="kv-grid">
              <div className="kv-cell">
                <small>WGS84 LAT / LON</small>
                <strong>
                  {inspected.lat.toFixed(6)}° N, {inspected.lng.toFixed(6)}° W
                </strong>
              </div>
              <div className="kv-cell">
                <small>FRF LOCAL (x, y)</small>
                <strong>
                  x = {pointCoords.frfX.toFixed(1)} m, y = {pointCoords.frfY.toFixed(1)} m
                </strong>
              </div>
              <div className="kv-cell">
                <small>UTM 18N ({ANALYSIS_CRS})</small>
                <strong>
                  {pointCoords.utmE.toFixed(1)} E, {pointCoords.utmN.toFixed(1)} N
                </strong>
              </div>
              <div className="kv-cell">
                <small>STUDY AREA CHECK</small>
                <strong style={{ color: pointCoords.inside ? 'var(--cyan)' : 'var(--gold)' }}>
                  {pointCoords.inside ? 'Inside study box' : 'Outside study box'}
                </strong>
              </div>
            </div>

            <div className="slot-card" style={{ marginTop: 8 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span className="eyebrow">REGIONAL ELEVATION SAMPLE</span>
                <span className="badge badge-real">AWS TERRARIUM z15</span>
              </div>
              <div className="mono" style={{ fontSize: 13, fontWeight: 600, marginTop: 4 }}>
                {awsSample
                  ? `${awsSample.elevation_m.toFixed(2)} m (pixel ≈ ${awsSample.pixel_size_m.toFixed(1)} m)`
                  : awsError
                    ? `Unavailable: ${awsError}`
                    : 'Sampling tile…'}
              </div>
              <div className="slot-meta">
                Coarse regional elevation tile — not equivalent to 1 m USACE LiDAR bare-earth elevation.
              </div>
            </div>
          </>
        )}
      </section>

      {/* Selected Transect & Sensor Boundary Evidence */}
      <section className="panel-section">
        <div className="panel-heading">
          <h2>Transect &amp; Sensor Evidence</h2>
          {transect && <DataStateBadge state={transect.state} />}
        </div>

        {!tData ? (
          <div className="slot-meta">Select a shore-normal transect on the map or in the left sidebar.</div>
        ) : (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <strong style={{ fontSize: 14 }}>{tData.properties.label}</strong>
              <span className="mono muted" style={{ fontSize: 11 }}>
                {tData.properties.id}
              </span>
            </div>
            <div className="slot-meta" style={{ marginBottom: 8 }}>
              Reference: {tData.properties.x_reference}
            </div>

            <div className="eyebrow" style={{ marginBottom: 5 }}>
              SEPARATE SENSOR BOUNDARY PICKS
            </div>
            {tData.boundaries.map((b, i) => (
              <div key={`${b.type}-${b.sensor}-${b.epoch_label}-${i}`} className="env-row">
                <div>
                  <div style={{ fontSize: 11.5, fontWeight: 500 }}>
                    <span
                      style={{
                        color:
                          b.type === 'radar'
                            ? 'var(--cyan)'
                            : b.type === 'optical'
                              ? 'var(--gold)'
                              : '#db9d82',
                      }}
                    >
                      [{b.type.toUpperCase()}]
                    </span>{' '}
                    {b.sensor} · {b.definition}
                  </div>
                  <div className="mono muted" style={{ fontSize: 9.5 }}>
                    {b.epoch_label}
                  </div>
                </div>
                <div className="mono" style={{ fontSize: 11.5, whiteSpace: 'nowrap', textAlign: 'right' }}>
                  <div>
                    FRF x = {(b.x_frf_m ?? b.x_m).toFixed(1)} m
                    {b.uncertainty_m != null ? ` ± ${b.uncertainty_m} m` : ''}
                  </div>
                  <div className="muted" style={{ fontSize: 9.5 }}>
                    line Δx = {b.x_m.toFixed(1)} m
                  </div>
                </div>
              </div>
            ))}

            {aData && (
              <div className="slot-card" style={{ marginTop: 8 }} data-testid="analysis-card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span className="eyebrow">COASTAL BOUNDARY RECONSTRUCTION</span>
                  <DataStateBadge state={analysis?.state ?? 'unavailable'} inferred />
                </div>
                <div className="slot-meta" style={{ marginTop: 4 }}>
                  <strong>{aData.model_name}</strong> ({aData.model_version})
                </div>
                <div className="slot-meta">Scope: {aData.state_scope}</div>
                {aData.october_minus_june && (
                  <div className="mono" style={{ fontSize: 11, marginTop: 6, lineHeight: 1.5 }}>
                    <div>
                      <strong>Oct − Jun Waterline Δx:</strong>{' '}
                      {aData.october_minus_june.waterline_shift_m !== null
                        ? `${aData.october_minus_june.waterline_shift_m > 0 ? '+' : ''}${aData.october_minus_june.waterline_shift_m.toFixed(2)} m`
                        : '—'}
                    </div>
                    <div>
                      <strong>Oct − Jun Dune-Toe Δx:</strong>{' '}
                      {aData.october_minus_june.dunetoe_shift_m !== null
                        ? `${aData.october_minus_june.dunetoe_shift_m > 0 ? '+' : ''}${aData.october_minus_june.dunetoe_shift_m.toFixed(2)} m`
                        : 'Withheld (VV/VH disagreement)'}
                    </div>
                  </div>
                )}

                <div style={{ marginTop: 8, borderTop: '1px solid #1e2d3b', paddingTop: 6 }}>
                  {aData.epochs.map((ep) => (
                    <div key={ep.date} className="mono" style={{ fontSize: 10.5, marginBottom: 6, lineHeight: 1.45 }}>
                      <div style={{ color: 'var(--cyan)', fontWeight: 600 }}>{ep.epoch_label}</div>
                      <div>
                        Legacy S2 NDWI Waterline: FRF x = {ep.waterline.x_frf_m?.toFixed(2) ?? '—'} m
                        {' (CV RMSE '}{ep.waterline.cv_rmse_m?.toFixed(2) ?? '—'} m)
                      </div>
                      <div style={{ color: 'var(--purple)' }}>
                        S1 Bayes Dune Toe:{' '}
                        {ep.dunetoe.accepted_x_frf_m !== null
                          ? `FRF x = ${ep.dunetoe.accepted_x_frf_m.toFixed(1)} m (90% CI ${ep.dunetoe.ci90_low_frf_m?.toFixed(1)}–${ep.dunetoe.ci90_high_frf_m?.toFixed(1)} m, SD ${ep.dunetoe.posterior_sd_m?.toFixed(1)} m)`
                          : `Withheld — ${ep.dunetoe.status} (MAP ${ep.dunetoe.bayes_map_x_frf_m?.toFixed(1) ?? '—'} m, |VV−VH| = ${ep.dunetoe.vv_vh_disagreement_m?.toFixed(1) ?? '—'} m)`}
                      </div>
                    </div>
                  ))}
                </div>

                <div className="slot-meta" style={{ marginTop: 4, borderTop: '1px solid #1e2d3b', paddingTop: 5 }}>
                  <strong>Physics Profile Model:</strong>{' '}
                  {aData.physics_model?.status === 'available'
                    ? `Active (${aData.physics_model.points.length} profile nodes)`
                    : aData.physics_model?.reason ?? 'Awaiting V1 integration'}
                </div>
              </div>
            )}
          </>
        )}

        {terrainChange?.data && (
          <div className="slot-meta" style={{ marginTop: 8 }}>
            <strong>LiDAR Δz Datum:</strong> {terrainChange.data.vertical_datum} ({terrainChange.data.units})
          </div>
        )}
      </section>

      <CoastalEvidence waterlines={aData?.coastal_observations?.waterlines ?? []} />

      {/* Live NOAA Station 8651370 Observations */}
      <EnvironmentPanel />

      {mapErrors.length > 0 && (
        <section className="panel-section">
          <div className="eyebrow" style={{ color: 'var(--danger)' }}>
            TILE / NETWORK DIAGNOSTICS
          </div>
          {mapErrors.map((m, i) => (
            <div key={i} className="slot-meta" style={{ color: 'var(--danger)' }}>
              {m}
            </div>
          ))}
        </section>
      )}
    </aside>
  );
}
