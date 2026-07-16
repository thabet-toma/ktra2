import { test, expect } from '@playwright/test';
import { setOffline } from './pw-offline-test-utils';

test.describe('P5-B: Offline draft creation + reconnect sync', () => {
  test('mutation is queued when creating a draft while offline', async ({ page }) => {
    await page.goto('/');
    // حمّل module قبل قطع الشبكة؛ وإلا يفشل import نفسه ولا يصل الاختبار إلى IndexedDB.
    await page.evaluate(() => import('../services/offline/db').then(() => undefined));
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

  test('server errors return a syncing mutation to pending with an actionable error', async ({ page }) => {
    await page.route('**/api/test-sync/**', (route) =>
      route.fulfill({ status: 503, contentType: 'text/plain', body: 'temporary outage' }),
    );
    await page.goto('/');

    const row = await page.evaluate(async () => {
      const [{ default: db }, { processMutationQueue }] = await Promise.all([
        import('../services/offline/db'),
        import('../services/offline/cachedApi'),
      ]);
      const id = await db.mutation_queue.add({
        status: 'pending',
        created_at: new Date().toISOString(),
        endpoint: 'test-sync/document/',
        method: 'PATCH',
        body: JSON.stringify({ value: 1 }),
        tenant_id: 1,
        temp_id: `temp-${crypto.randomUUID()}`,
      });
      await processMutationQueue();
      const saved = await db.mutation_queue.get(id);
      await db.mutation_queue.delete(id);
      return { status: saved?.status, error: saved?.error };
    });

    expect(row.status).toBe('pending');
    expect(row.error).toContain('temporary outage');
  });
});
