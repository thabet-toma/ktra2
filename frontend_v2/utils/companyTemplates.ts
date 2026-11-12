/**
 * ISSUE #50 — سِجلّ قوالب الشركة (مرآة `tenants/company_templates.py`).
 *
 * منتقي القالب في شاشة إنشاء الشركة يعرض بطاقة لكل قيمة هنا: أيقونة واسم
 * ووصف سطر يقول ماذا يُفعَّل وماذا يُخفى (قرار 13). المفتاح `key` هو نفسه ما
 * يُرسَل في جسد `POST /api/tenants/companies/` (`template`)، و`general` هو
 * الافتراضي — بلا قناع وبلا تغيير سلوك (قرار 16).
 *
 * #291: مفتاحا `accounting_firm` و`client_book` حُذفا من الواجهة مع طبقة
 * «المكتب القديمة». **يبقيان في الخادم** (`tenants/company_templates.py`
 * و`core/shell_manifest.py`) لهذه الموجة، ويُحذفان في تذكرةٍ منفصلة بعد تحويل
 * آخر مكتب — فلا تُعِد إدراجهما هنا قبل ذلك.
 */

export type CompanyTemplateKey =
  | 'general' | 'tyres' | 'accounting_office';

export type CompanyTemplate = {
  key: CompanyTemplateKey;
  name: string;
  /** اسم أيقونة lucide-react */
  icon: string;
  description: string;
};

export const DEFAULT_COMPANY_TEMPLATE: CompanyTemplateKey = 'general';

export const COMPANY_TEMPLATES: readonly CompanyTemplate[] = [
  {
    key: 'general',
    name: 'عام / تجاري',
    icon: 'Building2',
    description: 'دليل حسابات تجاري كامل — مخزون واستيراد وكل أنواع المستندات.',
  },
  {
    key: 'tyres',
    name: 'إطارات',
    icon: 'Disc',
    description: 'مطابقٌ اليوم لقالب «عام / تجاري» حرفياً — مفتاحٌ مستقل تُعلَّق عليه تخصيصات قطاع الإطارات لاحقاً.',
  },
  // ISSUE #271 — قالبُ موديول مكتب المحاسبة الجديد. كان في الخادم
  // (`COMPANY_TEMPLATES` ومفتاحُ الترخيص `accounting_office`) وبلا بطاقةٍ هنا،
  // فلا يقدر أحدٌ على إنشاء شركةٍ به من الشاشة. الوصفُ منقولٌ عن الخادم.
  {
    key: 'accounting_office',
    name: 'مكتب محاسبة (الجديد)',
    icon: 'Landmark',
    description: 'مكتب محاسبة بموديول المكتب الجديد — زبون المكتب وبطاقته الضريبية وجهاته وإعداداته، بلا مخزون ولا استيراد.',
  },
];

/**
 * قوالبُ **إنشاء شركة**: ما يملكه المستخدم لنفسه. بعد #291 لم يبقَ قالبٌ
 * مستثنى — `client_book` كان الوحيد، وقد حُذف مع دفاتر العملاء المُدارة.
 */
export const SELF_SERVE_COMPANY_TEMPLATES: readonly CompanyTemplate[] = COMPANY_TEMPLATES;

export function companyTemplateByKey(key: string): CompanyTemplate | undefined {
  return COMPANY_TEMPLATES.find((template) => template.key === key);
}
