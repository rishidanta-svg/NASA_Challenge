import {useEffect,useState} from 'react';
import {getTransect,type Sourced} from '../api/client';
import type {TransectDetail} from '../api/schemas';
import {useApp} from '../state/store';
export function CrossSection(){
  const {selectedTransectId,bottomOpen,set}=useApp();
  const [detail,setDetail]=useState<Sourced<TransectDetail>|null>(null);
  const [guides,setGuides]=useState(false);
  const [hover,setHover]=useState<number|null>(null);
  useEffect(()=>{let active=true;setDetail(null);if(selectedTransectId)void getTransect(selectedTransectId).then(r=>{if(active)setDetail(r)});return()=>{active=false}},[selectedTransectId]);
  const t=detail?.data,j=t?.profiles[0],o=t?.profiles[1];
  const points=[...(j?.points??[]),...(o?.points??[])];
  const xmin=points.length?Math.min(...points.map(p=>p.x_m)):0,xmax=points.length?Math.max(...points.map(p=>p.x_m)):200;
  const zmin=points.length?Math.floor(Math.min(...points.map(p=>p.z_m)))-1:0,zmax=points.length?Math.ceil(Math.max(...points.map(p=>p.z_m)))+1:8;
  const W=760,H=165,left=42,right=12,top=12,bottom=25;
  const sx=(x:number)=>left+(x-xmin)/(xmax-xmin||1)*(W-left-right),sy=(z:number)=>top+(zmax-z)/(zmax-zmin||1)*(H-top-bottom);
  const path=(ps:{x_m:number;z_m:number}[])=>ps.map((p,i)=>`${i===0||p.x_m-ps[i-1]!.x_m>1.01?'M':'L'}${sx(p.x_m)},${sy(p.z_m)}`).join(' ');
  function near<T extends {x_m:number}>(ps:T[]|undefined){if(hover===null||!ps?.length)return null;const p=ps.reduce((a,b)=>Math.abs(a.x_m-hover)<Math.abs(b.x_m-hover)?a:b);return Math.abs(p.x_m-hover)<=.51?p:null;}
  const hj=near(j?.points),ho=near(o?.points),change=near(t?.measured_change?.change_profile);
  return <section className="cross-section-dock" aria-label="Measured beach profile" data-testid="cross-section"><div className="cross-section-header"><strong>Measured beach profile · {t?.properties.label??'Loading…'}</strong><div style={{display:'flex',alignItems:'center',gap:12}}>{!!t?.boundaries.length&&<label style={{fontSize:10}}><input type="checkbox" checked={guides} onChange={e=>setGuides(e.target.checked)}/> Sensor markers</label>}<button aria-label="Close beach profile" onClick={()=>set({bottomOpen:!bottomOpen,showTransects:false})}>Close</button></div></div>
    {j&&o?<div className="cross-section-body"><div className="chart-svg-wrap"><svg viewBox={`0 0 ${W} ${H}`} width="100%" height="100%" role="img" aria-label="Measured June and October beach heights" onPointerMove={e=>{const b=e.currentTarget.getBoundingClientRect();setHover(Math.max(xmin,Math.min(xmax,xmin+(((e.clientX-b.left)/b.width*W-left)/(W-left-right))*(xmax-xmin))))}} onPointerLeave={()=>setHover(null)}>
      {[0,.25,.5,.75,1].map(f=>{const z=zmin+(zmax-zmin)*f,x=xmin+(xmax-xmin)*f;return <g key={f}><line x1={left} x2={W-right} y1={sy(z)} y2={sy(z)} stroke="#e3e5dc"/><text x={left-5} y={sy(z)+3} textAnchor="end" fontSize="9" fill="#777">{z.toFixed(1)} m</text><text x={sx(x)} y={H-5} textAnchor="middle" fontSize="9" fill="#777">{x.toFixed(0)} m</text></g>})}
      {guides&&t?.boundaries.filter(b=>b.x_m>=xmin&&b.x_m<=xmax).map((b,i)=><line key={i} x1={sx(b.x_m)} x2={sx(b.x_m)} y1={top} y2={H-bottom} stroke="#a3a79a" strokeDasharray="2 4"><title>{b.definition} · {b.acquired_at} · {b.x_frf_m?.toFixed(1)} m FRF</title></line>)}
      <path d={path(j.points)} fill="none" stroke="#353832" strokeWidth="2"/><path d={path(o.points)} fill="none" stroke="#90948a" strokeWidth="2" strokeDasharray="5 3"/>
      {hover!==null&&<line x1={sx(hover)} x2={sx(hover)} y1={top} y2={H-bottom} stroke="#65695c"/>}
    </svg></div><div className="slot-card"><div>━ June · ┄ October</div><p className="slot-meta">{j.acquired_at?.slice(0,10)} / {o.acquired_at?.slice(0,10)}<br/>{j.vertical_datum}</p>{hover===null?<p className="slot-meta">Move over the profile to inspect measured heights.</p>:<p className="slot-meta">Along profile: {hover.toFixed(1)} m<br/>June: {hj?hj.z_m.toFixed(2)+' m':'No return'}<br/>October: {ho?ho.z_m.toFixed(2)+' m':'No return'}<br/>Paired change: {change?change.dz_m.toFixed(2)+' m':'No paired return'}</p>}</div></div>:<p className="slot-meta" role="status">{detail?.reason??'Loading measured profile…'}</p>}
  </section>;
}
