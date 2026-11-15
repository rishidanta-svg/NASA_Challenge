import { expect, test } from '@playwright/test';

test('Guided Tour walks cleanly through all 5 interactive investigation steps and headline results', async ({ page }) => {
  await page.goto('/');

  await page.getByRole('button', { name: 'Guided Tour', exact: true }).click();
  await expect(page.getByText('Step 1 of 5')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'What happened at Duck, North Carolina?' })).toBeVisible();

  await page.getByRole('button', { name: 'Next →' }).click();
  await expect(page.getByText('Step 2 of 5')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Can radar detect changes invisible to ordinary photographs?' })).toBeVisible();
  await page.getByRole('button', { name: /October 2026/ }).click();
  await page.getByRole('button', { name: 'ΔHH change', exact: true }).click();
  await expect(page.getByLabel('Active map layer legend')).toBeVisible();

  await page.getByRole('button', { name: 'Next →' }).click();
  await expect(page.getByText('Step 3 of 5')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Why do two satellites disagree?' })).toBeVisible();
  await expect(page.getByText('76 of 168 matched cells')).toBeVisible();
  await expect(page.getByRole('slider', { name: 'Survey comparison divider' })).toBeVisible();

  await page.getByRole('button', { name: 'Next →' }).click();
  await expect(page.getByText('Step 4 of 5')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'What actually happened to the beach?' })).toBeVisible();
  await expect(page.getByText('−0.268 m')).toBeVisible();
  await expect(page.getByText('17,654')).toBeVisible();
  await expect(page.getByTestId('cross-section')).toBeVisible();

  await page.getByRole('button', { name: 'Next →' }).click();
  await expect(page.getByText('Step 5 of 5')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'What if the waterline moves because the tide changes?' })).toBeVisible();
  await page.getByRole('button', { name: 'Before · Raw NDWI waterline' }).click();
  await expect(page.getByText('Raw NDWI waterline').first()).toBeVisible();
  await page.getByRole('button', { name: 'After · Tide-corrected waterline' }).click();
  await expect(page.getByText('49.7% LOWER RMSE')).toBeVisible();
  await expect(page.getByText('7.42 m → 3.73 m')).toBeVisible();
  await expect(page.getByText("Don't just detect change. Verify it.")).toBeVisible();

  await page.getByRole('button', { name: 'Restart Tour' }).click();
  await expect(page.getByText('Step 1 of 5')).toBeVisible();

  await page.getByRole('tab', { name: /Breakthrough/ }).click();
  await expect(page.getByText('Step 5 of 5')).toBeVisible();
  await page.getByRole('button', { name: 'Explore Freely' }).click();
  await expect(page.getByRole('complementary')).toHaveCount(0);

  await page.getByRole('button', { name: 'Findings', exact: true }).click();
  await expect(page.getByText('Result A · Shoreline Accuracy (Sentinel-2)')).toBeVisible();
  await expect(page.getByText('Result B · Physical Coastal Change (USACE LiDAR)')).toBeVisible();
  await expect(page.getByText('~11,684 m²')).toBeVisible();
});
