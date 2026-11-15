import { useEffect, useState } from 'react';
import { getBoundaryAnalysis, type Sourced } from '../api/client';
import type { BoundaryAnalysis } from '../api/schemas';
import { useApp } from '../state/store';

export function BoundaryWorkspace() {
  const {selectedTransectId,transects,date,set}=useApp();
  const [result,setResult]=useState<Sourced<BoundaryAnalysis>|null>(null);
  const [epoch,setEpoch]=useState(date.slice(0,7));
  useEffect(()=>{let cancelled=false;setResult(null);if(selectedTransectId)void getBoundaryAnalysis(selectedTransectId).then(r=>{if(!cancelled)setResult(r)});return()=>{cancelled=true}},[selectedTransectId]);
  const data=result?.data;
  const records=data?.records.filter(r=>r.epoch===epoch)??[];
  const observations=records.flatMap(r=>r.observations??[]);
  const failed=data?.quality_checks.filter(c=>c.status==='FAIL')??[];
  function download(){if(!data)return;const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`${data.transect_id}-evidence.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
  return <section className="boundary-workspace" aria-label="Coastal findings"><h1>What the observations show</h1><p className="intro">Explore estimated beach boundaries at a survey location. These are research estimates, not erosion forecasts.</p>
    <div className="boundary-controls"><label>Location<select aria-label="Findings location" value={selectedTransectId??''} onChange={e=>set({selectedTransectId:e.target.value})}>{(transects?.data??[]).map((t,i)=><option key={t.properties.id} value={t.properties.id}>Section {i+1} · {t.properties.frf_y_m} m along coast</option>)}</select></label>
      <label>Observation group<select aria-label="Boundary epoch" value={epoch} onChange={e=>setEpoch(e.target.value)}>{['2026-06','2026-09','2026-10'].map(d=><option key={d} value={d}>{new Date(`${d}-01T00:00:00Z`).toLocaleDateString('en-GB',{month:'long',year:'numeric',timeZone:'UTC'})}</option>)}</select></label></div>
    {!data?<p role="status">{result?'Analysis is unavailable. Try refreshing study data from About.':'Loading study results…'}</p>:<>
      <div className="boundary-cards">{records.map(r=><article className="slot-card" key={r.feature}><span className="eyebrow">{r.feature==='waterline'?'Water’s edge':'Foot of the dune'}</span><h2>{r.x_frf_m===null?'No reliable estimate':`${r.x_frf_m.toFixed(1)} m`}</h2><p>{r.x_frf_m===null?'The observations disagree too much to report a position.':'Estimated position across the beach, measured from the local survey origin.'}</p><details><summary>Estimate details</summary><p>{r.source}</p><p>{r.status}</p><p>Validation error scale: {r.cv_rmse_m?.toFixed(2)??'unavailable'} m horizontally.</p>{r.interval90_frf_m&&<p>Approximate 90% range: {r.interval90_frf_m.map(v=>v.toFixed(1)).join('–')} m.</p>}</details></article>)}</div>
      {failed.length>0&&<div className="quality-note"><strong>A data pairing needs review</strong><p>A NISAR observation differs from the originally planned satellite–survey pairing. Results remain visible with the exact dates below.</p></div>}
      <details><summary>When were these observations taken?</summary><p>Satellite and ground surveys are not always simultaneous. Positive gaps mean the satellite observed after the LiDAR survey. The group selector does not represent an exact acquisition date.</p><div className="science-table"><table><thead><tr><th>Observation</th><th>Acquired (UTC)</th><th>Time from survey</th></tr></thead><tbody>{observations.map((o,i)=><tr key={i}><td>{o.product}<details><summary>Source record</summary>{o.acquisition_id}</details></td><td>{o.acquired_at?new Date(o.acquired_at).toISOString().replace('T',' ').slice(0,19):'Unavailable'}</td><td>{o.lidar_offset_hours===null?'Unavailable':`${o.lidar_offset_hours>0?'+':''}${o.lidar_offset_hours.toFixed(1)} h`}</td></tr>)}</tbody></table></div></details>
      <details><summary>How accurate are the estimates?</summary><p>Validation compares estimated horizontal positions against LiDAR references. The current Bayesian method has not demonstrated better accuracy than the baseline on matched rows.</p><div className="science-table"><table><thead><tr><th>Method</th><th>Reference rows</th><th>Error (RMSE)</th></tr></thead><tbody>{data.validation.map(v=><tr key={v.method}><td>{v.method.replaceAll('_',' ')}</td><td>{v.N}</td><td>{v.RMSE_m?.toFixed(3)??'Unavailable'} m</td></tr>)}</tbody></table></div></details>
      <details><summary>Quality checks and limitations</summary><ul>{data.limitations.map(l=><li key={l}>{l}</li>)}</ul><div className="science-table"><table><thead><tr><th>Check</th><th>Result</th></tr></thead><tbody>{data.quality_checks.map(c=><tr key={c.check}><td>{c.check}<details><summary>Details</summary>{c.detail}</details></td><td>{c.status}</td></tr>)}</tbody></table></div></details>
      <button className="full-button" onClick={download}>Download results and evidence</button><p className="quiet-note">Positions use the local FRF survey origin. The additional physics dataset is still pending delivery.</p>
    </>}
  </section>;
}
