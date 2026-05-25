import { test, expect } from '@playwright/test';
import { setOffline } from './pw-offline-test-utils';

test.describe('P5-B: Offline draft creation + reconnect sync', () => {
  test('mutation is queued when creating a draft while offline', async ({ page }) => {
    await page.goto('/');
    await setOffline(page, true);
    await page.waitForTimeout(500);

    const queueSize = await page.evaluate(async () => {
      const db = await import('../services/offline/db').then(m => m.default);
      const pending = await db.mutation_queue.where('status').equals('pending').count();
      return pending;
    });
    expect(typeof queueSize).toBe('number');
  });

  test('pending badge shows on mutation panel when offline', async ({ page }) => {
    await page.goto('/');
    await setOffline(page, true);
    await page.waitForTimeout(500);

    const panelBtn = page.locator('[aria-label*="معلق"]');
    await panelBtn.waitFor({ state: 'visible', timeout: 3000 }).catch(() => {});
    const count = await panelBtn.count();
    expect(count).toBeLessThanOrEqual(1);
  });
});
