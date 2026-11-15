/**
 * Registry of live map instances so UI components can issue camera commands
 * without prop-drilling, and so the compare (secondary) map follows the
 * primary camera.
 */
import type { Map as MLMap, LngLatBoundsLike } from 'maplibre-gl';
import { REGIONAL_VIEW, STUDY_BBOX } from '../config/geo';

let primary: MLMap | null = null;
let secondary: MLMap | null = null;

export function registerMap(role: 'primary' | 'secondary', map: MLMap | null): void {
  if (role === 'primary') primary = map;
  else secondary = map;
  if (role === 'secondary' && map && primary) syncSecondary();
}

export function getPrimaryMap(): MLMap | null {
  return primary;
}

export function syncSecondary(): void {
  if (!primary || !secondary) return;
  secondary.jumpTo({
    center: primary.getCenter(),
    zoom: primary.getZoom(),
    bearing: primary.getBearing(),
    pitch: primary.getPitch(),
  });
}

const studyPadding = () => ({top:80,bottom:80,left:(primary?.getContainer().clientWidth ?? 0) > 850 ? 390 : 36,right:36});

export function flyToStudyArea(): void {
  primary?.fitBounds(STUDY_BBOX as LngLatBoundsLike, { padding: studyPadding(), duration: 1600, bearing: primary.getBearing(), pitch: primary.getPitch() });
}

export function flyToDuck(): void {
  primary?.flyTo({ center: [-75.752, 36.186], zoom: 14.2, duration: 1400 });
}

export function flyToRegional(): void {
  primary?.flyTo({ center: REGIONAL_VIEW.center, zoom: REGIONAL_VIEW.zoom, duration: 1400 });
}

export function resetCamera(): void {
  primary?.fitBounds(STUDY_BBOX as LngLatBoundsLike, { padding: studyPadding(), bearing: 0, pitch: 0, duration: 900 });
}

export function setPitch(pitch: number): void {
  primary?.easeTo({ pitch, duration: 300 });
}

export function setBearing(bearing: number): void {
  primary?.easeTo({ bearing, duration: 300 });
}

export function zoomBy(delta: number): void {
  if (primary) primary.easeTo({ zoom: primary.getZoom() + delta, duration: 250 });
}

export function flyToLngLat(lng: number, lat: number, zoom = 17): void {
  primary?.flyTo({ center: [lng, lat], zoom: Math.max(primary.getZoom(), zoom), duration: 900 });
}
