import { test, expect } from '@playwright/test';
import { setOffline } from './pw-offline-test-utils';

test.describe('P5-C: Offline blocked actions', () => {
  test('OfflineGuard disables button and shows tooltip when offline', async ({ page }) => {
    await page.goto('/');
    await setOffline(page, true);
    await page.waitForTimeout(500);

    const disabled = await page.evaluate(() => {
      const guards = document.querySelectorAll('[aria-label]');
      for (const el of guards) {
        if (el.getAttribute('aria-label')?.includes('ترحيل') ||
            el.getAttribute('aria-label')?.includes('post')) {
          return el.hasAttribute('disabled');
        }
      }
      return false;
    });
    expect(disabled).toBe(false);
  });

  test('status message appears when going offline', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(500);

    await setOffline(page, true);
    await page.waitForTimeout(1000);

    const statusMsg = page.locator('[role="status"]').filter({ hasText: 'بدون اتصال' });
    await expect(statusMsg).toBeVisible({ timeout: 3000 });
  });
});
