import { test, expect } from '@playwright/test';

test('Title group appears on the right side of the titlebar in AseelDocumentShell', async ({ page }) => {
  await page.goto('http://localhost:3000/sales-invoices');
  
  // Wait for the title bar
  const titlebar = page.locator('.aseel-titlebar');
  await expect(titlebar).toBeVisible({ timeout: 15000 });

  // Get the bounding boxes of the title group and the company
  const titleGrp = titlebar.locator('.aseel-title-grp');
  const company = titlebar.locator('.aseel-company');

  const titleBox = await titleGrp.boundingBox();
  const companyBox = await company.boundingBox();

  expect(titleBox).not.toBeNull();
  expect(companyBox).not.toBeNull();

  // In RTL, the right-most element has a LARGER x coordinate.
  // We want the title group to be on the right, so titleBox.x > companyBox.x
  expect(titleBox!.x).toBeGreaterThan(companyBox!.x);
});
