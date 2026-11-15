import { expect, test } from '@playwright/test';

test('shows real optical corrections, measured profiles, and radar direction flags', async ({ page }) => {
  const geojson = new Set<string>();
  page.on('response', (response) => {
    const url = new URL(response.url());
    if (response.ok() && url.pathname.startsWith('/api/boundaries/')) geojson.add(url.pathname);
  });
  await page.goto('/');
  const panel = page.getByTestId('coastal-evidence');
  await expect(panel).toContainText('RMSE 3.73 m');
  await expect(panel).toContainText('RMSE 4.80 m');
  await page.getByTestId('transect-FRF-950').click();
  await panel.getByText('Sentinel‑2 · 2026-06-18 16:03:02 UTC', { exact: true }).click();
  await expect(panel.getByTestId('tide-2026-06')).toContainText('94.63 m');
  await expect(panel).toContainText('Slope sensitivity');
  await expect(page.getByTestId('cross-section')).toContainText('Oct waterline');
  await expect(panel.getByText('Experimental wave setup ·')).toHaveCount(0);

  const toggle = (slot: string) => page.getByTestId(`slot-${slot}`).getByRole('checkbox');
  for (const [slot, file] of [
    ['physics-s2-ndwi', 'physics-s2-ndwi-june'],
    ['physics-s2-tide', 'physics-s2-tide-june'],
    ['physics-s2-mndwi', 'physics-s2-mndwi-june'],
    ['physics-s2-setup', 'physics-s2-setup-june'],
    ['radar-disagreement', 'radar-disagreement'],
  ]) {
    await toggle(slot!).check();
    await expect.poll(() => geojson.has(`/api/boundaries/${file}.geojson`)).toBe(true);
  }
  await expect(panel).toContainText('RMSE 2.19 m');
  await panel.getByText('Radar disagreement · 76 / 168 strict cells').click();
  await expect(panel).toContainText('671 / 1310 across shared radar coverage');
  await page.getByRole('button', { name: 'Jun 30 S1' }).click();
  await expect(toggle('physics-s2-tide')).toBeDisabled();
  await expect(page.getByTestId('slot-physics-s2-tide')).toContainText('No qualified layer on the selected acquisition date');
  await page.getByRole('button', { name: 'Oct 2026' }).click();
  await expect.poll(() => geojson.has('/api/boundaries/physics-s2-tide-october.geojson')).toBe(true);
});
