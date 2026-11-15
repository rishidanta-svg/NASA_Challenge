import { expect, test } from '@playwright/test';

const ARTIFACT_DIR = '/Users/tanvidanta/.gemini/antigravity/brain/7e0d87ad-fc9f-4aba-acea-1e94e9a2d8b7';

test('POLTERGEIST 2D -> 3D Duck FRF coastal map, scientific slots, cross-section, and live NOAA data', async ({
  page,
}) => {
  await page.goto('/');

  // Verify POLTERGEIST branding (no LITTORAL branding)
  await expect(page.locator('.brand-title')).toHaveText('POLTERGEIST');
  await expect(page.locator('body')).not.toContainText('LITTORAL');

  // Verify MapLibre canvas renders
  const canvas = page.locator('.maplibregl-canvas').first();
  await expect(canvas).toBeVisible();

  // Verify all 10 scientific overlay slots exist
  for (const slotId of [
    'lidar-dz',
    'nisar-hh',
    'nisar-hv',
    'nisar-boundary',
    's1-vv',
    's1-vh',
    's2-index',
    's2-boundary',
    'model-dz',
    'model-sigma',
  ]) {
    await expect(page.getByTestId(`slot-${slotId}`)).toBeVisible();
  }

  // Enable radar and optical boundaries + model prediction
  await page.getByTestId('slot-nisar-boundary').locator('input[type="checkbox"]').check();
  await page.getByTestId('slot-s2-boundary').locator('input[type="checkbox"]').check();

  // Select transect FRF-Y1000 and verify Inspector + Cross-Section update
  await page.getByTestId('transect-FRF-Y1000').click();
  await expect(page.getByTestId('cross-section')).toContainText('FRF y = 1000 m (FRF-Y1000)');

  // Wait for OpenFreeMap tiles + live NOAA 8651370 response to settle
  await page.waitForTimeout(3500);
  await expect(page.getByTestId('env-panel')).toContainText('Water level');

  // Capture 2D verified screenshot
  await page.screenshot({ path: `${ARTIFACT_DIR}/poltergeist-2d-duck-frf.png` });

  // Switch basemap to Dark and confirm scientific overlays remain active
  await page.getByTestId('basemap-select').selectOption('dark');
  await page.waitForTimeout(2000);

  // Switch to Phase 2: 3D Terrain mode
  await page.getByTestId('mode-3d').click();
  await expect(page.locator('.map-hud-top-left')).toContainText('3D');
  await expect(page.locator('.map-hud-top-left')).toContainText('1× vert');
  await page.waitForTimeout(2500);

  // Capture 3D verified screenshot
  await page.screenshot({ path: `${ARTIFACT_DIR}/poltergeist-3d-terrain.png` });
});
