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
  const set = useApp((state) => state.set);

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
            : features[1]?.properties.id ?? features[0]?.properties.id ?? null;
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
