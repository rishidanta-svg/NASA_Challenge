import { useCallback, useEffect } from 'react';
import { getAcquisitions, getLayers, getStudyArea, getTerrainChange, getTransects } from './api/client';
import { clearCache } from './api/http';
import { CrossSection } from './components/CrossSection';
import { Header } from './components/Header';
import { Inspector } from './components/Inspector';
import { LayerPanel } from './components/LayerPanel';
import { API_BASE_URL } from './config/env';
import { MapView } from './map/MapView';
import { useApp } from './state/store';

export function App() {
  const { selectedTransectId, set } = useApp();

  const loadAll = useCallback(
    async (force = false) => {
      if (force) clearCache('api:');
      const [studyArea, layers, acquisitions, transects, terrainChange] = await Promise.all([
        getStudyArea(),
        getLayers(),
        getAcquisitions(),
        getTransects(),
        getTerrainChange(),
      ]);
      const defaultTransectId = selectedTransectId ?? transects.data?.[1]?.properties.id ?? transects.data?.[0]?.properties.id ?? null;
      set({
        studyArea,
        layers,
        acquisitions,
        transects,
        terrainChange,
        selectedTransectId: defaultTransectId,
      });
    },
    [selectedTransectId, set],
  );

  useEffect(() => {
    void loadAll(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="app-shell">
      <Header onRefreshAll={() => void loadAll(true)} />

      <div className="workstation-grid">
        <LayerPanel />
        <main className="center-column">
          <MapView />
          <CrossSection />
        </main>
        <Inspector />
      </div>

      <footer className="app-footer">
        <span>POLTERGEIST · DUCK FRF COASTAL MONITORING WORKSTATION</span>
        <span>
          MapLibre GL JS · OpenFreeMap · AWS Terrarium DEM · NOAA CO-OPS #8651370 · API: {API_BASE_URL}
        </span>
      </footer>
    </div>
  );
}
