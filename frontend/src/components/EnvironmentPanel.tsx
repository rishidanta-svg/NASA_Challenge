import { useCallback, useEffect, useState } from 'react';
import { getEnvironmentLatest, type Sourced } from '../api/client';
import { clearCache } from '../api/http';
import type { EnvironmentLatest } from '../api/schemas';
import { NOAA_DUCK_STATION } from '../config/geo';
import { DataStateBadge } from './DataStateBadge';

export function EnvironmentPanel() {
  const [env, setEnv] = useState<Sourced<EnvironmentLatest> | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (force = false) => {
    setLoading(true);
    if (force) clearCache('noaa:');
    try {
      const res = await getEnvironmentLatest();
      setEnv(res);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(false);
    const id = setInterval(() => void load(false), 180_000);
    return () => clearInterval(id);
  }, [load]);

  const observations = env?.data?.observations ?? [];

  return (
    <section className="panel-section" aria-label="Live Environmental Observations" data-testid="env-panel">
      <div className="panel-heading">
        <div>
          <h2>Live Environment · Duck Pier</h2>
          <small className="mono muted" style={{ fontSize: 9.5 }}>
            NOAA Station {NOAA_DUCK_STATION.id} ({NOAA_DUCK_STATION.lat}° N, {Math.abs(NOAA_DUCK_STATION.lon)}° W)
          </small>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <DataStateBadge state={env?.state ?? 'unavailable'} origin={env?.origin} />
          <button
            onClick={() => void load(true)}
            disabled={loading}
            style={{ padding: '3px 7px', fontSize: 10.5 }}
            title="Refresh NOAA station readings"
          >
            {loading ? '…' : '↻'}
          </button>
        </div>
      </div>

      {env?.reason && (
        <div className="slot-meta" style={{ marginBottom: 6 }}>
          {env.reason}
        </div>
      )}

      {observations.length === 0 ? (
        <div className="slot-meta">
          {loading ? 'Querying NOAA CO-OPS station 8651370…' : 'No live observations available.'}
        </div>
      ) : (
        <div>
          {observations.map((o) => {
            const ageMin =
              o.observed_at && o.kind === 'observation'
                ? Math.round((Date.now() - Date.parse(o.observed_at)) / 60_000)
                : null;
            const stale = ageMin !== null && ageMin > 90;
            const dir = o.extra?.direction_cardinal ? ` ${o.extra.direction_cardinal}` : '';

            return (
              <div key={o.variable} className="env-row">
                <div>
                  <div style={{ fontWeight: 500, fontSize: 12 }}>
                    {o.label}
                    {o.datum ? <span className="mono muted"> ({o.datum})</span> : null}
                    {o.kind === 'prediction' && (
                      <span className="mono" style={{ fontSize: 9.5, color: 'var(--gold)', marginLeft: 5 }}>
                        TIDE PREDICTION
                      </span>
                    )}
                  </div>
                  <div className="mono muted" style={{ fontSize: 9.5 }}>
                    {o.observed_at ? o.observed_at.replace('T', ' ').replace(':00Z', ' UTC') : 'No timestamp'}
                    {o.quality && o.quality !== 'unknown' ? ` · ${o.quality}` : ''}
                    {stale ? ` · ${ageMin}m ago` : ''}
                  </div>
                </div>
                <div className="mono" style={{ fontWeight: 600, fontSize: 12.5, textAlign: 'right' }}>
                  {o.value !== null ? (
                    <span style={{ color: stale ? 'var(--gold)' : 'var(--text)' }}>
                      {o.value.toFixed(2)} {o.units}
                      {dir}
                    </span>
                  ) : (
                    <span className="muted" title={o.error ?? 'Unavailable at station'}>
                      N/A
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="slot-meta" style={{ marginTop: 8 }}>
        Source:{' '}
        <a href={NOAA_DUCK_STATION.url} target="_blank" rel="noopener noreferrer">
          NOAA Tides &amp; Currents #8651370 ↗
        </a>{' '}
        · Unavailable readings remain N/A and are never fabricated.
      </div>
    </section>
  );
}
