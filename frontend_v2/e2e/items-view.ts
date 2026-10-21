import type { Page } from '@playwright/test';

/**
 * تبديلُ شاشة المنتجات إلى العرض الجدولي — الشجرة صارت الافتراضية (B3).
 *
 * كلُّ اختبارٍ يخصّ الجدول كان يُبدّله بنسخته: نقرةٌ عارية في ملفّ، ونقرةٌ
 * تنتظر الجلب في آخر. والنقرةُ وحدها لا تكفي: تبديلُ الوضع يعيد جلب القائمة
 * بعد `debounce 250ms`، فيصل الردُّ بعد التفاعل التالي ويمحو ما عدّله (محاكي
 * يردّ الصفوف الثابتة يجعل السباق يظهر في كل تشغيلٍ لا أحياناً). الانتظارُ هنا
 * هو ما يجعل بداية كل اختبار محدَّدة، لا سرعةَ الجهاز.
 *
 * `networkidle` قبل النقرة كي لا يلتقط الانتظارُ جلبَ الشجرة الأولى (الافتراضي)
 * فيمرّ قبل أن يبدأ جلبُ الجدول.
 */
export async function switchItemsToTable(page: Page): Promise<void> {
  await page.waitForLoadState('networkidle');
  const refetch = page.waitForResponse(
    (r) => r.url().includes('/inventory/products/') && r.request().method() === 'GET',
  );
  await page.getByTitle('عرض كجدول').click();
  await refetch;
}
