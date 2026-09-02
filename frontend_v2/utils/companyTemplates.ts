/**
 * ISSUE #50 — سِجلّ قوالب الشركة (مرآة `tenants/company_templates.py`).
 *
 * منتقي القالب في شاشة إنشاء الشركة يعرض بطاقة لكل قيمة هنا: أيقونة واسم
 * ووصف سطر يقول ماذا يُفعَّل وماذا يُخفى (قرار 13). المفتاح `key` هو نفسه ما
 * يُرسَل في جسد `POST /api/tenants/companies/` (`template`)، و`general` هو
 * الافتراضي — بلا قناع وبلا تغيير سلوك (قرار 16).
 */

export type CompanyTemplateKey = 'general' | 'accounting_firm';

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
    key: 'accounting_firm',
    name: 'مكتب محاسبة',
    icon: 'Calculator',
    description: 'أتعاب مهنية بلا مخزون ولا استيراد — سبعة أنواع مستندات فقط.',
  },
];

export function companyTemplateByKey(key: string): CompanyTemplate | undefined {
  return COMPANY_TEMPLATES.find((template) => template.key === key);
}
