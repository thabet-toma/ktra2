import { test, expect } from '@playwright/test';
import {
  installAuthenticatedOfflineApp,
  openAuthenticatedOfflineApp,
  setOffline,
} from './pw-offline-test-utils';

test.use({ serviceWorkers: 'block' });

test.describe('P5-A: Offline list browsing', () => {
  test.beforeEach(async ({ page }) => {
    await installAuthenticatedOfflineApp(page);
  });

  test('offline banner becomes visible after losing connection', async ({ page }) => {
    await openAuthenticatedOfflineApp(page);
    await setOffline(page, true);
    // OfflineBanner is wired in App.tsx and only renders when status.online is
    // false. Allow a brief tick for the navigator event to propagate.
    const banner = page.getByRole('status').filter({ hasText: 'بدون اتصال' }).first();
    await expect(banner).toBeVisible({ timeout: 5000 });
  });

  test('retry button on the banner exists and is reachable by keyboard', async ({ page }) => {
    await openAuthenticatedOfflineApp(page);
    await setOffline(page, true);
    const retry = page.getByRole('button', { name: /أعِد المحاولة/ });
    await expect(retry).toBeVisible({ timeout: 5000 });
    await retry.focus();
    await expect(retry).toBeFocused();
  });
});
