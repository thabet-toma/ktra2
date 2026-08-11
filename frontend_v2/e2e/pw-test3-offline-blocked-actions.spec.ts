import { test, expect } from '@playwright/test';
import {
  installAuthenticatedOfflineApp,
  openAuthenticatedOfflineApp,
  setOffline,
} from './pw-offline-test-utils';

test.use({ serviceWorkers: 'block' });

test.describe('P5-C: Posting buttons are blocked when offline', () => {
  test.beforeEach(async ({ page }) => {
    await installAuthenticatedOfflineApp(page);
  });

  test('OfflineGuard mounts a role=group container with the action label', async ({ page }) => {
    // Hit YearEndClose where OfflineGuard wraps «تنفيذ الإغلاق السنوي».
    await openAuthenticatedOfflineApp(page, '/accounting/year-end-close');
    await setOffline(page, true);

    const guard = page.locator('[role="group"][aria-label="تنفيذ الإغلاق السنوي"]');
    await expect(guard).toBeVisible({ timeout: 5000 });
  });

  test('offline status banner appears with role=status and Arabic text', async ({ page }) => {
    await openAuthenticatedOfflineApp(page);
    await setOffline(page, true);
    const banner = page.getByRole('status').filter({ hasText: 'بدون اتصال' }).first();
    await expect(banner).toBeVisible({ timeout: 5000 });
  });
});
