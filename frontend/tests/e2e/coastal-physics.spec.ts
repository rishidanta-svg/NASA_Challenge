import {expect,test} from '@playwright/test';

test('current findings separate optical physics, measured change and NISAR experiments',async({page})=>{
  await page.goto('/');
  await page.getByRole('button',{name:'Findings',exact:true}).click();
  await expect(page.getByRole('heading',{name:'What the observations show'})).toBeVisible();
  await expect(page.getByText('Tide-adjusted waterline',{exact:true})).toBeVisible();
  await page.getByText('Waterline validation against LiDAR',{exact:true}).click();
  await expect(page.getByText('3.73 m',{exact:true})).toBeVisible();
  await expect(page.getByText('4.80 m',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'NISAR experiments',exact:true}).click();
  await expect(page.getByText('0.2549 m',{exact:true})).toBeVisible();
  await expect(page.getByText('0.2582 m',{exact:true})).toBeVisible();
  await expect(page.getByText('Adding NISAR did not improve this test',{exact:true})).toBeVisible();
  await page.getByText('Can NISAR identify the waterline?',{exact:true}).click();
  await expect(page.getByText('june: 39 candidate rows · waterline comparison failed.',{exact:true})).toBeVisible();
  const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'Download results and evidence'}).click();
  expect((await download).suggestedFilename()).toContain('current-evidence.json');
});
