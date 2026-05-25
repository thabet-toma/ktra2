import { test, expect } from '@playwright/test';
import { setOffline } from './pw-offline-test-utils';

test.describe('P5-C: Posting buttons are blocked when offline', () => {
  test('OfflineGuard mounts a role=group container with the action label', async ({ page }) => {
    // Hit YearEndClose where OfflineGuard wraps «تنفيذ الإغلاق السنوي».
    await page.goto('/accounting/year-end-close');
    await page.waitForLoadState('networkidle').catch(() => {});
    await setOffline(page, true);

    const guard = page.locator('[role="group"][aria-label="تنفيذ الإغلاق السنوي"]');
    await expect(guard).toBeVisible({ timeout: 5000 });
  });

  test('offline status banner appears with role=status and Arabic text', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle').catch(() => {});
    await setOffline(page, true);
    const banner = page.locator('role=status').filter({ hasText: 'بدون اتصال' }).first();
    await expect(banner).toBeVisible({ timeout: 5000 });
  });
});
