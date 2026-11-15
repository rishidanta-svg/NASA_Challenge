import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The API base URL is read at runtime from import.meta.env.VITE_API_BASE_URL
// (see src/config/env.ts). No dev proxy is used so the browser talks to the
// FastAPI origin exactly as it will in production; the backend must send CORS
// headers for http://localhost:5173 (documented in docs/frontend-api-contract.md).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true },
  preview: { port: 4173, strictPort: true },
  build: {
    sourcemap: true,
    chunkSizeWarningLimit: 1500,
  },
  test: {
    environment: 'node',
    include: ['tests/unit/**/*.test.ts'],
  },
});
