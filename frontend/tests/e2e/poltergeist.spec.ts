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
  await expect(page.getByLabel('Left comparison survey')).toHaveValue('2026-06-19');
  await expect(page.getByLabel('Right comparison survey')).toHaveValue('2026-10-16');
  const divider=page.getByRole('slider',{name:'Survey comparison divider'});
  await expect(divider).toHaveAttribute('aria-valuenow','50');
  await divider.focus(); await page.keyboard.press('ArrowRight');
  await expect(divider).toHaveAttribute('aria-valuenow','55');
  await page.getByRole('button',{name:'Findings',exact:true}).click();
  await expect(page.getByRole('heading',{name:'What the observations show'})).toBeVisible();
  await expect(page.getByText('A data pairing needs review',{exact:true})).toBeVisible();
  await expect(page.getByRole('table')).toHaveCount(0); // Details are collapsed by default.
  await page.getByText('When were these observations taken?',{exact:true}).click();
  await expect(page.getByText('+287.4 h',{exact:true}).first()).toBeVisible();
  const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'Download results and evidence'}).click();
  expect((await download).suggestedFilename()).toContain('evidence.json');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('complementary')).toHaveCount(0);
});
