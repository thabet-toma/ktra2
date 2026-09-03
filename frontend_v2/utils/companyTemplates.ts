/**
 * ISSUE #50 — سِجلّ قوالب الشركة (مرآة `tenants/company_templates.py`).
 *
 * منتقي القالب في شاشة إنشاء الشركة يعرض بطاقة لكل قيمة هنا: أيقونة واسم
 * ووصف سطر يقول ماذا يُفعَّل وماذا يُخفى (قرار 13). المفتاح `key` هو نفسه ما
 * يُرسَل في جسد `POST /api/tenants/companies/` (`template`)، و`general` هو
 * الافتراضي — بلا قناع وبلا تغيير سلوك (قرار 16).
 */

export type CompanyTemplateKey = 'general' | 'accounting_firm' | 'client_book';

export type CompanyTemplate = {
  key: CompanyTemplateKey;
  name: string;
  /** اسم أيقونة lucide-react */
  icon: string;
  description: string;
};

export const DEFAULT_COMPANY_TEMPLATE: CompanyTemplateKey = 'general';

// ISSUE #81: قالب الدفتر الذي يفتحه مكتب المحاسبة لزبونه من `ClientBooksPanel`
// — ليس الافتراضي العام (`DEFAULT_COMPANY_TEMPLATE`) الذي يبقى `general` لكل
// مسار إنشاء شركة آخر.
export const DEFAULT_CLIENT_BOOK_TEMPLATE: CompanyTemplateKey = 'client_book';

export const COMPANY_TEMPLATES: readonly CompanyTemplate[] = [
  {
    key: 'general',
    name: 'عام / تجاري',
    icon: 'Building2',
    description: 'دليل حسابات تجاري كامل — مخزون واستيراد وكل أنواع المستندات.',
  },
  {
    key: 'accounting_firm',
    name: 'مكتب محاسبة',
    icon: 'Calculator',
    description: 'أتعاب مهنية بلا مخزون ولا استيراد — سبعة أنواع مستندات فقط.',
  },
  {
    key: 'client_book',
    name: 'دفتر عميل',
    icon: 'BookOpenCheck',
    description: 'دفتر مكتب محاسبة يُمسَك بالسندات — بلا مخزون ولا فواتير بيع أو شراء.',
  },
];

/**
 * قوالبُ **إنشاء شركة**: ما يملكه المستخدم لنفسه. `client_book` ليس منها —
 * دفتر العميل يفتحه مكتبُ محاسبةٍ لزبونه من «دفاتر عملائي» تحت حصّة
 * `office.managed_books`، وشاشةُ بدايته وقناعه ووحدته المرخَّصة كلّها مبنيّة
 * على وجود مكتبٍ فوقه؛ من أنشأه شركةً مستقلّة حصل على دفترٍ بلا مكتب.
 * الخادم يفرض القاعدة نفسها (`tenants.company_templates.assert_self_serve_template`)
 * — هذه القائمة عرضٌ لها لا مصدرُها.
 */
export const SELF_SERVE_COMPANY_TEMPLATES: readonly CompanyTemplate[] =
  COMPANY_TEMPLATES.filter((template) => template.key !== 'client_book');

/**
 * قوالبُ **دفتر العميل**: `client_book` وحده. القالبان الآخران يفتحان نظاماً
 * كاملاً للزبون — نقيضُ ما بُني له هذا الباب. يفرضها الخادم بـ`assert_book_template`.
 */
export const CLIENT_BOOK_TEMPLATES: readonly CompanyTemplate[] =
  COMPANY_TEMPLATES.filter((template) => template.key === 'client_book');

export function companyTemplateByKey(key: string): CompanyTemplate | undefined {
  return COMPANY_TEMPLATES.find((template) => template.key === key);
}
