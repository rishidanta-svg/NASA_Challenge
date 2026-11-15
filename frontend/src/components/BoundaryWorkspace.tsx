import { useEffect, useState } from 'react';
import { getAnalysis, getCoastalEvidence, getNisarEvidence, type Sourced } from '../api/client';
import type { Analysis, CoastalEvidence, NisarEvidence } from '../api/schemas';
import { useApp } from '../state/store';

const metres = (v: number | null | undefined) => (v == null ? 'Not available' : `${v.toFixed(2)} m`);
const numFixed = (v: number | null | undefined, digits = 2, unit = '') =>
  v == null ? 'Not available' : `${v.toFixed(digits)}${unit ? ` ${unit}` : ''}`;

const modelNames: Record<string, string> = {
  zero_change: 'Assume no change',
  training_mean: 'Training-set mean change',
  A: 'NISAR only',
  B: 'Sentinel-1 + Sentinel-2',
  C: 'Sentinel-1 + Sentinel-2 + NISAR',
};

interface UnlabeledRange {
  unit: string;
  n: number;
  range: [number, number];
}

function fmtRange(r: UnlabeledRange | undefined): string {
  if (!r) return 'Not available';
  return `${r.range[0].toFixed(2)} to ${r.range[1].toFixed(2)} ${r.unit}`;
}

export function BoundaryWorkspace() {
  const { selectedTransectId, transects, date, set } = useApp();
  const [tab, setTab] = useState<'observations' | 'experiments'>('observations');
  const [analysis, setAnalysis] = useState<Sourced<Analysis> | null>(null);
  const [coastal, setCoastal] = useState<Sourced<CoastalEvidence> | null>(null);
  const [nisar, setNisar] = useState<Sourced<NisarEvidence> | null>(null);
  const [epoch, setEpoch] = useState(date.startsWith('2026-10') ? '2026-10' : '2026-06');

  useEffect(() => {
    let active = true;
    void getCoastalEvidence().then((r) => {
      if (active) setCoastal(r);
    });
    void getNisarEvidence().then((r) => {
      if (active) setNisar(r);
    });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    setAnalysis(null);
    if (selectedTransectId) {
      void getAnalysis(selectedTransectId).then((r) => {
        if (active) setAnalysis(r);
      });
    }
    return () => {
      active = false;
    };
  }, [selectedTransectId]);

  const a = analysis?.data;
  const c = coastal?.data;
  const n = nisar?.data;
  const t = n?.terrain_ablation;
  const row = a?.coastal_observations?.waterlines.find((w) => w.date === epoch);
  const terrain = a?.coastal_observations?.terrain;
  const validProfile = terrain?.change_profile ?? [];
  const mean = validProfile.length ? validProfile.reduce((sum, p) => sum + p.dz_m, 0) / validProfile.length : null;

  const mhwCheck = c?.validation.targets.fixed_mhw_contour;
  const rawRmse = mhwCheck?.raw_vs_tide.methods?.raw?.rmse_m;
  const tideRmse = mhwCheck?.raw_vs_tide.methods?.tide?.rmse_m;
  const setupRmse = mhwCheck?.raw_vs_tide_vs_setup.methods?.setup?.rmse_m;
  const tideReduction = (mhwCheck?.raw_vs_tide as { rmse_reduction_percent?: Record<string, number> } | undefined)?.rmse_reduction_percent?.tide;
  const mhwN = mhwCheck?.raw_vs_tide.n;

  const unlabeled = (n?.input_qa as { unlabeled_features?: Record<string, UnlabeledRange> } | undefined)?.unlabeled_features;
  const nisarAcqJune = (n?.input_qa as { source_acquisitions?: { june?: Record<string, unknown> } } | undefined)?.source_acquisitions?.june;

  function download() {
    const payload = { coastal_observations: c, transect: a?.coastal_observations, nisar_experiment: n };
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'poltergeist-current-evidence.json';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return (
    <section className="boundary-workspace" aria-label="Coastal findings">
      <div className="panel-heading" style={{ marginBottom: 4 }}>
        <span className="eyebrow">Verified Coastal Evidence & Diagnostics</span>
        <span className="badge">Duck FRF · Jun–Oct 2026</span>
      </div>
      <h1>What the observations show</h1>
      <p className="intro">
        Independent LiDAR elevation truth, tide-corrected Sentinel-2 optical boundaries, environmental telemetry, and separate exploratory radar experiments.
      </p>

      <div className="findings-tabs" role="group" aria-label="Findings section">
        <button aria-pressed={tab === 'observations'} onClick={() => setTab('observations')}>
          Observations
        </button>
        <button aria-pressed={tab === 'experiments'} onClick={() => setTab('experiments')}>
          NISAR experiments
        </button>
      </div>

      {tab === 'observations' ? (
        <>
          {rawRmse != null && tideRmse != null && tideReduction != null && (
            <article className="verified-result-card" aria-label="Verified Sentinel-2 tide correction result">
              <div className="panel-heading">
                <span className="eyebrow">Primary Verified Optical Result · Sentinel-2</span>
                <span className="badge badge-observed num">−{tideReduction.toFixed(1)}% RMSE</span>
              </div>
              <p className="verified-headline">
                <strong className="num">{tideReduction.toFixed(1)}% reduction</strong> in Sentinel-2 shoreline-position RMSE across{' '}
                <strong className="num">{mhwN ?? 36}</strong> October LiDAR MHW contour positions (
                <span className="num">{c?.target?.value.toFixed(3) ?? '0.359'} m {c?.target?.vertical_datum ?? 'NAVD88'}</span>).
              </p>
              <div className="rmse-compare-bars" aria-label="Before and after tide correction RMSE visual">
                <div className="rmse-bar-row">
                  <div className="rmse-bar-label">
                    <span>Before tide correction (raw optical NDWI)</span>
                    <strong className="num">RMSE {rawRmse.toFixed(2)} m</strong>
                  </div>
                  <div className="rmse-track">
                    <div className="rmse-fill rmse-before" style={{ width: '100%' }} />
                  </div>
                </div>
                <div className="rmse-bar-row">
                  <div className="rmse-bar-label">
                    <span>After tide correction (NOAA water level + LiDAR slope)</span>
                    <strong className="num">RMSE {tideRmse.toFixed(2)} m</strong>
                  </div>
                  <div className="rmse-track">
                    <div className="rmse-fill rmse-after" style={{ width: `${Math.min(100, (tideRmse / rawRmse) * 100).toFixed(1)}%` }} />
                  </div>
                </div>
                {setupRmse != null && (
                  <div className="rmse-bar-row">
                    <div className="rmse-bar-label muted">
                      <span>Experimental + wave setup comparison</span>
                      <span className="num">RMSE {setupRmse.toFixed(2)} m</span>
                    </div>
                    <div className="rmse-track">
                      <div className="rmse-fill rmse-setup" style={{ width: `${Math.min(100, (setupRmse / rawRmse) * 100).toFixed(1)}%` }} />
                    </div>
                  </div>
                )}
              </div>
              <p className="slot-meta" style={{ marginBottom: 0 }}>
                <strong>Role of tide correction:</strong> Optical indices detect the instantaneous wet/dry edge at satellite overpass tide, not fixed MHW. Translating water-level elevation difference onto the surveyed foreshore slope reconciles apparent shoreline shift. Attributed strictly to Sentinel-2 optical physics — never NISAR.
              </p>
            </article>
          )}

          <div className="boundary-controls">
            <label>
              Location
              <select aria-label="Findings location" value={selectedTransectId ?? ''} onChange={(e) => set({ selectedTransectId: e.target.value })}>
                {(transects?.data ?? []).map((p, i) => (
                  <option key={p.properties.id} value={p.properties.id}>
                    Section {i + 1} · {p.properties.frf_y_m} m along coast
                  </option>
                ))}
              </select>
            </label>
            <label>
              Observation
              <select aria-label="Findings observation" value={epoch} onChange={(e) => setEpoch(e.target.value)}>
                <option value="2026-06">June 2026</option>
                <option value="2026-10">October 2026</option>
              </select>
            </label>
          </div>

          {!a ? (
            <p role="status">{analysis?.reason ?? 'Loading source observations…'}</p>
          ) : (
            <>
              <div className="boundary-cards">
                <article className="slot-card">
                  <div className="panel-heading">
                    <span className="eyebrow">Tide-adjusted waterline</span>
                    <span className="badge badge-estimated">Estimated</span>
                  </div>
                  <h2 className="num">{metres(row?.tide.x_frf_m)}</h2>
                  <p>
                    {row?.tide.status === 'withheld'
                      ? 'Withheld: physical inputs did not qualify.'
                      : `FRF cross-shore position adjusted to MHW (shift: ${row?.tide.shift_m != null ? `${row.tide.shift_m >= 0 ? '+' : ''}${row.tide.shift_m.toFixed(2)} m` : 'Not available'}).`}
                  </p>
                  <small>Conditional on foreshore slope · not a dune boundary</small>
                </article>
                <article className="slot-card">
                  <div className="panel-heading">
                    <span className="eyebrow">Measured beach height change</span>
                    <span className="badge badge-observed">Observed</span>
                  </div>
                  <h2 className="num">{metres(mean)}</h2>
                  <p>
                    Mean Oct − Jun height along this transect (study-wide paired mean:{' '}
                    <span className="num">{c?.terrain?.mean_m != null ? `${c.terrain.mean_m.toFixed(2)} m` : 'Not available'}</span> on{' '}
                    <span className="num">{c?.terrain?.native_paired_cells?.toLocaleString() ?? '17,466'}</span> cells).
                  </p>
                  <small>Measured USACE LiDAR (NAVD88), not satellite-predicted</small>
                </article>
              </div>

              <div className="env-telemetry-box">
                <div className="panel-heading">
                  <span className="eyebrow">Matched Environmental & Optical Variables ({epoch})</span>
                  <span className="badge">NOAA 8651370 + FRF</span>
                </div>
                <div className="telemetry-grid">
                  <div>
                    <small>Water level (Measured)</small>
                    <strong className="num">{numFixed(row?.environment?.water_level_m_mllw, 3, 'm MLLW')}</strong>
                  </div>
                  <div>
                    <small>Tide prediction (Est.)</small>
                    <strong className="num">
                      {row?.environment?.tide_prediction_m_mllw != null
                        ? `${row.environment.tide_prediction_m_mllw.toFixed(3)} m (${row.environment.predicted_tide_stage ?? '—'})`
                        : 'Not available'}
                    </strong>
                  </div>
                  <div>
                    <small>Wave Hs / Tp (17 m array)</small>
                    <strong className="num">
                      {row?.environment?.wave_hs_m_17m != null && row?.environment?.wave_tp_s_17m != null
                        ? `${row.environment.wave_hs_m_17m.toFixed(2)} m · ${row.environment.wave_tp_s_17m.toFixed(1)} s`
                        : 'Not available'}
                    </strong>
                  </div>
                  <div>
                    <small>Foreshore slope (LiDAR)</small>
                    <strong className="num">
                      {row?.tide.slope?.slope_m_per_m != null ? `${row.tide.slope.slope_m_per_m.toFixed(3)} m/m` : 'Not available'}
                    </strong>
                  </div>
                  <div>
                    <small>Wind speed / gust</small>
                    <strong className="num">
                      {row?.environment?.wind_speed_ms != null
                        ? `${row.environment.wind_speed_ms.toFixed(1)} / ${row.environment.wind_gust_ms?.toFixed(1) ?? '—'} m/s`
                        : 'Not available'}
                    </strong>
                  </div>
                  <div>
                    <small>S2 cloud fraction (SCL)</small>
                    <strong className="num">
                      {row?.optical_qa?.cloud_fraction_of_scl_cells != null
                        ? `${(row.optical_qa.cloud_fraction_of_scl_cells * 100).toFixed(2)}% (${row.optical_qa.cloud_cells ?? 0} cells)`
                        : 'Not reported'}
                    </strong>
                  </div>
                </div>
              </div>

              <details>
                <summary>Source observations and physical assumptions</summary>
                <p>
                  Optical scene: <span className="num">{row?.acquired_at ?? 'Not available'}</span> · <span className="mono">{row?.acquisition_id}</span>
                </p>
                <p>
                  Raw NDWI position (Observed): <strong className="num">{metres(row?.ndwi.x_frf_m)}</strong> · MNDWI comparison (20 m SWIR):{' '}
                  <strong className="num">{metres(row?.mndwi.x_frf_m)}</strong>.
                </p>
                <p>
                  Matched gauge water level: <strong className="num">{metres(row?.environment?.water_level_m_mllw)}</strong> MLLW at{' '}
                  <span className="num">{row?.environment?.water_level_timestamp_utc ?? 'Not available'}</span> (residual vs tide prediction:{' '}
                  <span className="num">{numFixed(row?.environment?.observed_minus_predicted_m, 3, 'm')}</span>).
                </p>
                <p>{row?.tide.reasons.join(' ')}</p>
                {row?.tide.slope_sensitivity_frf_m && (
                  <p>
                    Slope P10–P90 sensitivity span: <span className="num">{row.tide.slope_sensitivity_frf_m.map((v) => v.toFixed(2)).join('–')} m</span>. This is a conditional slope bracket, not a confidence interval.
                  </p>
                )}
                <p>
                  Experimental wave setup: <span className="num">{metres(row?.setup.x_frf_m)}</span> · {row?.setup.status}. {row?.setup.reasons.join(' ')}
                </p>
                {c?.terrain?.acquisitions && (
                  <p>
                    USACE LiDAR quality:{' '}
                    {c.terrain.acquisitions
                      .map(
                        (lq) =>
                          `${lq.epoch} (${lq.acquired_at}, coregQC=${lq.quality?.coregQCFlag ?? '—'}, RMS=${lq.quality?.rmsReflectorError?.toFixed(3) ?? '—'} m)`,
                      )
                      .join(' · ')}
                  </p>
                )}
                <p>{terrain?.reasons.join(' ')}</p>
              </details>
            </>
          )}

          {c ? (
            <>
              <details>
                <summary>Waterline validation against LiDAR</summary>
                <p>{c.validation.scope} Horizontal errors are reported below. These evaluate optical shoreline targets, separate from vertical terrain regression.</p>
                {Object.entries(c.validation.targets).map(([key, value]) => (
                  <div key={key} style={{ marginTop: 12 }}>
                    <h2>{key === 'fixed_mhw_contour' ? 'Fixed mean-high-water contour (0.359 m NAVD88)' : 'Survey-time wet/dry proxy'}</h2>
                    <div className="science-table">
                      <table>
                        <thead>
                          <tr>
                            <th>Method</th>
                            <th>Rows</th>
                            <th>Horizontal RMSE</th>
                            <th>MAE</th>
                            <th>Bias</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(value.raw_vs_tide.methods ?? {}).map(([name, m]) => (
                            <tr key={name}>
                              <td>{name}</td>
                              <td className="num">{m.n}</td>
                              <td className="num">{metres(m.rmse_m)}</td>
                              <td className="num">{metres(m.mae_m)}</td>
                              <td className="num">{m.bias_m.toFixed(2)} m</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <p>{value.raw_vs_tide.reason}</p>
                    <details>
                      <summary>Experimental setup comparison</summary>
                      {Object.entries(value.raw_vs_tide_vs_setup.methods ?? {}).map(([name, m]) => (
                        <p key={name}>
                          {name}: {metres(m.rmse_m)} RMSE on {m.n} rows
                        </p>
                      ))}
                    </details>
                  </div>
                ))}
              </details>

              <details>
                <summary>Radar disagreement and exact acquisition times</summary>
                <p>
                  <strong className="num">
                    {c.radar_disagreement.opposite_strict_cells} of {c.radar_disagreement.strict_overlap_cells}
                  </strong>{' '}
                  strict joint cells show opposite NISAR (L-band HH) vs Sentinel-1 (C-band VV) change signs;{' '}
                  <strong className="num">
                    {c.radar_disagreement.opposite_radar_cells} of {c.radar_disagreement.matched_radar_cells}
                  </strong>{' '}
                  across shared radar coverage. This indicates timing and frequency divergence — never confirmed erosion.
                </p>
                {c.radar_disagreement.s1_minus_nisar_seconds && (
                  <p className="num">
                    Sentinel-1 minus NISAR overpass offset: June {(c.radar_disagreement.s1_minus_nisar_seconds.june / 86400).toFixed(2)} days · October{' '}
                    {(c.radar_disagreement.s1_minus_nisar_seconds.october / 60).toFixed(1)} min.
                  </p>
                )}
                {Object.entries(c.radar_disagreement.acquisitions ?? {}).map(([sensor, epochs]) => (
                  <div key={sensor} style={{ marginBottom: 10 }}>
                    <h2>{sensor}</h2>
                    {Object.entries(epochs).map(([name, e]) => (
                      <p key={name} className="slot-meta">
                        <strong>{name}:</strong> <span className="num">{e.acquired_at}</span>
                        {e.environment?.water_level_m_mllw != null && (
                          <span> · NOAA tide {e.environment.water_level_m_mllw.toFixed(3)} m MLLW</span>
                        )}
                        <br />
                        <span className="mono">{e.id}</span>
                      </p>
                    ))}
                  </div>
                ))}
                <p>{c.radar_disagreement.reasons.join(' ')}</p>
              </details>
            </>
          ) : (
            <p role="status">{coastal?.reason ?? 'Loading validation…'}</p>
          )}

          <details>
            <summary>Historical model results</summary>
            <p>
              The historical 7.188 m Bayesian dune-position error and 3.016 m independently tested optical error remain documented in project records. They used different targets, acquisitions, and methods from current coastal physics products and are retained for auditability only.
            </p>
          </details>
        </>
      ) : (
        <>
          {!n ? (
            <p role="status">{nisar?.reason ?? 'Loading independent NISAR experiments…'}</p>
          ) : (
            <>
              <p className="intro">
                <span className="num">{t?.n ?? 0}</span> valid 10 m cells across one June–October interval. Predictions are scored out-of-sample on held-out alongshore strips with a 30 m spatial guard (vertical error in metres NAVD88).
              </p>

              {t?.metrics ? (
                <div className="science-table">
                  <table>
                    <thead>
                      <tr>
                        <th>Model</th>
                        <th>Cells</th>
                        <th>Vertical RMSE</th>
                        <th>MAE</th>
                        <th>Bias</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(t.metrics).map(([name, m]) => (
                        <tr key={name}>
                          <td>{modelNames[name] ?? name}</td>
                          <td className="num">{m.n}</td>
                          <td className="num">{m.rmse_m.toFixed(4)} m</td>
                          <td className="num">{m.mae_m.toFixed(4)} m</td>
                          <td className="num">{m.bias_m >= 0 ? `+${m.bias_m.toFixed(4)}` : m.bias_m.toFixed(4)} m</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p>{t?.reason ?? 'Terrain experiment withheld.'}</p>
              )}

              {t?.ablation && (
                <div className="quality-note">
                  <strong>{t.ablation.C_minus_B_rmse_m > 0 ? 'Adding NISAR did not improve this test' : 'NISAR result requires independent temporal validation'}</strong>
                  <p>
                    RMSE difference (Model C − Model B):{' '}
                    <span className="num">
                      {t.ablation.C_minus_B_rmse_m > 0 ? '+' : ''}
                      {t.ablation.C_minus_B_rmse_m.toFixed(5)} m ({t.ablation.C_minus_B_rmse_percent?.toFixed(2)}%)
                    </span>
                    . NISAR improved {t.ablation.strips_with_lower_rmse_for_C} of {t.per_strip?.length ?? 0} held-out strips.
                  </p>
                  <p>
                    Deployment status: <strong>{t.terrain_model_deployment?.status}</strong>. {t.terrain_model_deployment?.reason}.
                  </p>
                </div>
              )}

              {unlabeled && (
                <details open>
                  <summary>NISAR L-band backscatter & HH−HV polarization summary</summary>
                  <p className="slot-meta">
                    Collection <span className="mono">{String(nisarAcqJune?.collection ?? 'NISAR_L2_GCOV_PROVISIONAL_V1')}</span> · Track{' '}
                    <span className="num">{String(nisarAcqJune?.track ?? 69)}</span> / Frame <span className="num">{String(nisarAcqJune?.frame ?? 70)}</span> ·{' '}
                    {String(nisarAcqJune?.orbit_direction ?? 'Descending')} {String(nisarAcqJune?.look_direction ?? 'Left')} · 1,310 valid 10 m cells (Joint L+S:{' '}
                    {String(nisarAcqJune?.joint_l_s ?? false)}).
                  </p>
                  <div className="science-table">
                    <table>
                      <thead>
                        <tr>
                          <th>Variable (RTC γ⁰)</th>
                          <th>June range</th>
                          <th>October range</th>
                          <th>Oct − Jun Δ</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td>HH backscatter</td>
                          <td className="num">{fmtRange(unlabeled.june_hh_db)}</td>
                          <td className="num">{fmtRange(unlabeled.october_hh_db)}</td>
                          <td className="num">{fmtRange(unlabeled.delta_hh_db)}</td>
                        </tr>
                        <tr>
                          <td>HV backscatter</td>
                          <td className="num">{fmtRange(unlabeled.june_hv_db)}</td>
                          <td className="num">{fmtRange(unlabeled.october_hv_db)}</td>
                          <td className="num">{fmtRange(unlabeled.delta_hv_db)}</td>
                        </tr>
                        <tr>
                          <td>HH − HV polarization contrast</td>
                          <td className="num">{fmtRange(unlabeled.june_hh_minus_hv_db)}</td>
                          <td className="num">{fmtRange(unlabeled.october_hh_minus_hv_db)}</td>
                          <td className="num">{fmtRange(unlabeled.delta_hh_minus_hv_db)}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </details>
              )}

              <details>
                <summary>Held-out strips and method</summary>
                <p>
                  Ridge regression; 100 m held-out strips, 30 m spatial buffer; standardization and alpha penalty selected strictly inside training folds. Environmental telemetry provides context only.
                </p>
                {t?.per_strip?.map((s) => (
                  <p key={s.frf_y_start_m} className="num">
                    FRF y {s.frf_y_start_m} m: {s.n} cells · Model C − B RMSE {s.C_minus_B_rmse_m >= 0 ? '+' : ''}
                    {s.C_minus_B_rmse_m.toFixed(4)} m
                  </p>
                ))}
                <p>Only one seasonal interval was available; prediction intervals and significant erosion/deposition classes remain withheld.</p>
                {Object.entries(t?.acquisition_pairs ?? {}).map(([sensor, p]) => (
                  <div key={sensor}>
                    <strong>{sensor}</strong>
                    <p className="num">
                      {p.june_utc} → {p.october_utc}
                    </p>
                    <details>
                      <summary>Source identifiers</summary>
                      <p className="mono">
                        {p.june_id}
                        <br />
                        {p.october_id}
                      </p>
                    </details>
                  </div>
                ))}
                <p>The June Sentinel-1 pass follows NISAR by about 11.96 days; timing and radar frequency effects cannot be separated.</p>
              </details>

              <details>
                <summary>Can NISAR identify the waterline?</summary>
                <p>
                  HH brightness extraction is an exploratory transition frozen before optical/tide comparability checks; failed comparability is reported transparently.
                </p>
                {Object.entries(n.shoreline.epochs).map(([name, e]) => (
                  <p key={name}>
                    {name}: {e.candidate_rows ?? 0} candidate rows · waterline comparison {e.comparability?.status ?? 'withheld'}.
                  </p>
                ))}
                {Object.entries(n.shoreline.epochs).map(([name, e]) => {
                  const otsu = (e as { otsu_threshold_db?: number }).otsu_threshold_db;
                  const medOff = (e.comparability as { median_candidate_minus_expected_m?: number } | undefined)?.median_candidate_minus_expected_m;
                  return otsu != null || medOff != null ? (
                    <p key={`${name}-meta`} className="slot-meta num">
                      {name} diagnostics: Otsu threshold {otsu != null ? `${otsu.toFixed(2)} dB` : '—'} · median residual vs expected ocean band{' '}
                      {medOff != null ? `${medOff.toFixed(2)} m` : '—'}
                    </p>
                  ) : null;
                })}
                <p>
                  Input checks: <strong>{n.input_qa.status}</strong>. Passing grid/calibration QA does not establish shoreline accuracy.
                </p>
              </details>
            </>
          )}
        </>
      )}

      <button className="full-button" disabled={!c && !n} onClick={download}>
        Download results and evidence
      </button>
      <p className="quiet-note">
        All models are retrospective research products. Esri background imagery is not matched to survey dates. Observed values, conditional estimates, and exploratory radar outputs remain strictly separated.
      </p>
    </section>
  );
}
