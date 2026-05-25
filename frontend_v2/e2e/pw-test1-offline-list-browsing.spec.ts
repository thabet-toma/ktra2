import { test, expect } from '@playwright/test';
import { setOffline } from './pw-offline-test-utils';

test.describe('P5-A: Offline list browsing', () => {
  test('offline banner appears when network is disconnected', async ({ page }) => {
    await page.goto('/');
    await setOffline(page, true);
    await page.waitForTimeout(500);

    const banner = page.locator('text=بدون اتصال');
    await expect(banner).toBeVisible();
  });

  test('offline.html fallback works for navigation when offline', async ({ page }) => {
    await setOffline(page, true);
    await page.goto('/some-unknown-path');
    await page.waitForTimeout(500);
    const bodyText = await page.locator('body').innerText();
    expect(bodyText).toContain('بدون اتصال');
  });
});
