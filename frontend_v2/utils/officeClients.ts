import type { WorkspaceCompany } from '../types/accountant';

/**
 * «شركاتي المرتبطة» — قائمةُ بوابة المحاسب وحدها: الشركاتُ التي ربطها المحاسب
 * بشركائه على المنصّة (`AccountantEngagement`). نصفُها القديم من سجلّ المكتب
 * المحلي حُذف مع طبقة «المكتب القديمة» في #291؛ فلم يبقَ مصدرٌ ثانٍ يُدمَج،
 * والقائمةُ صارت تعرض ما يعيده الخادم لا أكثر.
 *
 * دوالٌّ صرفة (لا React ولا شبكة) كي تُختبر وحدها.
 */

/**
 * سببُ إغلاق الملف لا «مغلق» وحدها: ارتباطٌ نشط على شركة لم تفعّل وحدة البوابة
 * ليس بانتظار موافقة أحد — قول ذلك يمنع المحاسب من انتظار ردٍّ لن يأتي.
 */
export function platformHint(company: WorkspaceCompany): string {
  if (!company.accessible) {
    return company.status === 'active'
      ? 'الشركة لم تفعّل وحدة بوابة المحاسب — دفاترها لا تُفتح حتى تفعّلها.'
      : 'بانتظار موافقة الشركة — الملف لا يُفتح قبلها.';
  }
  return company.last_period
    ? `آخر فترة مُراجَعة: ${company.last_period.period_from} → ${company.last_period.period_to}`
    : 'لم تُراجَع أي فترة بعد';
}

/**
 * تصفية محلية فوق البحث، والمفتوحُ أوّلاً ثم البقيّة — ترتيبُ القائمة القديم
 * نفسه (المفتوح قبل المعلَّق) حفاظاً على أن أول ما يقع عليه النظر هو ما يُعمل
 * عليه. وداخل كل فريق ترتيبٌ أبجدي عربي.
 */
export function visibleWorkspaceCompanies(
  companies: WorkspaceCompany[],
  search: string,
): WorkspaceCompany[] {
  const needle = search.trim().toLowerCase();
  const matched = needle
    ? companies.filter((company) => company.company_name.toLowerCase().includes(needle))
    : [...companies];
  return matched.sort((left, right) => {
    if (left.accessible !== right.accessible) return left.accessible ? -1 : 1;
    return left.company_name.localeCompare(right.company_name, 'ar');
  });
}
