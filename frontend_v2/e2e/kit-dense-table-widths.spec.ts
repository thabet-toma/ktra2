import { test, expect } from '@playwright/test';

test('KitDenseTable saves column width to localStorage on resize', async ({ page }) => {
  // The component story is public and deterministic; authenticated partner data is not.
  await page.goto('/ui-kit');
  
  // Wait for the table to load
  const table = page.locator('.ktra-dense-table');
  await expect(table).toBeVisible({ timeout: 15000 });

  // Find a resizable column th
  const resizableHeader = page.locator('.ktra-dense-table th:has(span[title="اسحب لتغيير عرض العمود"])').first();
  await expect(resizableHeader).toBeVisible();

  const initialWidth = await resizableHeader.evaluate((element) => (element as HTMLElement).style.width);
  
  const handle = resizableHeader.locator('span[title="اسحب لتغيير عرض العمود"]');
  // Dispatch the same document-level mouse sequence used by the component.
  await handle.dispatchEvent('mousedown', { clientX: 100, clientY: 10, button: 0 });
  await page.evaluate(() => {
    document.dispatchEvent(new MouseEvent('mousemove', { clientX: 150, clientY: 10, bubbles: true }));
    document.dispatchEvent(new MouseEvent('mouseup', { clientX: 150, clientY: 10, bubbles: true }));
  });

  await expect.poll(() => resizableHeader.evaluate((element) => (element as HTMLElement).style.width))
    .not.toBe(initialWidth);
  const resizedWidth = await resizableHeader.evaluate((element) => (element as HTMLElement).style.width);

  // Reload page
  await page.reload();
  await expect(table).toBeVisible({ timeout: 15000 });

  // Check if width is preserved
  const reloadedHeader = page.locator('.ktra-dense-table th:has(span[title="اسحب لتغيير عرض العمود"])').first();
  await expect.poll(() => reloadedHeader.evaluate((element) => (element as HTMLElement).style.width))
    .toBe(resizedWidth);
});
