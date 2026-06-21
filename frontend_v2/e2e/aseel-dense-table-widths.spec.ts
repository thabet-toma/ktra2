import { test, expect } from '@playwright/test';

test('AseelDenseTable saves column width to localStorage on resize', async ({ page }) => {
  // We navigate to a page that has AseelDenseTable (e.g., partners page)
  await page.goto('http://localhost:3000/partners');
  
  // Wait for the table to load
  const table = page.locator('.aseel-dense-table');
  await expect(table).toBeVisible({ timeout: 15000 });

  // Find a resizable column th
  const resizableHeader = page.locator('.aseel-dense-table th:has(span[title="اسحب لتغيير عرض العمود"])').first();
  await expect(resizableHeader).toBeVisible();

  // Get initial width
  const initialBox = await resizableHeader.boundingBox();
  expect(initialBox).not.toBeNull();
  
  const handle = resizableHeader.locator('span[title="اسحب لتغيير عرض العمود"]');
  const handleBox = await handle.boundingBox();
  expect(handleBox).not.toBeNull();

  // Drag the handle to resize
  await page.mouse.move(handleBox!.x + handleBox!.width / 2, handleBox!.y + handleBox!.height / 2);
  await page.mouse.down();
  // move mouse right by 50px
  await page.mouse.move(handleBox!.x + 50, handleBox!.y + handleBox!.height / 2);
  await page.mouse.up();

  // Check new width
  const newBox = await resizableHeader.boundingBox();
  expect(newBox!.width).not.toEqual(initialBox!.width);

  // Reload page
  await page.reload();
  await expect(table).toBeVisible({ timeout: 15000 });

  // Check if width is preserved
  const reloadedHeader = page.locator('.aseel-dense-table th:has(span[title="اسحب لتغيير عرض العمود"])').first();
  const reloadedBox = await reloadedHeader.boundingBox();
  
  // The new width should be within 10 pixels of the resized width due to layout shifting
  expect(Math.abs(reloadedBox!.width - newBox!.width)).toBeLessThan(10);
});
