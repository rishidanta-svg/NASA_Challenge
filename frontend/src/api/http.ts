/** Minimal fetch wrapper: timeouts, typed errors, and a TTL promise cache. */

export type ApiErrorKind = 'network' | 'timeout' | 'http' | 'schema' | 'unavailable' | 'upstream';

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly kind: ApiErrorKind,
    public readonly status?: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export interface FetchOptions {
  timeoutMs?: number;
  signal?: AbortSignal;
}

export async function fetchJson(url: string, { timeoutMs = 8000, signal }: FetchOptions = {}): Promise<unknown> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(new DOMException('timeout', 'TimeoutError')), timeoutMs);
  const onAbort = () => ctrl.abort(signal?.reason);
  signal?.addEventListener('abort', onAbort, { once: true });
  let res: Response;
  try {
    res = await fetch(url, { signal: ctrl.signal, headers: { Accept: 'application/json' } });
  } catch (err) {
    if (ctrl.signal.aborted && !signal?.aborted) throw new ApiError(`Timed out after ${timeoutMs} ms: ${url}`, 'timeout');
    throw new ApiError(`Network error (offline, DNS or CORS): ${url}`, 'network');
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', onAbort);
  }
  if (!res.ok) {
    let detail = '';
    try {
      const body = (await res.json()) as { title?: string; detail?: string };
      detail = body.detail || body.title || '';
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(`HTTP ${res.status}${detail ? `: ${detail}` : ''} — ${url}`, 'http', res.status);
  }
  try {
    return await res.json();
  } catch {
    throw new ApiError(`Response is not JSON: ${url}`, 'schema');
  }
}

interface CacheEntry {
  expires: number;
  promise: Promise<unknown>;
}
const cache = new Map<string, CacheEntry>();

/** Share in-flight requests and cache successful results for ttlMs. Failures are not cached. */
export function cached<T>(key: string, ttlMs: number, fn: () => Promise<T>): Promise<T> {
  const now = Date.now();
  const hit = cache.get(key);
  if (hit && hit.expires > now) return hit.promise as Promise<T>;
  const promise = fn();
  cache.set(key, { expires: now + ttlMs, promise });
  promise.catch(() => {
    if (cache.get(key)?.promise === promise) cache.delete(key);
  });
  return promise;
}

export function clearCache(prefix = ''): void {
  for (const k of cache.keys()) if (k.startsWith(prefix)) cache.delete(k);
}
