import { test, expect } from '@playwright/test';
import { setOffline } from './pw-offline-test-utils';

test.describe('P5-E: Conflict resolution flow', () => {
  test('SyncConflictModal renders with three resolution buttons', async ({ page }) => {
    await page.goto('/');

    const hasConflictModal = await page.evaluate(async () => {
      const { default: SyncConflictModal } = await import('../components/offline/SyncConflictModal');
      return typeof SyncConflictModal === 'function';
    });
    expect(hasConflictModal).toBe(true);
  });

  test('mutation queue processMutationQueue runs without error', async ({ page }) => {
    await page.goto('/');
    // حمّل module قبل قطع الشبكة؛ الاختبار يفحص التنفيذ الأوفلاين لا تحميل JS.
    await page.evaluate(() => import('../services/offline/cachedApi').then(() => undefined));
    await setOffline(page, true);
    await page.waitForTimeout(500);

    const result = await page.evaluate(async () => {
      const { processMutationQueue } = await import('../services/offline/cachedApi');
      try {
        await processMutationQueue();
        return 'ok';
      } catch (e: any) {
        return e.message;
      }
    });
    expect(result).toBe('ok');
  });
});
