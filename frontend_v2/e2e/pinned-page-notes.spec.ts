import { test, expect } from '@playwright/test';
import type { Page, Route } from '@playwright/test';

/**
 * «تثبيت على الصفحة» — الملاحظة المثبّتة تظهر بالأصفر أعلى الصفحة تلقائياً،
 * مفتاحها مسار الصفحة وحده (لا query)، و«منجز» يُخفيها، والطيّ يُحفظ لكل صفحة.
 * الخادم مُحاكى: نداء `customer-notes/` يُرَدّ من مصفوفة في الذاكرة.
 */

interface MockNote {
  id: number;
  title: string;
  body: string;
  is_done: boolean;
  is_pinned: boolean;
  priority: string;
  created_by_name: string;
  created_at: string;
  target_type: string;
  target_id: string;
}

const signIn = async (page: Page, notes: MockNote[], requests: string[]) => {
  await page.addInitScript(() => {
    localStorage.setItem('token', 'pin-e2e-token');
    localStorage.setItem('userId', 'pin-e2e-user');
    localStorage.setItem('tenantId', '1');
  });

  await page.route('**/*', async (route: Route) => {
    const url = new URL(route.request().url());
    if (url.port !== '8000' && !url.pathname.startsWith('/api/')) {
      await route.continue();
      return;
    }
    const json = (body: unknown) => route.fulfill({
      contentType: 'application/json', body: JSON.stringify(body),
    });
    if (url.pathname.endsWith('/hr/users/pin-e2e-user/')) {
      await json({
        id: 'pin-e2e-user', name: 'Pin E2E Tester', role: 'manager',
        email: 'pin@example.test', employmentStatus: 'active', isApproved: true, isEmailVerified: true,
      });
      return;
    }
    if (url.pathname.includes('tenants/companies/my-companies/')) {
      await json([{
        role: 'owner', isDefault: true,
        tenant: { TenantID: 1, Name: 'شركة الاختبار', plan: 'pro', isActive: true },
      }]);
      return;
    }
    if (url.pathname.includes('/mapper/activityStatus/')) {
      await json({ isCurrentlyActive: true });
      return;
    }
    const patch = /customer-notes\/(\d+)\/$/.exec(url.pathname);
    if (patch && route.request().method() === 'PATCH') {
      const note = notes.find((n) => n.id === Number(patch[1]))!;
      Object.assign(note, route.request().postDataJSON());
      await json(note);
      return;
    }
    if (url.pathname.endsWith('/customer-notes/') && route.request().method() === 'GET') {
      requests.push(url.search);
      const targetId = url.searchParams.get('target_id');
      await json(notes.filter((n) => n.target_type === 'page' && n.target_id === targetId));
      return;
    }
    await json([]);
  });
};

const note = (over: Partial<MockNote>): MockNote => ({
  id: 1, title: 'راجع الفواتير المعلّقة', body: 'قبل إقفال الشهر', is_done: false,
  is_pinned: true, priority: 'normal', created_by_name: 'سامر', created_at: '2026-10-01T09:00:00Z',
  target_type: 'page', target_id: '/dashboard', ...over,
});

test('الملاحظة المثبّتة تظهر بالأصفر أعلى الصفحة، والمفتوحة غير المثبّتة تُعدّ في الشارة فقط', async ({ page }) => {
  const requests: string[] = [];
  await signIn(page, [
    note({ id: 1 }),
    note({ id: 2, title: 'غير مثبّتة', is_pinned: false }),
    note({ id: 3, title: 'منجزة', is_done: true }),
  ], requests);
  await page.goto('/dashboard?tab=x');
  const banner = page.getByRole('region', { name: 'ملاحظات مثبّتة على الصفحة' });
  await expect(banner).toBeVisible({ timeout: 20000 });
  await expect(banner).toContainText('راجع الفواتير المعلّقة');
  await expect(banner).not.toContainText('غير مثبّتة');
  await expect(banner).not.toContainText('منجزة');
  await expect(banner).toHaveClass(/bg-amber-50/);
  await expect(page.getByTestId('page-notes-count')).toHaveText('2');  // المفتاح المسار وحده: لا طلب يحمل `?tab=x`، ولا طلب `pinned=1` ثانياً للشريط
  // (الطلبات المتكرّرة من StrictMode في التطوير وتحميل الشركة، لا من تعدّد المصادر).
  expect(requests.length).toBeGreaterThan(0);
  for (const search of requests) {
    const params = new URLSearchParams(search);
    expect(params.get('target_id')).toBe('/dashboard');
    expect(params.has('pinned')).toBe(false);
  }
});

test('«منجز» يُخفي الشريط، والطيّ يُحفظ لهذا المستخدم ولهذه الصفحة', async ({ page }) => {
  const requests: string[] = [];
  await signIn(page, [note({ id: 1 }), note({ id: 2, title: 'الثانية' })], requests);
  await page.goto('/dashboard');
  const banner = page.getByRole('region', { name: 'ملاحظات مثبّتة على الصفحة' });
  await expect(banner).toBeVisible({ timeout: 20000 });

  await banner.getByRole('button', { name: 'طيّ الملاحظات المثبّتة' }).click();
  await expect(banner).toContainText('ملاحظتان مثبّتتان على هذه الصفحة');
  expect(await page.evaluate(
    () => localStorage.getItem('ktra.pinnedNotes.collapsed.pin-e2e-user./dashboard'),
  )).toBe('1');
  await page.reload();
  await expect(banner).toContainText('ملاحظتان مثبّتتان على هذه الصفحة', { timeout: 20000 });

  await banner.getByRole('button', { name: 'توسيع الملاحظات المثبّتة' }).click();
  await banner.getByRole('button', { name: 'منجز' }).first().click();
  await expect(banner).not.toContainText('راجع الفواتير المعلّقة');
  await expect(banner).toContainText('الثانية');
});
