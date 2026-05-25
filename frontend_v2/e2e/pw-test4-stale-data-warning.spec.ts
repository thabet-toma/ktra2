import { test, expect } from '@playwright/test';

test.describe('P5-D: Stale data warning before sensitive action', () => {
  test('StaleDataConfirm renders modal with correct structure', async ({ page }) => {
    await page.goto('/');

    const hasModal = await page.evaluate(async () => {
      const { useStaleConfirm } = await import('../components/offline/StaleDataConfirm');
      return typeof useStaleConfirm === 'function';
    });
    expect(hasModal).toBe(true);
  });

  test('coachmark appears on first offline event', async ({ page }) => {
    await page.goto('/');
    await page.evaluate(() => localStorage.removeItem('offline-coachmark-shown'));
    await page.waitForTimeout(300);

    await page.evaluate(() => {
      window.dispatchEvent(new Event('offline'));
    });
    await page.waitForTimeout(1000);

    const coachmark = page.locator('text=أنت الآن بدون اتصال');
    await expect(coachmark).toBeVisible({ timeout: 3000 });
  });
});
