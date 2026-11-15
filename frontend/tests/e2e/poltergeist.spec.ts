import { expect, test } from '@playwright/test';

test('Poltergeist keeps the map clear and reveals detail on request', async ({page}) => {
  await page.goto('/');
  await expect(page.getByRole('link',{name:'poltergeist Coastal observatory'})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Duck coastline'})).toBeVisible();
  await expect(page.getByRole('slider')).toHaveCount(0);
  await expect(page.getByRole('heading',{name:'Location Inspector'})).toHaveCount(0);
  await expect(page.locator('.maplibregl-canvas').first()).toBeVisible();
  await page.getByRole('button',{name:'Layers',exact:true}).click();
  await page.getByRole('radio',{name:/Ground level change/}).check();
  await expect(page.getByRole('img',{name:'Color scale from -2.5 to 2.5 m'})).toBeVisible();
  await page.getByRole('button',{name:'Compare',exact:true}).click();
  await expect(page.getByLabel('Left comparison survey')).toHaveValue('2026-06-18');
  await expect(page.getByLabel('Right comparison survey')).toHaveValue('2026-10-16');
  const divider=page.getByRole('slider',{name:'Survey comparison divider'});
  await expect(divider).toHaveAttribute('aria-valuenow','50');
  await divider.focus(); await page.keyboard.press('ArrowRight');
  await expect(divider).toHaveAttribute('aria-valuenow','55');
  await page.getByRole('button',{name:'Findings',exact:true}).click();
  await expect(page.getByRole('heading',{name:'What the observations show'})).toBeVisible();
  await expect(page.getByText('Tide-adjusted waterline',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'NISAR experiments',exact:true}).click();
  await expect(page.getByText('Adding NISAR did not improve this test',{exact:true})).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('complementary')).toHaveCount(0);
});
