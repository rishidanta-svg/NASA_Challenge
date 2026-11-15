/**
 * POLTERGEIST FastAPI client.
 *
 * Every function resolves to a `Sourced<T>`, never throws, and states where its
 * data came from:
 *   real        — validated response from FastAPI (or NOAA for environment)
 *   config      — declared project configuration (e.g. the study bbox)
 *   unavailable — no data (never filled with invented values)
 *
 * Unavailable or invalid science responses retain their own state.
 */
import type { ZodType, ZodTypeDef } from 'zod';
import { API_BASE_URL, ENVIRONMENT_SOURCE, NOAA_STATION } from '../config/env';
import { FRF_Y_RANGE_M, NOAA_DUCK_STATION, STUDY_BOUNDS } from '../config/geo';
import { cached, fetchJson } from './http';
import { fetchNoaaLatest } from './noaa';
import {
  BoundaryAnalysisSchema,
  type BoundaryAnalysis,
  NisarEvidenceSchema,
  type NisarEvidence,
  AcquisitionListSchema,
  AnalysisSchema,
  CoastalEvidenceSchema,
  EnvironmentLatestSchema,
  LayerListSchema,
  StudyAreaSchema,
  TerrainChangeSchema,
  TransectCollectionSchema,
  TransectDetailSchema,
  UnavailableSchema,
  type Acquisition,
  type Analysis,
  type CoastalEvidence,
  type EnvironmentLatest,
  type LayerDescriptor,
  type StudyArea,
  type TerrainChange,
  type TransectDetail,
  type TransectSummary,
} from './schemas';

export type DataState = 'real' | 'config' | 'mock' | 'unavailable';
export type DataOrigin = 'fastapi' | 'noaa' | 'mock' | 'config' | 'none';

export interface Sourced<T> {
  data: T | null;
  state: DataState;
  origin: DataOrigin;
  /** Why we fell back / why data is missing. */
  reason?: string;
  fetchedAt: string;
}

export const ENDPOINTS = {
  studyArea: '/api/study-area',
  acquisitions: '/api/acquisitions',
  layers: '/api/layers',
  terrainChange: '/api/terrain/change',
  coastalEvidence: '/api/coastal/observations',
  transects: '/api/transects',
  transect: (id: string) => `/api/transects/${encodeURIComponent(id)}`,
  analysis: (id: string) => `/api/analysis/${encodeURIComponent(id)}`,
  environmentLatest: '/api/environment/latest',
} as const;

const now = () => new Date().toISOString();

export function apiUrl(path: string): string {
  return /^https?:\/\//.test(path) ? path : `${API_BASE_URL}${path}`;
}

type Got<T> = { ok: true; data: T } | { ok: false; reason: string };

/** Fetch and validate one independent product. */
async function get<T>(path: string, schema: ZodType<T, ZodTypeDef, unknown>, ttlMs: number): Promise<Got<T>> {
  try {
    const body = await cached(`api:${path}`, ttlMs, () => fetchJson(apiUrl(path)));
    const un = UnavailableSchema.safeParse(body);
    if (un.success) return { ok: false, reason: `Backend: ${un.data.reason}` };
    const parsed = schema.safeParse(body);
    if (!parsed.success) {
      const issue = parsed.error.issues[0];
      return {
        ok: false,
        reason: `Contract violation at ${path}: ${issue?.path.join('.') || '(root)'} — ${issue?.message ?? 'invalid'}`,
      };
    }
    return { ok: true, data: parsed.data };
  } catch (err) {
    return { ok: false, reason: err instanceof Error ? err.message : String(err) };
  }
}

function sourced<T>(g: Got<T>): Sourced<T> {
  if (g.ok) return { data: g.data, state: 'real', origin: 'fastapi', fetchedAt: now() };
  return { data: null, state: 'unavailable', origin: 'none', reason: g.reason, fetchedAt: now() };
}

// ---------------- endpoints ----------------

export function configStudyArea(): StudyArea {
  const { west: w, south: s, east: e, north: n } = STUDY_BOUNDS;
  return {
    type: 'Feature',
    geometry: { type: 'Polygon', coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] },
    properties: { name: 'Duck FRF study area', analysis_crs: 'EPSG:32618', frf_y_range_m: [FRF_Y_RANGE_M[0], FRF_Y_RANGE_M[1]] },
  };
}

export async function getStudyArea(): Promise<Sourced<StudyArea>> {
  const g = await get(ENDPOINTS.studyArea, StudyAreaSchema, 3600_000);
  if (g.ok) return { data: g.data, state: 'real', origin: 'fastapi', fetchedAt: now() };
  return { data: configStudyArea(), state: 'config', origin: 'config', reason: g.reason, fetchedAt: now() };
}

export async function getAcquisitions(): Promise<Sourced<Acquisition[]>> {
  const g = await get(ENDPOINTS.acquisitions, AcquisitionListSchema, 300_000);
  if (g.ok) return { data: g.data, state: 'real', origin: 'fastapi', fetchedAt: now() };
  // No mock acquisitions: inventing acquisition times would misrepresent the record.
  return { data: null, state: 'unavailable', origin: 'none', reason: g.reason, fetchedAt: now() };
}

export async function getLayers(): Promise<Sourced<LayerDescriptor[]>> {
  return sourced(await get(ENDPOINTS.layers, LayerListSchema, 300_000));
}

export async function getCoastalEvidence(): Promise<Sourced<CoastalEvidence>> {
  return sourced(await get(ENDPOINTS.coastalEvidence, CoastalEvidenceSchema, 300_000));
}

export async function getTerrainChange(): Promise<Sourced<TerrainChange>> {
  return sourced(await get(ENDPOINTS.terrainChange, TerrainChangeSchema, 300_000));
}

export async function getTransects(): Promise<Sourced<TransectSummary[]>> {
  const g = await get(ENDPOINTS.transects, TransectCollectionSchema, 300_000);
  return sourced(g.ok ? { ok: true, data: g.data.features } : g);
}

export async function getTransect(id: string): Promise<Sourced<TransectDetail>> {
  return sourced(await get(ENDPOINTS.transect(id), TransectDetailSchema, 300_000));
}

export async function getAnalysis(id: string): Promise<Sourced<Analysis>> {
  return sourced(await get(ENDPOINTS.analysis(id), AnalysisSchema, 300_000));
}

/**
 * Live environment: FastAPI first (mode auto/api), then NOAA CO-OPS directly
 * (mode auto/noaa). Never mocked.
 */
export async function getEnvironmentLatest(): Promise<Sourced<EnvironmentLatest>> {
  const reasons: string[] = [];
  if (ENVIRONMENT_SOURCE !== 'noaa') {
    const g = await get(ENDPOINTS.environmentLatest, EnvironmentLatestSchema, 60_000);
    if (g.ok) return { data: g.data, state: 'real', origin: 'fastapi', fetchedAt: now() };
    reasons.push(g.reason);
    if (ENVIRONMENT_SOURCE === 'api') return { data: null, state: 'unavailable', origin: 'none', reason: g.reason, fetchedAt: now() };
  }
  try {
    const data = await cached(`noaa:${NOAA_STATION}`, 60_000, () =>
      fetchNoaaLatest(NOAA_STATION, NOAA_STATION === NOAA_DUCK_STATION.id ? NOAA_DUCK_STATION.name : NOAA_STATION),
    );
    const anyValue = data.observations.some((o) => o.value !== null);
    if (!anyValue) throw new Error('NOAA returned no current values for any product');
    return {
      data,
      state: 'real',
      origin: 'noaa',
      reason: reasons.length ? `FastAPI unavailable (${reasons[0]}); using NOAA CO-OPS directly` : undefined,
      fetchedAt: now(),
    };
  } catch (err) {
    reasons.push(err instanceof Error ? err.message : String(err));
    return { data: null, state: 'unavailable', origin: 'none', reason: reasons.join(' · '), fetchedAt: now() };
  }
}

export async function getBoundaryAnalysis(id: string): Promise<Sourced<BoundaryAnalysis>> {
  return sourced(await get(`/api/boundary-analysis/${encodeURIComponent(id)}`, BoundaryAnalysisSchema, 300_000));
}

export async function getNisarEvidence(): Promise<Sourced<NisarEvidence>> {
  return sourced(await get('/api/coastal/nisar',NisarEvidenceSchema,300_000));
}
