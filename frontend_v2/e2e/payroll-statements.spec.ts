import { test, expect } from '@playwright/test';

/**
 * THA-126 — كشف الساعات اليومي على الشاشة العامّة، وتصدير Excel.
 *
 * ثلاثة وعود لا يُثبتها اختبار وحدة:
 *  1. **يُفتح على الشهر الحالي** — لا على «هذه السنة» ثم على رسالة خطأ من حارس
 *     الـ31 يوماً. الطلب الأول نفسه هو الدليل.
 *  2. **الشبكة تُرسم**: عمودٌ لكل يوم، وخانة الغياب «غ» في يومها.
 *  3. **زرّ Excel يُنزِّل ملفاً فعلاً** — و`tsc` لا يفحص خصائص JSX في هذا
 *     المستودع، فظهور الزرّ وعمله هو الدليل الوحيد على أن الشاشة تركّبه.
 *
 * الشبكة موقوفة كما في `did-you-know.spec.ts` — لا خادم ولا قاعدة بيانات
 * (MySQL متوقّفة على هذا الجهاز).
 */

const MONTH_START = (() => {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`;
})();

const DAYS = 3;

const catalogPayload = {
  categories: [{
    key: 'hr',
    label: 'الموارد البشرية',
    reports: [{
      key: 'timesheet-daily',
      title: 'كشف الساعات اليومي',
      description: 'صفٌّ لكل موظف وعمودٌ لكل يوم.',
      permission: 'hr.payroll.view',
      screen_path: null,
      row_link: null,
      filters: [
        { key: 'from', label: 'من تاريخ', kind: 'date', options: [], default: 'month' },
        { key: 'to', label: 'إلى تاريخ', kind: 'date', options: [], default: 'month' },
      ],
      columns: [
        { key: 'employee', header: 'الموظف', kind: 'text', total: false, width: '150px' },
        { key: 'total_hours', header: 'مجموع الساعات', kind: 'number', total: true, width: '100px' },
      ],
    }],
  }],
};

const runPayload = {
  key: 'timesheet-daily',
  title: 'كشف الساعات اليومي',
  category: 'hr',
  description: '',
  row_link: null,
  columns: [
    { key: 'employee', header: 'الموظف', kind: 'text', total: false, width: '150px' },
    ...Array.from({ length: DAYS }, (_, i) => ({
      key: `d${i + 1}`, header: `${i + 1} سب`, kind: 'text', total: false, width: '58px',
    })),
    { key: 'total_hours', header: 'مجموع الساعات', kind: 'number', total: true, width: '100px' },
    { key: 'absence_days', header: 'أيام الغياب', kind: 'number', total: true, width: '90px' },
  ],
  rows: [
    { id: 1, employee: 'عمر', d1: '8', d2: '7.5', d3: '', total_hours: '15.5', absence_days: '0' },
    { id: 2, employee: 'سامي', d1: '', d2: 'غ', d3: 'ت 30', total_hours: '0', absence_days: '1' },
  ],
  totals: { total_hours: '15.5', absence_days: '1' },
  total_rows: 2,
  truncated: false,
  generated_at: '2026-08-20T10:00:00',
  generated_by: 'ثابت',
};

/** كل طلبات التشغيل التي وصلت الخادم — للتحقّق من نطاق الفتح الأول. */
const runQueries: string[] = [];

const asPayrollManager = async (page: import('@playwright/test').Page) => {
  runQueries.length = 0;
  await page.addInitScript(() => {
    localStorage.setItem('token', 'ts-token');
    localStorage.setItem('userId', 'ts-user');
    localStorage.setItem('tenantId', '1');
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === '8000' || url.pathname.startsWith('/api/');
    if (!isApi) return route.continue();
    const json = (body: unknown) => route.fulfill({
      contentType: 'application/json', body: JSON.stringify(body),
    });

    if (url.pathname.endsWith('/hr/users/ts-user/')) {
      return json({
        id: 'ts-user', name: 'ثابت', role: 'manager', email: 'ts@example.test',
        employmentStatus: 'active', isApproved: true, isEmailVerified: true,
      });
    }
    if (url.pathname.endsWith('/tenants/companies/my-companies/')) {
      return json([{
        id: 1,
        tenant: {
          TenantID: 1, CompanyName: 'شركة الكشوف', SubscriptionPlan: 'basic',
          Status: 'active', CreatedAt: '2026-01-01T00:00:00Z', import_enabled: false,
        },
        role: 'manager', is_default: true,
        created_at: '2026-01-01T00:00:00Z', can_access_import: false,
      }]);
    }
    if (url.pathname.endsWith('/permissions/me/')) {
      return json({
        role: 'manager', is_manager: true,
        permissions: ['hr.payroll.view'], modules: {}, ui_mode: 'advanced',
      });
    }
    if (url.pathname.includes('/reports/timesheet-daily/')) {
      runQueries.push(url.search);
      return json(runPayload);
    }
    if (url.pathname.endsWith('/reports/')) return json(catalogPayload);
    return json([]);
  });
};

test.setTimeout(120000);

test('كشف الساعات يُفتح على الشهر الحالي، وشبكته تُرسم، وExcel يُنزَّل', async ({ page }) => {
  await asPayrollManager(page);
  await page.setViewportSize({ width: 1600, height: 900 });
  await page.goto('/reports/timesheet-daily');

  // 1) الفتح على الشهر الحالي — الطلب الأول هو الدليل، لا الحقل المعروض.
  await expect(page.getByText('كشف الساعات اليومي').first()).toBeVisible({ timeout: 20000 });
  await expect.poll(() => runQueries.length, { timeout: 20000 }).toBeGreaterThan(0);
  expect(decodeURIComponent(runQueries[0])).toContain(`from=${MONTH_START}`);

  // 2) الشبكة: عمود لكل يوم، والغياب مُعلَّم في يومه.
  await expect(page.getByRole('columnheader', { name: '2 سب' })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'غ', exact: true })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'ت 30' })).toBeVisible();

  // 3) زرّ Excel موجود ويُنزِّل ملفاً — ولا شيء غير هذا يُثبت أن الشاشة تركّبه.
  // المهلة سخيّة عمداً: المكتبة تُستورَد ديناميكياً، وخادم التطوير يُحزّمها عند
  // أول طلب لها (بضع عشرات من الثواني على بارد). في البناء الإنتاجي هي حزمة
  // جاهزة أصلاً — انظر `dist/assets/exceljs.min-*.js`.
  const download = page.waitForEvent('download', { timeout: 90000 });
  await page.getByRole('button', { name: 'تصدير Excel' }).click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/\.xlsx$/);
});
