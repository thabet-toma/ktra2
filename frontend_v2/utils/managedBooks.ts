/**
 * ISSUE #65 — أين المكتب؟ سؤالٌ يسبق كل نداء على `managed-books/`.
 *
 * نقطة الدفاتر المُدارة معنونةٌ بالمكتب (`companies/{office}/managed-books/`)،
 * فلا تُقرأ ولا يُنشأ فيها دفترٌ قبل تحديد الشركة التي تلعب دور المكتب. القاعدة
 * هنا **دالّة نقيّة** تُختبر بلا متصفح، ومصدرها العضويات التي تحمّلها
 * `CompanyContext` أصلاً — فلا نقطة خادمٍ جديدة ولا استعلامٌ ثانٍ.
 *
 * المكتب = شركةٌ بقالب `accounting_firm` يديرها المستخدم. **القالب شرطٌ لا
 * زينة**: نقطة `managed-books` تقبل أي مديرِ شركة، لكنّ فتح دفاترٍ لعملاء عملٌ
 * مكتبيٌّ لا تجاري — فلو عرضنا البابَ لكل مديرٍ لَرأى صاحبُ محلٍّ تجاري قائمة
 * «دفاتر عملائي» في شريطه بلا معنى.
 *
 * والأولوية للشركة النشطة: من يدير مكتبين يفتح دفاتر المكتب الذي يعمل عليه
 * الآن، لا دفاتر أوّلِ مكتبٍ بالترتيب.
 */

export const OFFICE_TEMPLATE = "accounting_firm";

export interface OfficeMembershipLike {
  role: string;
  tenant: { TenantID: number; template?: string };
}

/** عضوية المكتب التي تُعنوَن بها نداءات الدفاتر المُدارة، أو `null` فلا باب. */
export function pickOfficeTenant<T extends OfficeMembershipLike>(
  memberships: T[],
  activeTenantId: number | null,
): T | null {
  const offices = memberships.filter(
    (m) => m.role === "manager" && m.tenant.template === OFFICE_TEMPLATE,
  );
  if (offices.length === 0) return null;
  if (activeTenantId != null) {
    const active = offices.find((m) => m.tenant.TenantID === activeTenantId);
    if (active) return active;
  }
  // ترتيبٌ ثابت لا «أوّل ما وصل من الخادم»: قائمةٌ تتبدّل تعني قائمة دفاترٍ
  // تتبدّل تحت المستخدم بين تحميلٍ وآخر بلا سببٍ يراه.
  return offices.reduce((best, m) =>
    m.tenant.TenantID < best.tenant.TenantID ? m : best);
}
