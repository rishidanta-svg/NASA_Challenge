import { BASEMAPS, type BasemapId } from '../config/basemaps';
import { resolveSlot } from '../lib/layers';
import { useApp } from '../state/store';
import { Legend } from './Legend';
import { EnvironmentPanel } from './EnvironmentPanel';

const overlays = [
  {id:'none',name:'No overlay',description:'A clear view of the coastline.'},
  {id:'lidar-dz',name:'Ground level change',description:'Measured change between the June and October beach surveys.'},
  {id:'lidar-elevation',name:'Beach elevation',description:'Height of the beach above the survey reference level.'},
  {id:'physics-s2-tide',name:'Tide-adjusted waterline',description:'Optical estimate adjusted to mean high water; conditional on beach slope.'},
  {id:'nisar-hh',name:'Radar observation',description:'Satellite radar response. This is not a map of erosion.'},
];
const dates=[['2026-06-18','June observations'],['2026-10-16','October observations']];
export function MapTools({panel,onRefresh}:{panel:'layers'|'compare'|'about';onRefresh:()=>void}) {
  const {basemap,date,compareDate,slots,layers,transects,selectedTransectId,terrainSource,mode,bottomOpen,exaggeration,set,setSlot}=useApp();
  const selected=Object.keys(slots).find(id=>slots[id]?.visible) ?? 'none';
  const active=resolveSlot(layers?.data,selected,date);
  function choose(id:string){Object.keys(slots).forEach(key=>setSlot(key,{visible:key===id}));}
  function changeDate(value:string){set({date:value,terrainSource:terrainSource==='aws'?'aws':`lidar-dem-${value.startsWith('2026-06')?'june':'october'}`});}
  if(panel==='about')return <div className="panel-content about-content"><h1>About this study</h1><p>Poltergeist brings beach surveys and satellite observations together to help you understand coastal change.</p>
    <h2>One coastline, several perspectives</h2><p>LiDAR surveys measure the ground. Optical images estimate the water’s edge. Radar responds to surface conditions. Each tells a different part of the story.</p>
    <details><summary>Data sources & limitations</summary><p>Survey data: USACE Field Research Facility, Duck, NC. Radar: NASA–ISRO NISAR and Copernicus Sentinel-1. Optical profiles: Sentinel-2. Current conditions: NOAA.</p><p>Background imagery: Esri World Imagery. Terrain: regional elevation tiles, with USACE beach surveys available in the study area. Background imagery is not acquisition-matched and does not change with the survey selector.</p><p>Satellite and survey observations can be days apart. Findings shows exact times, uncertainty and unresolved quality checks. This research tool does not predict imminent erosion.</p></details>
    <details><summary>Map help</summary><p>Drag to move. Scroll or use + and − to zoom. Select 3D for terrain, then hold Ctrl while dragging to rotate and tilt. Use N to reset north.</p><p>The coast is naturally flat. True-scale dunes can appear subtle; optional height enhancement is labelled in map settings.</p></details>
    <details><summary>Current weather and tides</summary><p>Current observations, separate from the 2026 survey dates.</p><EnvironmentPanel/></details>
    <button className="full-button" onClick={onRefresh}>Refresh study data</button>
    <a className="text-link" href="https://earth.google.com/web/@36.186,-75.752,0a,1500d,35y,0h,60t,0r" target="_blank" rel="noopener noreferrer">Open this location in Google Earth ↗</a>
    <div className="quiet-note">NASA Space Apps research project. Not an official NASA service.</div>
  </div>;
  return <div className="panel-content"><h1>{panel==='compare'?'What changed?':'Choose what to see'}</h1>
    <p className="intro">{panel==='compare'?'Drag the divider across the map to compare the two observations.':'Start with the imagery, then add a layer to explore the beach.'}</p>
    {panel==='compare' && <div className="comparison-dates"><label>Left side<select aria-label="Left comparison survey" value={date} onChange={e=>changeDate(e.target.value)}>{dates.map(([v,n])=><option value={v} key={v}>{n}</option>)}</select></label><label>Right side<select aria-label="Right comparison survey" value={compareDate} onChange={e=>set({compareDate:e.target.value})}>{dates.map(([v,n])=><option value={v} key={v}>{n}</option>)}</select></label></div>}
    {panel==='compare' && date===compareDate && <p role="status">Both sides show the same survey. Choose different surveys to compare changes.</p>}
    {panel==='compare' && <button className="full-button" onClick={()=>choose('lidar-elevation')}>Compare surveyed beach elevations</button>}
    <fieldset className="layer-choices"><legend>Map overlay</legend>{overlays.map(o=>{const available=o.id==='none'||!!resolveSlot(layers?.data,o.id,date);return <label key={o.id} className={`layer-choice ${selected===o.id?'active':''}`}><input type="radio" name="overlay" value={o.id} disabled={!available} checked={selected===o.id} onChange={()=>choose(o.id)}/><span><strong>{o.name}</strong><small>{available?o.description:'This layer is unavailable.'}</small></span></label>})}</fieldset>
    {selected==='nisar-hh-land-water-candidate' && <p className="quiet-note">Exploratory radar brightness transition. The waterline comparison failed; this is not a validated shoreline.</p>}
    {active && <div className="active-legend"><span>{active.epoch_label}</span>{active.acquired_at && <time>{new Date(active.acquired_at).toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'})}</time>}<Legend colormap={active.colormap} units={active.units} inferred={active.inferred} meaning={active.quantity ?? ''}/></div>}
    {panel==='layers' && <label className="field-label">Survey<select aria-label="Survey observation" value={date} onChange={e=>changeDate(e.target.value)}>{dates.map(([v,n])=><option value={v} key={v}>{n}</option>)}</select></label>}
    <details><summary>More satellite comparisons</summary><p>These layers represent different measurements. Radar disagreement is not an erosion label; NISAR candidate lines failed the waterline comparison.</p><label className="field-label">Additional overlay<select aria-label="Additional satellite overlay" value={selected} onChange={e=>choose(e.target.value)}>
      <option value={selected}>{active?.title ?? 'Choose a layer'}</option>
      {(layers?.data??[]).filter(l=>l.status==='available' && l.kind!=='raster_dem' && l.id===resolveSlot(layers?.data,l.slot,date)?.id && l.slot!==selected).map(l=><option value={l.slot} key={l.id}>{l.title}</option>)}
    </select></label><p>Each layer keeps its original acquisition date. Background imagery is not historical survey imagery.</p></details>
    <details><summary>Beach profiles</summary><p>Inspect the measured height along a line across the beach.</p><label className="field-label">Profile location<select aria-label="Profile location" value={selectedTransectId??''} onChange={e=>set({selectedTransectId:e.target.value,showTransects:true,bottomOpen:true})}>{(transects?.data??[]).map((t,i)=><option key={t.properties.id} value={t.properties.id}>Section {i+1} · {t.properties.frf_y_m} m along the coast</option>)}</select></label><button className="full-button" disabled={!selectedTransectId} onClick={()=>set({bottomOpen:!bottomOpen,showTransects:!bottomOpen})}>{bottomOpen?'Hide profile':'Show profile on map'}</button></details>
    <details><summary>Map appearance</summary><label className="field-label">Background<select aria-label="Map background" value={basemap} onChange={e=>set({basemap:e.target.value as BasemapId})}>{BASEMAPS.filter(b=>['satellite','positron'].includes(b.id)).map(b=><option key={b.id} value={b.id}>{b.id==='positron'?'Street map':b.label}</option>)}</select></label>
      <label className="field-label">Terrain source<select aria-label="Terrain source" value={terrainSource} onChange={e=>set({terrainSource:e.target.value})}><option value="aws">Regional terrain</option>{(layers?.data??[]).filter(l=>l.kind==='raster_dem').map(l=><option key={l.id} value={l.id}>{l.epoch_label} beach survey</option>)}</select></label>
      {mode==='3d' && <label className="field-label">Terrain height<select aria-label="Terrain height" value={exaggeration} onChange={e=>set({exaggeration:Number(e.target.value)})}><option value={1}>True scale</option><option value={2}>Enhanced ×2</option></select></label>}
      {selected!=='none' && <label className="field-label">Overlay strength<select aria-label="Overlay strength" value={slots[selected]?.opacity??.75} onChange={e=>setSlot(selected,{opacity:Number(e.target.value)})}><option value={.4}>Subtle</option><option value={.75}>Balanced</option><option value={1}>Solid</option></select></label>}
    </details>
    <div className="quiet-note">The satellite background is for orientation. Only study overlays change between survey dates.</div>
  </div>;
}
