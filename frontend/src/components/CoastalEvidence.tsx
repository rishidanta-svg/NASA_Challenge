import { useEffect, useState } from 'react';
import { getCoastalEvidence, type Sourced } from '../api/client';
import type { CoastalEvidence as Evidence, WaterlineEpoch } from '../api/schemas';
import { useApp } from '../state/store';

const meters = (n: number | null | undefined) => n == null ? '—' : `${n.toFixed(2)} m`;
const utc = (value: string) => value.slice(0, 19).replace('T', ' ') + ' UTC';

export function CoastalEvidence({ waterlines }: { waterlines: WaterlineEpoch[] }) {
  const [summary, setSummary] = useState<Sourced<Evidence> | null>(null);
  const showSetup = useApp((s) => s.slots['physics-s2-setup']?.visible);
  useEffect(() => {
    let active = true;
    void getCoastalEvidence().then((result) => { if (active) setSummary(result); });
    return () => { active = false; };
  }, []);

  const data = summary?.data;
  const radar = data?.radar_disagreement;
  const targets = data?.validation.targets;
  const fixed = targets?.fixed_mhw_contour;
  const wetDry = targets?.survey_level_wet_dry_proxy;
  const show = (position: WaterlineEpoch['tide']) => position.status === 'withheld'
    ? `Withheld — ${position.reasons.join('. ')}` : meters(position.x_frf_m);

  return (
    <section className="panel-section" aria-label="Physics-guided coastal observations" data-testid="coastal-evidence">
      <div className="panel-heading"><h2>Coastal observations</h2></div>
      {!data && <p className="slot-meta">{summary?.reason ?? 'Loading validation and radar comparisons…'}</p>}
      {data?.status === 'withheld' && <p className="slot-meta">{data.reasons.join('. ')}</p>}
      {!waterlines.length && <p className="slot-meta">Select a transect to compare optical positions.</p>}
      {waterlines.map((row) => (
        <details className="slot-card coastal-detail" key={row.acquisition_id}>
          <summary>Sentinel‑2 · {utc(row.acquired_at)}</summary>
          <div className="slot-meta">FRF x increases seaward</div>
          <div>Raw NDWI · {show(row.ndwi)}</div>
          <div>Raw MNDWI · {show(row.mndwi)}</div>
          <div data-testid={`tide-${row.date}`}>Tide-corrected to mean high water · {show(row.tide)}</div>
          {row.tide.sigma_m != null && <div>Position uncertainty (1σ) · {meters(row.tide.sigma_m)}</div>}
          {row.tide.slope_sensitivity_frf_m && (
            <div className="slot-meta">Slope sensitivity · {meters(row.tide.slope_sensitivity_frf_m[0])} to {meters(row.tide.slope_sensitivity_frf_m[1])}</div>
          )}
          {row.tide.status === 'conditional' && <div className="slot-meta">{row.tide.reasons.join('. ')}.</div>}
          {showSetup && <div>Experimental wave setup · {show(row.setup)}</div>}
          {row.environment && (
            <div className="slot-meta">
              Duck gauge · {meters(row.environment.water_level_m_mllw)} MLLW
              {row.environment.water_level_timestamp_utc && ` at ${utc(row.environment.water_level_timestamp_utc)}`}
              <br />
              FRF buoy Hs · {meters(row.environment.wave_hs_m_17m)} · Tp {row.environment.wave_tp_s_17m ?? '—'} s
              {row.environment.wave_dir_deg_17m != null && ` · ${row.environment.wave_dir_deg_17m}° true from`}
              <br />
              Wind · {row.environment.wind_speed_ms ?? '—'} m/s · gust {row.environment.wind_gust_ms ?? '—'} m/s
              <br />
              Rain over prior 24 h · {row.environment.rain_24h_mm ?? '—'} mm
            </div>
          )}
        </details>
      ))}
      {data && fixed && wetDry && (
        <details className="slot-card coastal-detail" open>
          <summary>Waterline validation</summary>
          <div className="slot-meta">{data.validation.scope}</div>
          <Validation label="October mean-high-water contour" comparison={fixed.raw_vs_tide} />
          <Validation label="June and October wet/dry proxy" comparison={wetDry.raw_vs_tide} />
          {showSetup && <Validation label="Experimental setup on the same contour samples" comparison={fixed.raw_vs_tide_vs_setup} />}
        </details>
      )}
      {radar && (
        <details className="slot-card coastal-detail">
          <summary>Radar disagreement · {radar.opposite_strict_cells ?? '—'} / {radar.strict_overlap_cells ?? '—'} strict cells</summary>
          {radar.matched_radar_cells != null && (
            <div>{radar.opposite_radar_cells} / {radar.matched_radar_cells} across shared radar coverage.</div>
          )}
          {Object.entries(radar.acquisitions ?? {}).map(([sensor, epochs]) => (
            <div className="slot-meta" key={sensor}>
              {sensor} · {Object.values(epochs).map((epoch) => utc(epoch.acquired_at)).join(' → ')}
            </div>
          ))}
          <div className="slot-meta">{radar.reasons.join('. ')}.</div>
        </details>
      )}
    </section>
  );
}

type Comparison = Evidence['validation']['targets'][string]['raw_vs_tide'];

function Validation({ label, comparison }: { label: string; comparison: Comparison }) {
  return (
    <div className="coastal-validation">
      <strong>{label} · {comparison.n} rows</strong>
      {comparison.reason && <div>{comparison.reason}</div>}
      {Object.entries(comparison.methods ?? {}).map(([method, value]) => (
        <div key={method}>
          {method === 'raw' ? 'Raw' : method === 'tide' ? 'Tide' : 'Tide + setup'} · RMSE {meters(value.rmse_m)} · MAE {meters(value.mae_m)} · bias {meters(value.bias_m)}
        </div>
      ))}
    </div>
  );
}
