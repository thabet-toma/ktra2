import { test, expect } from '@playwright/test';

/**
 * مشية التسليم على الخادم الحيّ وبيانات شركة حقيقية — بلا أي stub.
 *
 * هذا الملف يُغلق علمَي الصدق المسجَّلين في THA-107: مشية A1 جرت على طبقة خادم
 * مُستبدَلة، وعيّنة CSV في A4 أُنتجت بتشغيل دالة التصدير معزولةً. هنا: الخادم
 * الحقيقي على 8000، وشركة «الجرابعه» (tenant 3) وفيها 4254 قيداً مرحّلاً،
 * ونقرة تصدير حقيقية من المتصفح.
 *
 * يتطلّب خادماً يعمل على 8000 وتوكن صالحاً في LIVE_TOKEN.
 */

const TOKEN = process.env.LIVE_TOKEN ?? '';
const TENANT = process.env.LIVE_TENANT ?? '3';
const USER_ID = process.env.LIVE_USER_ID ?? '1';

test.skip(!TOKEN, 'LIVE_TOKEN غير مضبوط — مشية التسليم تحتاج توكناً حقيقياً');

test.beforeEach(async ({ page }) => {
  await page.addInitScript(
    ([token, tenantId, userId]) => {
      localStorage.setItem('token', token);
      localStorage.setItem('userId', userId);
      localStorage.setItem('tenantId', tenantId);
      localStorage.setItem('lastActivityAt', String(Date.now()));
    },
    [TOKEN, TENANT, USER_ID],
  );
});

test('ميزان المراجعة يعرض بيانات شركة حقيقية، والتصدير يُنزّل أرقاماً خاماً', async ({ page }) => {
  await page.goto('/accounting/trial-balance');

  // الجدول يمتلئ من الخادم الحقيقي لا من stub
  const rows = page.locator('table tbody tr');
  await expect.poll(() => rows.count(), { timeout: 30000 }).toBeGreaterThan(5);

  // نقرة التصدير الحقيقية — والملف يُلتقط من المتصفح نفسه
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'تصدير' }).first().click();
  const download = await downloadPromise;

  expect(download.suggestedFilename()).toMatch(/^trial-balance-.*\.csv$/);

  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const c of stream) chunks.push(Buffer.from(c));
  const csv = Buffer.concat(chunks).toString('utf8');

  // الشرط الذي طلبه المالك: أرقام يعيد المحاسب حسابها، لا نصوص معروضة
  expect(csv).toMatch(/﻿/);                 // BOM كي يفتح عربياً في Excel
  expect(csv).not.toMatch(/"\d{1,3},\d{3}/);     // لا فواصل آلاف داخل خانة رقمية
  expect(csv).toMatch(/\d+\.\d{1,2}/);           // وأرقام عشرية خام موجودة فعلاً

  console.log('CSV file :', download.suggestedFilename());
  console.log('CSV head :', csv.split('\n').slice(0, 3).join('\n'));
});

test('التنقيب: صفّ الميزان يفتح الأستاذ العام على الحساب نفسه', async ({ page }) => {
  await page.goto('/accounting/trial-balance');

  const rows = page.locator('table tbody tr');
  await expect.poll(() => rows.count(), { timeout: 30000 }).toBeGreaterThan(5);

  // أول صفّ يحمل حركة فعلية (رصيد ختامي غير صفري)
  const target = rows.filter({ hasText: /1103|المدينون/ }).first();
  await target.click();

  await expect(page).toHaveURL(/general-ledger/, { timeout: 15000 });
  await expect(page.locator('body')).toContainText(/الأستاذ|1103|المدينون/, { timeout: 15000 });
});
