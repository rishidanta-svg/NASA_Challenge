import { slotById } from '../config/slots';
import type { LayerDescriptor } from '../api/schemas';

/** Days between two YYYY-MM-DD dates (absolute). */
export function dayDistance(a: string, b: string): number {
  return Math.abs(Date.parse(`${a}T00:00:00Z`) - Date.parse(`${b}T00:00:00Z`)) / 86_400_000;
}

/**
 * Pick the descriptor that fills a slot for the selected timeline date:
 * - only `status: available` descriptors are eligible
 * - time-independent products (reference_date null) always qualify
 * - otherwise the descriptor with the nearest reference_date wins
 */
export function resolveSlot(layers: LayerDescriptor[] | null | undefined, slot: string, date: string): LayerDescriptor | null {
  const cands = (layers ?? []).filter((l) => l.slot === slot && l.status === 'available');
  if (!cands.length) return null;
  if (slotById(slot)?.exactDate) return cands.find((l) => l.reference_date === date) ?? null;
  const timeless = cands.find((l) => !l.reference_date);
  if (timeless) return timeless;
  return cands.reduce((best, l) =>
    dayDistance(l.reference_date!, date) < dayDistance(best.reference_date!, date) ? l : best,
  );
}

/** Descriptors in a slot regardless of status (used to show "awaiting" reasons). */
export function slotDescriptors(layers: LayerDescriptor[] | null | undefined, slot: string): LayerDescriptor[] {
  return (layers ?? []).filter((l) => l.slot === slot);
}

export function isMockDescriptor(l: LayerDescriptor | null | undefined): boolean {
  return !!l && (l.provenance.source.startsWith('MOCK') || (l.url ?? '').startsWith('mock://'));
}

/** Raster-DEM descriptors usable as 3D terrain sources (e.g. USACE LiDAR epochs). */
export function demDescriptors(layers: LayerDescriptor[] | null | undefined): LayerDescriptor[] {
  return (layers ?? []).filter((l) => l.kind === 'raster_dem' && l.status === 'available');
}
