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

/**
 * ترتيب المكاتب المرشَّحة — الأوّل هو المُجرَّب أوّلاً.
 *
 * **بلاغ المالك بعد أول تشغيل**: «بكبس دخول لدفتر الزبون بوديني على شركتي
 * الافتراضية». السبب أن من يدير **أكثر من مكتب** كان يقع في فجوة: بعد الدخول
 * إلى الدفتر تصير الشركة النشطة هي الدفترَ نفسه — وهو ليس مكتباً ولا هو في
 * `my-companies` أصلاً — فتسقط قاعدةُ «الشركة النشطة أولاً» ويُختار أصغرُ
 * معرّفٍ بين المكاتب. فإن لم يكن ذاك هو المكتب المالك عادت قائمة دفاترِه بلا
 * دفترِنا، فلا تُحلّ الشركة النشطة وتُستبدل بالافتراضية: أي أن الضغطة تُلقيك
 * في شركةٍ أخرى بلا رسالة.
 *
 * العلاج: `bookOfficeId` — المكتب الذي دخلنا منه، **مكتوبٌ لحظةَ الدخول** في
 * مفتاح الجلسة (`utils/officeShell.ts`) فلا يُستنتج ولا يُخمَّن. ويُقبل ولو لم
 * يحمل قالب المكتب، لأن الجلسة تشهد أننا جئنا منه فعلاً — بخلاف
 * `activeTenantId` الذي هو تفضيلُ ترتيبٍ لا شهادة، فلا يفتح باباً لغير المكاتب.
 */
export function orderOfficesByPreference<T extends OfficeMembershipLike>(
  memberships: T[],
  opts: { bookOfficeId?: number | null; activeTenantId?: number | null } = {},
): T[] {
  const managed = memberships.filter((m) => m.role === "manager");
  const { bookOfficeId = null, activeTenantId = null } = opts;
  const candidates = managed.filter(
    (m) => m.tenant.template === OFFICE_TEMPLATE
      || (bookOfficeId != null && m.tenant.TenantID === bookOfficeId),
  );
  const rank = (m: T): number => {
    if (bookOfficeId != null && m.tenant.TenantID === bookOfficeId) return 0;
    if (activeTenantId != null && m.tenant.TenantID === activeTenantId) return 1;
    return 2;
  };
  // ترتيبٌ ثابت لا «أوّل ما وصل من الخادم»: قائمةٌ تتبدّل تعني قائمة دفاترٍ
  // تتبدّل تحت المستخدم بين تحميلٍ وآخر بلا سببٍ يراه.
  return [...candidates].sort(
    (a, b) => rank(a) - rank(b) || a.tenant.TenantID - b.tenant.TenantID,
  );
}

/** عضوية المكتب التي تُعنوَن بها نداءات الدفاتر المُدارة، أو `null` فلا باب. */
export function pickOfficeTenant<T extends OfficeMembershipLike>(
  memberships: T[],
  activeTenantId: number | null,
): T | null {
  return orderOfficesByPreference(memberships, { activeTenantId })[0] ?? null;
}
