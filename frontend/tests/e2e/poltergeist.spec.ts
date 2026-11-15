import { expect, test } from '@playwright/test';

test('POLTERGEIST displays live NOAA and verified June and October Duck FRF layers in 2D and 3D', async ({ page }, info) => {
  const images = new Set<string>();
  const errors: string[] = [];
  const failures: string[] = [];
  let basemapLoaded = false;
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('response', (response) => {
    const url = new URL(response.url());
    if (url.hostname === 'tiles.openfreemap.org' && url.pathname.includes('/styles/') && response.ok()) basemapLoaded = true;
    const layer = /^\/api\/tiles\/([^/]+)\//.exec(url.pathname)?.[1];
    if (layer && response.ok() && response.headers()['content-type'] === 'image/png') images.add(layer);
    if (layer && response.status() >= 400) failures.push(`${layer} ${response.status()}`);
  });
  const noaa = page.waitForResponse((r) => r.url().endsWith('/api/environment/latest') && r.ok());

  await page.goto('/');
  await expect(page.locator('.brand-title')).toHaveText('POLTERGEIST');
  await expect(page.locator('.maplibregl-canvas').first()).toBeVisible();
  await expect.poll(() => basemapLoaded, { timeout: 20_000 }).toBe(true);

  const zoom = () => page.locator('.map-hud-camera').innerText().then((value) => Number(/Z ([0-9.]+)/.exec(value)?.[1]));
  await expect.poll(zoom).toBeGreaterThan(15);
  const dz = page.getByTestId('slot-lidar-dz');
  await expect(dz.getByRole('img')).toHaveAccessibleName('Color scale from -2.5 to 2.5 m');
  await expect.poll(() => images.has('lidar-dz-2026-oct-jun'), { timeout: 20_000 }).toBe(true);
  for (const slot of ['nisar-boundary','s1-vv','s1-vh','s2-index','s2-boundary','model-dz','model-sigma']) {
    await expect(page.getByTestId(`slot-${slot}`).getByText('AWAITING')).toBeVisible();
  }

  await page.getByTestId('transect-FRF-950').click();
  await expect(page.getByTestId('cross-section')).toContainText('FRF y = 950 m (FRF-950)');
  await expect(page.getByTestId('cross-section')).toContainText('REAL · VERIFIED');
  await expect(page.getByRole('img', {name: 'Cross-shore elevation profile for FRF y = 950 m'})).toBeVisible();
  const environment = await (await noaa).json();
  const water = environment.observations.find((item: { variable: string }) => item.variable === 'water_level');
  expect(water.station_id).toBe('8651370');
  expect(water.observed_at).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  expect(Number.isFinite(water.value)).toBe(true);
  await expect(page.getByTestId('env-panel')).toContainText('Water level');
  await expect(page.getByTestId('env-panel')).toContainText('NAVD88');
  await dz.scrollIntoViewIfNeeded();
  await page.screenshot({ path: info.outputPath('duck-2d-measured-change.png') });

  const toggle = (id: string) => page.getByTestId(`slot-${id}`).getByRole('checkbox');
  await toggle('lidar-dz').uncheck();
  for (const [slot, layer] of [
    ['lidar-elevation', 'lidar-elevation-june'],
    ['lidar-coverage', 'lidar-paired-coverage'],
    ['nisar-quality', 'nisar-quality-june'],
    ['nisar-hh-change', 'nisar-hh-change'],
    ['nisar-hv-change', 'nisar-hv-change'],
  ]) {
    await toggle(slot!).check();
    await expect.poll(() => images.has(layer!)).toBe(true);
    await toggle(slot!).uncheck();
  }
  for (const pol of ['hh', 'hv']) {
    await toggle(`nisar-${pol}`).check();
    await expect.poll(() => images.has(`nisar-${pol}-june`)).toBe(true);
  }
  await page.screenshot({ path: info.outputPath('duck-june-radar.png') });
  await page.getByRole('button', { name: 'Oct 2026' }).click();
  for (const pol of ['hh', 'hv']) {
    await expect(page.getByTestId(`slot-nisar-${pol}`)).toContainText('October 2026');
    await expect.poll(() => images.has(`nisar-${pol}-october`)).toBe(true);
  }
  await page.getByTestId('slot-nisar-hv').scrollIntoViewIfNeeded();
  await page.screenshot({ path: info.outputPath('duck-october-radar.png') });

  await toggle('nisar-hh').uncheck();
  await toggle('nisar-hv').uncheck();
  await toggle('lidar-elevation').check();
  await expect.poll(() => images.has('lidar-elevation-october')).toBe(true);
  const darkStyle = page.waitForResponse((r) => r.url().endsWith('/styles/dark') && r.ok());
  await page.getByTestId('basemap-select').selectOption('dark');
  await darkStyle;
  await page.getByRole('combobox', { name: '3D elevation DEM source' }).selectOption('lidar-dem-october');
  await page.getByTestId('mode-3d').click();
  await expect(page.locator('.map-hud-top-left')).toContainText('USACE LiDAR ~1 m');
  await expect.poll(() => images.has('lidar-dem-october'), { timeout: 18_000 }).toBe(true);
  await expect.poll(zoom).toBeGreaterThan(15);
  await expect(page.getByRole('slider', { name: 'Camera tilt degrees' })).toHaveValue('58');
  await page.getByRole('slider', { name: '3D vertical exaggeration' }).fill('2');
  await expect(page.locator('.map-hud-top-left')).toContainText('2× vert');
  await page.getByTestId('slot-lidar-elevation').scrollIntoViewIfNeeded();
  await page.screenshot({ path: info.outputPath('duck-3d-lidar.png') });
  expect(failures).toEqual([]);
  expect(errors).toEqual([]);
});
