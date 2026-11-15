/**
 * AWS Terrain Tiles (Terrarium encoding) helpers.
 * elevation_m = (R × 256 + G + B / 256) − 32768
 * https://github.com/tilezen/joerd/blob/master/docs/formats.md
 */

export const AWS_TERRARIUM_URL = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png';
export const AWS_TERRARIUM_MAXZOOM = 15;
export const AWS_TERRAIN_ATTRIBUTION =
  '<a href="https://github.com/tilezen/joerd/blob/master/docs/attribution.md" target="_blank" rel="noopener">' +
  'Terrain Tiles: Mapzen/Tilezen · USGS 3DEP · NOAA · et al.</a>';

export function decodeTerrarium(r: number, g: number, b: number): number {
  return r * 256 + g + b / 256 - 32768;
}

export interface TilePixel {
  z: number;
  x: number;
  y: number;
  px: number;
  py: number;
}

/** Web Mercator tile + pixel for a lng/lat at zoom z (256 px tiles). */
export function lngLatToTilePixel(lng: number, lat: number, z: number, tileSize = 256): TilePixel {
  const n = 2 ** z;
  const latRad = (lat * Math.PI) / 180;
  const fx = ((lng + 180) / 360) * n;
  const fy = ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n;
  const x = Math.floor(fx);
  const y = Math.floor(fy);
  return {
    z,
    x,
    y,
    px: Math.min(tileSize - 1, Math.floor((fx - x) * tileSize)),
    py: Math.min(tileSize - 1, Math.floor((fy - y) * tileSize)),
  };
}

/** Approximate ground size of one tile pixel (m) at a latitude and zoom. */
export function pixelSizeMeters(lat: number, z: number, tileSize = 256): number {
  return (Math.cos((lat * Math.PI) / 180) * 2 * Math.PI * 6378137) / (tileSize * 2 ** z);
}

const tileCache = new Map<string, Promise<ImageData>>();

async function loadTile(z: number, x: number, y: number): Promise<ImageData> {
  const key = `${z}/${x}/${y}`;
  let p = tileCache.get(key);
  if (!p) {
    p = (async () => {
      const url = AWS_TERRARIUM_URL.replace('{z}', String(z)).replace('{x}', String(x)).replace('{y}', String(y));
      const res = await fetch(url, { mode: 'cors' });
      if (!res.ok) throw new Error(`Terrain tile ${key}: HTTP ${res.status}`);
      const bmp = await createImageBitmap(await res.blob());
      const canvas = new OffscreenCanvas(bmp.width, bmp.height);
      const ctx = canvas.getContext('2d');
      if (!ctx) throw new Error('2D canvas unavailable');
      ctx.drawImage(bmp, 0, 0);
      return ctx.getImageData(0, 0, bmp.width, bmp.height);
    })();
    p.catch(() => tileCache.delete(key));
    tileCache.set(key, p);
  }
  return p;
}

export interface TerrainSample {
  elevation_m: number;
  zoom: number;
  pixel_size_m: number;
  source: 'AWS Terrain Tiles (Terrarium)';
}

/** Sample AWS regional terrain at a point (nearest pixel at maxzoom). */
export async function sampleAwsElevation(lng: number, lat: number): Promise<TerrainSample> {
  const t = lngLatToTilePixel(lng, lat, AWS_TERRARIUM_MAXZOOM);
  const img = await loadTile(t.z, t.x, t.y);
  const i = (t.py * img.width + t.px) * 4;
  const d = img.data;
  return {
    elevation_m: decodeTerrarium(d[i]!, d[i + 1]!, d[i + 2]!),
    zoom: t.z,
    pixel_size_m: pixelSizeMeters(lat, t.z),
    source: 'AWS Terrain Tiles (Terrarium)',
  };
}
