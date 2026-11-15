import type { Colormap } from '../api/schemas';

export interface LegendProps {
  colormap?: Colormap | null;
  units: string | null;
  inferred?: boolean;
  meaning?: string;
}

export function Legend({ colormap, units, inferred, meaning }: LegendProps) {
  if (!colormap) {
    return meaning ? <div className="slot-meta">{meaning}</div> : null;
  }
  const min = colormap.min;
  const max = colormap.max;
  const span = max - min || 1;
  const stopsCss = colormap.stops
    .map(([v, c]) => `${c} ${(((v - min) / span) * 100).toFixed(1)}%`)
    .join(', ');
  const mid = (min + max) / 2;

  return (
    <div className="legend-block">
      {meaning && <div className="slot-meta" style={{ marginBottom: 6 }}>{meaning}</div>}
      <div
        className={`legend-gradient ${inferred ? 'inferred' : ''}`}
        style={{ background: `linear-gradient(90deg, ${stopsCss})` }}
        role="img"
        aria-label={`Color scale from ${min} to ${max} ${units ?? ''}`}
      />
      <div className="legend-ticks num">
        <span>
          {min > 0 ? `+${min}` : min} {units ?? ''}
        </span>
        <span>
          {mid === 0 ? '0' : mid.toFixed(2)} {units ?? ''}
        </span>
        <span>
          {max > 0 ? `+${max}` : max} {units ?? ''}
        </span>
      </div>
      <div className="legend-caption muted">
        <span>Scale: {colormap.type}</span>
        <span>{inferred ? 'Conditional / estimated' : 'Measured / direct'}</span>
      </div>
    </div>
  );
}
