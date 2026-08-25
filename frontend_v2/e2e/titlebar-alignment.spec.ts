import { test, expect } from '@playwright/test';

test('Title group appears on the right side of the titlebar in KitDocumentShell', async ({ page }) => {
  await page.goto('/ui-kit');
  
  // Wait for the title bar
  const titlebar = page.locator('.ktra-titlebar');
  await expect(titlebar).toBeVisible({ timeout: 15000 });

  // Get the bounding boxes of the title group and the company
  const titleGrp = titlebar.locator('.ktra-title-grp');
  const company = titlebar.locator('.ktra-company');

  const titleBox = await titleGrp.boundingBox();
  const companyBox = await company.boundingBox();

  expect(titleBox).not.toBeNull();
  expect(companyBox).not.toBeNull();

  // In RTL, the right-most element has a LARGER x coordinate.
  // We want the title group to be on the right, so titleBox.x > companyBox.x
  expect(titleBox!.x).toBeGreaterThan(companyBox!.x);
});
