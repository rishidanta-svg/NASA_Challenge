import type { DataOrigin, DataState } from '../api/client';

export interface DataStateBadgeProps {
  state: DataState;
  origin?: DataOrigin;
  inferred?: boolean;
  label?: string;
  title?: string;
}

export function DataStateBadge({ state, origin, inferred, label, title }: DataStateBadgeProps) {
  if (inferred) {
    return (
      <span className="badge badge-model" title={title ?? 'Physics-informed model estimate — not a direct sensor measurement'}>
        MODEL · {state === 'mock' ? 'MOCK' : 'INFERRED'}
      </span>
    );
  }
  if (state === 'real') {
    const src = origin === 'noaa' ? 'NOAA LIVE' : 'VERIFIED';
    return (
      <span className="badge badge-real" title={title ?? 'Verified observation'}>
        {label ?? `REAL · ${src}`}
      </span>
    );
  }
  if (state === 'config') {
    return (
      <span className="badge badge-config" title={title ?? 'Declared project configuration'}>
        {label ?? 'CONFIG'}
      </span>
    );
  }
  if (state === 'mock') {
    return (
      <span className="badge badge-mock" title={title ?? 'Synthetic placeholder — never interpret as a physical measurement'}>
        {label ?? 'MOCK · SYNTHETIC'}
      </span>
    );
  }
  return (
    <span className="badge badge-unavailable" title={title ?? 'Awaiting dataset from backend pipeline'}>
      {label ?? 'AWAITING DATA'}
    </span>
  );
}
