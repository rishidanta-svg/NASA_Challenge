import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 45_000,
  use: {
    baseURL: 'http://localhost:4173',
    channel: 'chrome',
    viewport: { width: 1440, height: 900 },
    headless: true,
  },
  webServer: [
    {
      command: '../.venv/bin/python -m uvicorn backend.app:app --app-dir .. --host 127.0.0.1 --port 8000',
      url: 'http://localhost:8000/api/study-area',
      reuseExistingServer: true,
      timeout: 20_000,
    },
    {
      command: 'npm run preview',
      url: 'http://localhost:4173',
      reuseExistingServer: true,
      timeout: 20_000,
    },
  ],
});
