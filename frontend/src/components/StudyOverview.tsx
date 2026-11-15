import { useState } from 'react';
import { getNisarEvidence } from '../api/client';
import type { CoastalEvidence } from '../api/schemas';
import { saveDownload, studyBrief } from '../lib/exports';
import { resolveSlot } from '../lib/layers';
import { useApp } from '../state/store';
import { Icon } from './Icon';

type Destination = 'layers' | 'compare' | 'findings' | null;
export function StudyOverview({ coastal, open }: { coastal: CoastalEvidence | null; open: (next: Destination) => void }) {
  const {layers, acquisitions, selectedTransectId, set} = useApp();
  const [exporting,setExporting] = useState(false);
  const mean = coastal?.terrain?.mean_m;
  const qualified = coastal?.terrain?.status === 'supported' && mean != null;
  function changeMap() {
    const state=useApp.getState();
    const slots=Object.fromEntries(Object.entries(state.slots).map(([id,s])=>[id,{...s,visible:id==='lidar-dz'}]));
    set({slots,date:'2026-10-16',inspected:null});
    open('layers');
  }
  async function download() {
    if(!coastal)return;
    setExporting(true);
    try {
      const n=await getNisarEvidence();
      saveDownload('poltergeist-duck-study-brief.html',studyBrief(coastal,n.data),'text/html;charset=utf-8');
    } finally {setExporting(false)}
  }
  return <div className="panel-content study-overview">
    <div className="location-label"><Icon name="pin" size={14}/> Duck, North Carolina</div>
    <h1>A changing coastline.</h1>
    <p className="intro">Explore how the beach changed between two surveys, and what satellites can tell us about it.</p>
    <div className="study-facts"><span><strong>500 m</strong>Study reach</span><span><strong>Jun → Oct</strong>2026 surveys</span></div>
    <article className="overview-result" aria-label="Measured study result">
      <span className="eyebrow">Measured ground-level change</span>
      <div className="overview-number num">{qualified?`${mean.toFixed(2)} m`:'—'}</div>
      <p>{qualified?(mean<0?'The surveyed ground was lower on average in October.':'The surveyed ground was higher on average in October.'):coastal?'The measured survey comparison is unavailable.':'Loading the measured survey comparison.'}</p>
      <small>{qualified?`${coastal?.terrain?.native_paired_cells?.toLocaleString() ?? 'Available'} paired LiDAR cells · October minus June`:'USACE LiDAR · paired valid measurements'}</small>
    </article>
    <button className="primary-action" onClick={changeMap} disabled={!resolveSlot(layers?.data,'lidar-dz','2026-10-16')}>Explore measured change <Icon name="arrow" size={17}/></button>
    <button className="action-row" onClick={()=>open('compare')} disabled={!resolveSlot(layers?.data,'lidar-elevation','2026-06-18')}><Icon name="compare"/><span><strong>Compare the beach surfaces</strong><small>Drag between June and October</small></span><Icon name="arrow" size={16}/></button>
    <button className="action-row" disabled={!selectedTransectId} onClick={()=>{open(null);set({bottomOpen:true,showTransects:true,inspected:null});}}><Icon name="chart"/><span><strong>Look across the beach</strong><small>See the measured height profiles</small></span><Icon name="arrow" size={16}/></button>
    <button className="action-row" onClick={()=>open('findings')}><Icon name="info"/><span><strong>Understand the evidence</strong><small>Findings, methods and model limitations</small></span><Icon name="arrow" size={16}/></button>
    <details className="overview-explainer"><summary>What am I looking at?</summary><p>The background image helps you find your way. The scientific overlays show the actual study measurements.</p><p><strong>Ground-level change</strong> compares measured beach heights. <strong>Waterlines</strong> estimate where land meets water. <strong>Radar</strong> measures reflected microwave energy; it does not directly measure erosion.</p><p>{acquisitions?.data?.length ?? 'Available'} acquisition records from four Earth observation instruments, with tide and wave measurements for context.</p></details>
    <button className="full-button brief-button" disabled={!coastal||exporting} onClick={()=>void download()}>{exporting?'Preparing brief…':'Download study brief'}</button>
    <p className="quiet-note">One coast, one study period. For research and field planning; not a live hazard warning.</p>
  </div>;
}
