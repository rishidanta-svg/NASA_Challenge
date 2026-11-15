import { dayDistance } from '../lib/layers';
import { useApp } from '../state/store';

const PRESET_DATES = [
  { label: 'Jun 2026', date: '2026-06-18' },
  { label: 'Jun 30 S1', date: '2026-06-30' },
  { label: 'Jul 2026', date: '2026-07-15' },
  { label: 'Aug 2026', date: '2026-08-15' },
  { label: 'Sep 2026', date: '2026-09-28' },
  { label: 'Oct 2026', date: '2026-10-16' },
] as const;

export function Timeline() {
  const { date, compare, compareDate, acquisitions, set } = useApp();
  const acqList = acquisitions?.data ?? [];

  const nearestAcq =
    acqList.length > 0
      ? acqList.reduce((best, a) =>
          dayDistance(a.acquired_at.slice(0, 10), date) < dayDistance(best.acquired_at.slice(0, 10), date) ? a : best,
        )
      : null;

  return (
    <section className="panel-section" aria-label="June to October 2026 Timeline">
      <div className="panel-heading">
        <h2>Observation Timeline</h2>
        <span className="mono muted" style={{ fontSize: 10 }}>
          JUN–OCT 2026
        </span>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 8 }}>
        {PRESET_DATES.map((p) => (
          <button
            key={p.date}
            onClick={() => set({ date: p.date })}
            style={{
              padding: '4px 7px',
              fontSize: 10.5,
              fontFamily: 'var(--font-mono)',
              borderColor: date === p.date ? 'var(--cyan)' : undefined,
              background: date === p.date ? 'var(--cyan-dim)' : undefined,
              color: date === p.date ? 'var(--cyan)' : undefined,
            }}
          >
            {p.label}
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <label className="mono" style={{ fontSize: 11, color: 'var(--muted)' }}>
          Active date
        </label>
        <input
          type="date"
          min="2026-06-01"
          max="2026-10-31"
          value={date}
          onChange={(e) => set({ date: e.target.value })}
          aria-label="Primary observation date"
          data-testid="timeline-date"
        />
      </div>

      <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={compare}
            onChange={(e) => set({ compare: e.target.checked })}
            data-testid="compare-toggle"
          />
          <span>Swipe compare date</span>
        </label>
        {compare && (
          <input
            type="date"
            min="2026-06-01"
            max="2026-10-31"
            value={compareDate}
            onChange={(e) => set({ compareDate: e.target.value })}
            aria-label="Comparison observation date"
          />
        )}
      </div>

      <div className="slot-meta" style={{ marginTop: 8 }} data-testid="timeline-acquisitions-summary">
        {acqList.length > 0 ? (
          <div>
            <div>
              <strong>{acqList.length} verified acquisitions</strong> in register (5 June · 4 October · 19 additional).
              Nearest scene to {date} selected per sensor.
            </div>
            {nearestAcq && (
              <div className="mono" style={{ fontSize: 10, marginTop: 4, color: 'var(--text)' }}>
                Active scene: {nearestAcq.sensor} · {nearestAcq.acquired_at.slice(0, 19).replace('T', ' ')}Z
                {nearestAcq.environment?.predicted_tide_stage
                  ? ` · Tide ${nearestAcq.environment.predicted_tide_stage}`
                  : ''}
                {nearestAcq.environment?.water_level_m_mllw != null
                  ? ` (${nearestAcq.environment.water_level_m_mllw.toFixed(2)} m MLLW)`
                  : ''}
                {nearestAcq.environment?.wave_hs_m_17m != null
                  ? ` · Hs ${nearestAcq.environment.wave_hs_m_17m.toFixed(2)} m`
                  : ''}
              </div>
            )}
          </div>
        ) : (
          <div>
            <strong>Acquisition register:</strong> awaiting <code className="mono">/api/acquisitions</code> from data
            pipeline (no timestamps fabricated).
          </div>
        )}
      </div>
    </section>
  );
}
