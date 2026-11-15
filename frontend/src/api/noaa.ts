/**
 * Direct browser client for NOAA CO-OPS (Tides & Currents) station data.
 * Used for live environmental context until FastAPI /api/environment/latest
 * is available. CORS: api.tidesandcurrents.noaa.gov sends
 * `Access-Control-Allow-Origin: *` (verified 2026-11-15).
 *
 * Values are passed through exactly as published. Missing readings stay null.
 */
import { fetchJson } from './http';
import type { EnvironmentLatest, EnvironmentObservation } from './schemas';

const DATAGETTER = 'https://api.tidesandcurrents.noaa.gov/api/prod/datagetter';
const APP = 'POLTERGEIST_NASA_SpaceApps';

interface NoaaRow {
  t?: string;
  v?: string;
  s?: string;
  d?: string;
  dr?: string;
  g?: string;
  f?: string;
  q?: string;
  type?: string;
}
interface NoaaResponse {
  metadata?: { id: string; name: string; lat: string; lon: string };
  data?: NoaaRow[];
  predictions?: NoaaRow[];
  error?: { message: string };
}

/** NOAA "YYYY-MM-DD HH:MM" in GMT → ISO-8601 UTC. */
export function noaaTimeToIso(t: string | undefined): string | null {
  if (!t) return null;
  const m = /^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})$/.exec(t.trim());
  return m ? `${m[1]}T${m[2]}:00Z` : null;
}

/** NOAA numeric string → number; empty / non-numeric → null (never coerced to 0). */
export function noaaNumber(v: string | undefined): number | null {
  if (v === undefined || v.trim() === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function url(station: string, params: Record<string, string>): string {
  const q = new URLSearchParams({
    station,
    units: 'metric',
    time_zone: 'gmt',
    format: 'json',
    application: APP,
    ...params,
  });
  return `${DATAGETTER}?${q.toString()}`;
}

async function getProduct(station: string, params: Record<string, string>): Promise<NoaaResponse> {
  const body = (await fetchJson(url(station, params), { timeoutMs: 10000 })) as NoaaResponse;
  if (body.error) throw new Error(body.error.message.trim());
  return body;
}

function base(
  station: string,
  stationName: string,
  variable: string,
  label: string,
  units: string,
  product: string,
): Omit<EnvironmentObservation, 'value' | 'observed_at'> {
  return {
    variable,
    label,
    units,
    kind: 'observation',
    station_id: station,
    station_name: stationName,
    provider: 'NOAA CO-OPS',
    source_url: `https://tidesandcurrents.noaa.gov/stationhome.html?id=${station}`,
    extra: { product },
  };
}

function missing(
  b: Omit<EnvironmentObservation, 'value' | 'observed_at'>,
  err: unknown,
): EnvironmentObservation {
  return { ...b, value: null, observed_at: null, error: err instanceof Error ? err.message : String(err) };
}

export async function fetchNoaaLatest(station: string, stationName = 'Duck, NC', now = new Date()): Promise<EnvironmentLatest> {
  const S = (variable: string, label: string, units: string, product: string) =>
    base(station, stationName, variable, label, units, product);

  const wlBase = { ...S('water_level', 'Water level', 'm', 'water_level'), datum: 'NAVD88' };
  const windBase = S('wind_speed', 'Wind speed', 'm/s', 'wind');
  const gustBase = S('wind_gust', 'Wind gust', 'm/s', 'wind');
  const atBase = S('air_temperature', 'Air temperature', '°C', 'air_temperature');
  const wtBase = S('water_temperature', 'Water temperature', '°C', 'water_temperature');
  const apBase = S('air_pressure', 'Barometric pressure', 'hPa', 'air_pressure');

  const [wl, wind, at, wt, ap, pred] = await Promise.allSettled([
    getProduct(station, { date: 'latest', product: 'water_level', datum: 'NAVD' }),
    getProduct(station, { date: 'latest', product: 'wind' }),
    getProduct(station, { date: 'latest', product: 'air_temperature' }),
    getProduct(station, { date: 'latest', product: 'water_temperature' }),
    getProduct(station, { date: 'latest', product: 'air_pressure' }),
    getProduct(station, { range: '30', begin_date: fmtNoaaDate(now), product: 'predictions', datum: 'NAVD', interval: 'hilo' }),
  ]);

  const obs: EnvironmentObservation[] = [];

  const single = (
    r: PromiseSettledResult<NoaaResponse>,
    b: Omit<EnvironmentObservation, 'value' | 'observed_at'>,
    withQuality = false,
  ): EnvironmentObservation => {
    if (r.status === 'rejected') return missing(b, r.reason);
    const row = r.value.data?.[0];
    if (!row) return missing(b, 'No data row returned');
    const value = noaaNumber(row.v);
    return {
      ...b,
      value,
      observed_at: noaaTimeToIso(row.t),
      qc_flag: row.f ?? null,
      quality: withQuality ? (row.q === 'v' ? 'verified' : row.q === 'p' ? 'preliminary' : 'unknown') : 'unknown',
      error: value === null ? 'Station reported an empty value' : null,
    };
  };

  obs.push(single(wl, wlBase, true));

  if (wind.status === 'rejected') {
    obs.push(missing(windBase, wind.reason), missing(gustBase, wind.reason));
  } else {
    const row = wind.value.data?.[0];
    const t = noaaTimeToIso(row?.t);
    const speed = noaaNumber(row?.s);
    const gust = noaaNumber(row?.g);
    const dir = noaaNumber(row?.d);
    obs.push({
      ...windBase,
      value: speed,
      observed_at: t,
      qc_flag: row?.f ?? null,
      quality: 'unknown',
      extra: { product: 'wind', direction_deg_true: dir, direction_cardinal: row?.dr ?? null },
      error: speed === null ? 'Station reported an empty value' : null,
    });
    obs.push({
      ...gustBase,
      value: gust,
      observed_at: t,
      qc_flag: row?.f ?? null,
      quality: 'unknown',
      error: gust === null ? 'Station reported an empty value' : null,
    });
  }

  obs.push(single(at, atBase), single(wt, wtBase), single(ap, apBase));

  // Tide predictions: next high and next low after `now`. Labelled as predictions, not observations.
  if (pred.status === 'fulfilled') {
    const rows = (pred.value.predictions ?? [])
      .map((p) => ({ ...p, iso: noaaTimeToIso(p.t) }))
      .filter((p) => p.iso && new Date(p.iso).getTime() > now.getTime());
    for (const type of ['H', 'L'] as const) {
      const p = rows.find((r) => r.type === type);
      if (!p) continue;
      obs.push({
        ...S(type === 'H' ? 'tide_next_high' : 'tide_next_low', type === 'H' ? 'Next high tide' : 'Next low tide', 'm', 'predictions'),
        kind: 'prediction',
        datum: 'NAVD88',
        value: noaaNumber(p.v),
        observed_at: p.iso,
        quality: 'unknown',
      });
    }
  }

  return { retrieved_at: new Date().toISOString(), observations: obs };
}

function fmtNoaaDate(d: Date): string {
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, '0');
  const day = String(d.getUTCDate()).padStart(2, '0');
  const hh = String(d.getUTCHours()).padStart(2, '0');
  const mm = String(d.getUTCMinutes()).padStart(2, '0');
  return `${y}${m}${day} ${hh}:${mm}`;
}
