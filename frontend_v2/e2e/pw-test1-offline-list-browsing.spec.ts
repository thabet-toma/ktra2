import { test, expect } from '@playwright/test';
import { setOffline } from './pw-offline-test-utils';

test.describe('P5-A: Offline list browsing', () => {
  test('offline banner becomes visible after losing connection', async ({ page }) => {
    await page.goto('/');
    // Wait for app shell to render before flipping the offline switch — otherwise
    // the SW may not have claimed the page yet and the banner won't mount.
    await page.waitForLoadState('networkidle').catch(() => {});
    await setOffline(page, true);
    // OfflineBanner is wired in App.tsx and only renders when status.online is
    // false. Allow a brief tick for the navigator event to propagate.
    const banner = page.locator('role=status').filter({ hasText: 'بدون اتصال' }).first();
    await expect(banner).toBeVisible({ timeout: 5000 });
  });

  test('retry button on the banner exists and is reachable by keyboard', async ({ page }) => {
    await page.goto('/');
    await setOffline(page, true);
    const retry = page.getByRole('button', { name: /أعِد المحاولة/ });
    await expect(retry).toBeVisible({ timeout: 5000 });
    await retry.focus();
    await expect(retry).toBeFocused();
  });
});
