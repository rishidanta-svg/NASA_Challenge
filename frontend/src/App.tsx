import { useCallback, useEffect, useState } from 'react';
import { getAcquisitions, getLayers, getStudyArea, getTerrainChange, getTransects } from './api/client';
import { clearCache } from './api/http';
import { BoundaryWorkspace } from './components/BoundaryWorkspace';
import { CrossSection } from './components/CrossSection';
import { Icon } from './components/Icon';
import { MapTools } from './components/MapTools';
import { MapView } from './map/MapView';
import { flyToStudyArea } from './map/registry';
import { useApp } from './state/store';

type Panel = 'overview' | 'layers' | 'compare' | 'findings' | 'about' | null;
export function App() {
  const [panel, setPanel] = useState<Panel>('overview');
  const set = useApp(s => s.set);
  const { bottomOpen, layers } = useApp();
  function open(next: Panel) {
    setPanel(next);set({compare:next === 'compare'});
    if (next === 'compare') {
      const state=useApp.getState();Object.keys(state.slots).forEach(id=>state.setSlot(id,{visible:id==='lidar-elevation'}));
      set({date:'2026-06-19',compareDate:'2026-10-16',terrainSource:state.terrainSource==='aws'?'aws':'lidar-dem-june'});
    }
  }
  const loadAll = useCallback(
    async (force = false) => {
      if (force) clearCache('api:');
      await Promise.all([
        getStudyArea().then((studyArea) => set({ studyArea })),
        getLayers().then((layers) => set({ layers })),
        getAcquisitions().then((acquisitions) => set({ acquisitions })),
        getTerrainChange().then((terrainChange) => set({ terrainChange })),
        getTransects().then((transects) => {
          const selected = useApp.getState().selectedTransectId;
          const features = transects.data ?? [];
          const selectedTransectId = features.some((feature) => feature.properties.id === selected)
            ? selected
            : features[2]?.properties.id ?? features[0]?.properties.id ?? null;
          set({ transects, selectedTransectId });
        }),
      ]);

    },
    [set],
  );

  useEffect(() => {
    void loadAll(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    function escape(e: KeyboardEvent) {if (e.key === 'Escape') {setPanel(null);set({compare:false,bottomOpen:false});}}
    window.addEventListener('keydown', escape); return () => window.removeEventListener('keydown',escape);
  },[set]);
  return <div className="earth-app">
    <header className="app-header"><a className="wordmark" href="#" onClick={e=>{e.preventDefault();open('overview');}}>poltergeist<span>Coastal observatory</span></a>
      <span className="project-label">Duck, North Carolina</span>
      <button className="header-info" onClick={()=>open('about')}>About this project <Icon name="info" size={16}/></button>
    </header>
    <nav className="tool-rail" aria-label="Main navigation">{([
      ['overview','globe','Explore'],['layers','layers','Layers'],['compare','compare','Compare'],['findings','chart','Findings'],['about','info','About'],
    ] as const).map(([id,icon,label])=><button key={id} className={panel===id?'selected':''} aria-pressed={panel===id} onClick={()=>open(panel===id?null:id)} title={label}><Icon name={icon}/><span>{label}</span></button>)}</nav>
    <main className="map-workspace" aria-label="Coastal map">
      <MapView />
      <button className="location-search" onClick={()=>{flyToStudyArea();open('overview');}} aria-label="Go to Duck study area"><Icon name="search" size={18}/><span>Duck, North Carolina</span><span className="search-meta">Study area</span></button>
      {panel && <aside className={`tool-panel ${panel === 'findings' ? 'wide-panel' : ''}`} aria-label={`${panel} panel`}>
        <div className="panel-toolbar"><span>{({overview:'Study area',layers:'Map layers',compare:'Compare observations',findings:'Coastal findings',about:'About Poltergeist'})[panel]}</span><button className="icon-button" aria-label="Close panel" onClick={()=>open(null)}><Icon name="close" size={18}/></button></div>
        {panel === 'overview' ? <div className="panel-content">
          <div className="location-label"><Icon name="pin" size={15}/> North Carolina · United States</div><h1>Duck coastline</h1><p className="intro">See how this stretch of beach changed between June and October 2026.</p>
          <div className="study-facts"><span><strong>500 m</strong>Study reach</span><span><strong>2 surveys</strong>June & October</span></div>
          <p className="section-label">Start exploring</p>
          <button className="action-row" onClick={()=>open('layers')}><Icon name="layers"/><span><strong>See coastal change</strong><small>View measured changes in ground level</small></span><Icon name="arrow" size={16}/></button>
          <button className="action-row" onClick={()=>open('compare')}><Icon name="compare"/><span><strong>Compare two observations</strong><small>Move between the June and October surveys</small></span><Icon name="arrow" size={16}/></button>
          <button className="action-row" onClick={()=>{open('findings');set({bottomOpen:false});}}><Icon name="chart"/><span><strong>Understand the findings</strong><small>Explore estimates and their limits</small></span><Icon name="arrow" size={16}/></button>
          <div className="quiet-note">This is a research study of one coastline. It is not a live erosion warning service.</div>
        </div> : panel === 'findings' ? <BoundaryWorkspace/> : <MapTools panel={panel} onRefresh={()=>void loadAll(true)}/>}
      </aside>}
      <div className="map-bottom-bar"><span>{layers?.state === 'real' ? 'Study data connected' : 'Study data unavailable'}</span><span>June – October 2026</span><button onClick={()=>open('about')}>Data sources</button></div>
      {bottomOpen && <div className="profile-overlay"><CrossSection/></div>}
    </main>
  </div>;
}
