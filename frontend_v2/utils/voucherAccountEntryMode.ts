/**
 * وضعُ إدخال حساب سند المصروف/الإيراد — مرآة
 * `TenantSettings.voucher_account_entry_mode` الخادمي، ومصدرٌ **واحد** للقاعدة
 * تقرأه شاشتا السندين معاً فلا تنحرف إحداهما عن الأخرى.
 *
 * القاعدة تفشل **مفتوحةً** عمداً: غياب القيمة (إعداداتٌ لم تصل بعد، أو شركةٌ
 * أقدم من الحقل) = `free`، وهو السلوك القائم منذ issue #56. الحارسُ الحقيقي
 * خادميّ (`accounting.services._voucher_account_entry_is_linked`) — ما هنا
 * إخفاءُ حقلٍ لا تصريح، فلا يكتب المستخدم في خانةٍ سيردّها الخادم.
 */
export type VoucherAccountEntryMode = "free" | "linked";

export const VOUCHER_ACCOUNT_ENTRY_MODES: {
  value: VoucherAccountEntryMode;
  label: string;
  hint: string;
}[] = [
  {
    value: "free",
    label: "نصّ حرّ — يُنشأ الحساب إن لم يوجد",
    hint: "أسرع للإدخال: تكتب «اشتراك إنترنت» فيُفتح له حسابٌ تحت أبيه المعياري.",
  },
  {
    value: "linked",
    label: "حساب من الشجرة إلزاماً",
    hint: "شجرةٌ مضبوطة لا تنبت فيها حسابات جديدة مع كل سند — يختار المدخِل من الموجود.",
  },
];

export function voucherAccountEntryIsLinked(
  mode: string | null | undefined,
): boolean {
  return mode === "linked";
}
