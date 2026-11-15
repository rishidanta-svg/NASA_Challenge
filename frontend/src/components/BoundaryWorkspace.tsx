import { useEffect, useState } from 'react';
import { getBoundaryAnalysis, type Sourced } from '../api/client';
import type { BoundaryAnalysis } from '../api/schemas';
import { useApp } from '../state/store';
import { DataStateBadge } from './DataStateBadge';

const metres = (n: number | null) => n === null ? 'Withheld / unavailable' : `${n.toFixed(2)} m`;
export function BoundaryWorkspace({ evidence = false }: { evidence?: boolean }) {
  const { selectedTransectId, transects, set } = useApp();
  const [result, setResult] = useState<Sourced<BoundaryAnalysis> | null>(null);
  const [epoch, setEpoch] = useState('2026-06');
  useEffect(() => {
    let cancelled = false;
    setResult(null);
    if (selectedTransectId) void getBoundaryAnalysis(selectedTransectId).then(r => { if (!cancelled) setResult(r); });
    return () => { cancelled = true; };
  }, [selectedTransectId]);
  const data = result?.data;
  const records = data?.records.filter(r => r.epoch === epoch) ?? [];
  const observations = records.flatMap(r => r.observations ?? []);
  function download() {
    if (!data) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'}));
    const link = document.createElement('a'); link.href = url; link.download = `${data.transect_id}-boundary-analysis.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <section className="boundary-workspace" aria-label={evidence ? 'Validation and evidence' : 'Boundary analysis'}>
    <div className="boundary-heading"><div><span className="eyebrow">{evidence ? 'EVIDENCE & LIMITATIONS' : 'BOUNDARY ANALYSIS'}</span>
      <h1>{evidence ? 'Inspect the evidence' : 'Track coastal boundaries'}</h1></div>
      {result && <DataStateBadge state={result.state} inferred={!!data} />}</div>
    <div className="boundary-controls">
      <label>Transect <select aria-label="Analysis transect" value={selectedTransectId ?? ''} onChange={e => set({selectedTransectId:e.target.value})}>
        {(transects?.data ?? []).map(t => <option key={t.properties.id} value={t.properties.id}>{t.properties.label}</option>)}
      </select></label>
      <label>Analysis epoch <select aria-label="Boundary epoch" value={epoch} onChange={e => setEpoch(e.target.value)}>
        {[...new Set(data?.records.map(r => r.epoch) ?? ['2026-06','2026-09','2026-10'])].map(e => <option key={e}>{e}</option>)}
      </select></label>
      <button disabled={!data} onClick={download}>Export evidence JSON ↓</button>
    </div>
    {!data ? <p role="status">{result?.reason ?? (selectedTransectId ? 'Loading committed analysis…' : 'Select a transect to inspect its analysis.')}</p> : <>
      <p className="muted">{data.coordinate_reference}. Analysis epochs group observations; exact acquisition times are listed below.</p>
      {!evidence && <><div className="boundary-cards">{records.map(r => <article className="slot-card" key={r.feature}>
        <span className="eyebrow">{r.feature === 'waterline' ? 'OPTICAL WATERLINE' : 'INFERRED DUNE TOE'}</span>
        <h2>{metres(r.x_frf_m)}</h2><p>{r.source}</p><p>{r.status}</p>
        <p>Spatial-CV error scale: {r.cv_rmse_m === null ? 'Unavailable' : metres(r.cv_rmse_m)}</p>
        {r.interval90_frf_m && <p>Approximate 90% interval: {r.interval90_frf_m.map(n => n.toFixed(2)).join('–')} m FRF x</p>}
      </article>)}</div>
      <h2>Sensor boundary observations</h2><p className="muted">Positive time offset means the satellite observed after the matched LiDAR scan.</p>
      <div className="science-table"><table><thead><tr><th>Product</th><th>Acquired (UTC)</th><th>FRF x</th><th>Δt vs LiDAR</th></tr></thead><tbody>
        {observations.map((o,i) => <tr key={`${o.product}-${i}`}><td title={o.acquisition_id}>{o.product}<details><summary>Source ID</summary>{o.acquisition_id}</details></td>
          <td>{o.acquired_at ? new Date(o.acquired_at).toISOString().replace('T',' ').replace('Z',' UTC') : 'Unavailable'}</td>
          <td>{o.x_frf_m === null ? 'Unavailable' : metres(o.x_frf_m)}</td><td>{o.lidar_offset_hours === null ? 'Unavailable' : `${o.lidar_offset_hours > 0 ? '+' : ''}${o.lidar_offset_hours.toFixed(1)} h`}</td></tr>)}
      </tbody></table></div></>}
      <h2>Committed validation results</h2><p>Compare methods on the same reference rows. RMSE describes horizontal boundary error; full validation and limitations are listed below.</p>
      <div className="science-table"><table><thead><tr><th>Method</th><th>Reference rows</th><th>Horizontal RMSE</th></tr></thead><tbody>
        {data.validation.map(v => <tr key={v.method}><td>{v.method.replaceAll('_',' ')}</td><td>{v.N}</td><td>{v.RMSE_m === null ? 'Unavailable' : `${v.RMSE_m.toFixed(3)} m`}</td></tr>)}
      </tbody></table></div>
      <h2>Pipeline quality checks</h2>
      <div className="science-table"><table><thead><tr><th>Check</th><th>Status</th><th>Detail</th></tr></thead><tbody>
        {data.quality_checks.map(c => <tr key={c.check}><td>{c.check}</td><td style={{color:c.status === 'FAIL' ? '#ffb492' : undefined}}>{c.status}</td><td>{c.detail}</td></tr>)}
      </tbody></table></div>
      <h2>Interpretation limits</h2><ul>{data.limitations.map(l => <li key={l}>{l}</li>)}</ul>
      <p className="muted">The additional physics collection is pending delivery. Live NOAA values describe current conditions, not acquisition-time conditions.</p>
    </>}
  </section>;
}
