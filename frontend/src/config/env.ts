/** Runtime configuration from Vite environment variables. */

export type EnvironmentSourceMode = 'auto' | 'noaa' | 'api';

const env = import.meta.env;

export const API_BASE_URL: string = String(env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '');

const mode = String(env.VITE_ENVIRONMENT_SOURCE || 'auto');
export const ENVIRONMENT_SOURCE: EnvironmentSourceMode =
  mode === 'noaa' || mode === 'api' || mode === 'auto' ? mode : 'auto';

export const NOAA_STATION: string = String(env.VITE_NOAA_STATION || '8651370');
