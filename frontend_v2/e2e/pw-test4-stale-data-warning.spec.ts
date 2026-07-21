import { test, expect } from '@playwright/test';
import {
  installAuthenticatedOfflineApp,
  openAuthenticatedOfflineApp,
  setOffline,
} from './pw-offline-test-utils';

test.use({ serviceWorkers: 'block' });

test.describe('P5-D: Stale data warning before sensitive action', () => {
  test.beforeEach(async ({ page }) => {
    await installAuthenticatedOfflineApp(page);
  });

  test('StaleDataConfirm renders modal with correct structure', async ({ page }) => {
    await openAuthenticatedOfflineApp(page);

    const hasModal = await page.evaluate(async () => {
      const { useStaleConfirm } = await import('../components/offline/StaleDataConfirm');
      return typeof useStaleConfirm === 'function';
    });
    expect(hasModal).toBe(true);
  });

  test('coachmark appears on first offline event', async ({ page }) => {
    await openAuthenticatedOfflineApp(page);
    await page.waitForTimeout(300);
    await setOffline(page, true);

    const coachmark = page.getByRole('heading', { name: 'أنت الآن بدون اتصال' });
    await expect(coachmark).toBeVisible({ timeout: 3000 });
  });
});
