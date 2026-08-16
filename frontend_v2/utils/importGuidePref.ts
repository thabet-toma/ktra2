/**
 * تفضيل «مرشد رحلة الاستيراد»: مفتوح أم مطويّ — **لكل مستخدم**.
 *
 * كان المفتاح واحداً للمتصفح كلّه (`ktra.importGuide.open`)، فطيّ صاحب المحل
 * يحرم الموظّف الجديد من المرشد على الجهاز نفسه — وجهاز المحلّ مشترك بطبعه.
 * المفتاح الآن مُلحق بمعرّف المستخدم الذي يمسكه `AuthContext`، فالتفضيل يتبع
 * صاحبه لا الجهاز.
 *
 * والافتراضي **مطويّ**: اللوح يرافق كلّ الشاشات، ولوحٌ يفتح نفسه فوق شاشة لا
 * علاقة لها بالاستيراد يزاحم المحتوى بدل أن يخدمه. من يريده يفتحه بزرّ «مرشد
 * الرحلة» في رأس الشاشة، ويُحفظ اختياره فلا يُسأل مرّتين.
 *
 * ملف صرف بلا React ولا شبكة — لذلك يُختبر وحده (`utils/importGuidePref.test.ts`).
 */

/** المخزن المطلوب فعلاً — `localStorage` يحقّقه، والاختبار يزيّفه بلا متصفح. */
export type PrefStore = Pick<Storage, "getItem" | "setItem">;

/**
 * مرسى زرّ «مرشد الرحلة» في شريط رأس الشاشة — يضعه `AppLayout` ويملؤه
 * `ImportJourneyGuide` عبر portal. الاسم هنا كي لا يتفرّق نصّان: مرسى بلا
 * مالئ يترك فراغاً، ومالئ بلا مرسى يترك المرشد بلا طريقٍ إليه.
 */
export const IMPORT_GUIDE_SLOT_ID = "import-guide-slot";

const BASE_KEY = "ktra.importGuide.open";

/**
 * مفتاح التخزين لهذا المستخدم. بلا معرّف (لحظة ما قبل وصول الملف الشخصي) يعود
 * للمفتاح العام بدل أن يكتب تحت مفتاح `:undefined` يخصّ لا أحد.
 */
export function importGuideOpenKey(userId: string | null | undefined): string {
  const id = String(userId ?? "").trim();
  return id ? `${BASE_KEY}:${id}` : BASE_KEY;
}

/**
 * هل يُفتح اللوح لهذا المستخدم؟ الافتراضي `false` — لا يُفتح إلا لمن فتحه صراحةً.
 * التخزين المحظور (وضع خاص، حصّة ممتلئة) لا يُسقط الشاشة: يعود للافتراضي.
 */
export function readImportGuideOpen(store: PrefStore, userId: string | null | undefined): boolean {
  try {
    return store.getItem(importGuideOpenKey(userId)) === "1";
  } catch {
    return false;
  }
}

/** يحفظ الاختيار لهذا المستخدم — وفشل الحفظ لا يمنع اللوح من العمل في الجلسة. */
export function writeImportGuideOpen(
  store: PrefStore,
  userId: string | null | undefined,
  open: boolean,
): void {
  try {
    store.setItem(importGuideOpenKey(userId), open ? "1" : "0");
  } catch {
    /* التخزين المحظور لا يمنع اللوح من العمل */
  }
}
