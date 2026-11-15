/**
 * OpenFreeMap basemap styles (free, no API key, OpenStreetMap / OpenMapTiles).
 * All URLs verified to return HTTP 200 with `Access-Control-Allow-Origin: *`.
 */
export const BASEMAPS = [
  { id: 'liberty', label: 'Liberty', url: 'https://tiles.openfreemap.org/styles/liberty', tone: 'standard' },
  { id: 'positron', label: 'Positron (light)', url: 'https://tiles.openfreemap.org/styles/positron', tone: 'light' },
  { id: 'dark', label: 'Dark', url: 'https://tiles.openfreemap.org/styles/dark', tone: 'dark' },
  { id: 'fiord', label: 'Fiord (muted dark)', url: 'https://tiles.openfreemap.org/styles/fiord', tone: 'dark' },
] as const;

export type BasemapId = (typeof BASEMAPS)[number]['id'];
export const DEFAULT_BASEMAP: BasemapId = 'liberty';

export function basemapUrl(id: BasemapId): string {
  return BASEMAPS.find((b) => b.id === id)?.url ?? BASEMAPS[0].url;
}
