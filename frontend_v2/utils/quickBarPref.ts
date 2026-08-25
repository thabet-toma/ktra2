/**
 * تفضيل «شريط الوصول السريع» (الشريط الأفقي أعلى المحتوى: رجوع + الاختصارات +
 * مرسى «مرشد الرحلة»): مبسوط أم مطويّ — **لكل مستخدم**.
 *
 * لماذا لكل مستخدم لا لكل متصفّح: جهاز المحلّ مشترك بطبعه، وطيُّ صاحب المحلّ
 * للشريط يحرم الموظّف من زرّ «رجوع» ومن اختصاراته على الجهاز نفسه. المفتاح
 * مُلحق بمعرّف المستخدم الذي يمسكه `AuthContext` — نفس عقد `importGuidePref.ts`
 * حرفاً بحرف كي لا يتفرّق نمطان لتفضيلٍ واحد المعنى.
 *
 * والافتراضي **مبسوط** — عكس المرشد: الشريط سلوك اليوم، ومن يطويه يطويه بقرارٍ
 * صريح فيُحفظ له. لا يُطوى أحدٌ لم يطلب.
 *
 * ملف صرف بلا React ولا DOM ولا شبكة — لذلك يُختبر وحده
 * (`utils/quickBarPref.test.ts`).
 */

/** المخزن المطلوب فعلاً — `localStorage` يحقّقه، والاختبار يزيّفه بلا متصفح. */
export type PrefStore = Pick<Storage, "getItem" | "setItem">;

/**
 * مُعرّف المنطقة القابلة للطيّ — يربط زرّ الكشف بمحتواه (`aria-controls`).
 * الاسم هنا لا في الترميز كي لا يتفرّق نصّان: زرٌّ يشير إلى مُعرّفٍ غير موجود
 * يكسر إعلان قارئ الشاشة بصمت.
 */
export const QUICK_BAR_REGION_ID = "quick-access-bar";

/** يُبثّ عند كل تبديل فتُحدَّث كل النسخ المركّبة بلا إعادة تحميل. */
export const QUICK_BAR_EVENT = "ktra:quick-bar";

const BASE_KEY = "ktra.quickBar.open";

/**
 * مفتاح التخزين لهذا المستخدم. بلا معرّف (لحظة ما قبل وصول الملف الشخصي) يعود
 * للمفتاح العام بدل أن يكتب تحت مفتاح `:undefined` يخصّ لا أحد.
 */
export function quickBarOpenKey(userId: string | null | undefined): string {
  const id = String(userId ?? "").trim();
  return id ? `${BASE_KEY}:${id}` : BASE_KEY;
}

/**
 * هل يُعرض الشريط لهذا المستخدم؟ الافتراضي `true` — لا يُطوى إلا لمن طواه
 * صراحةً. التخزين المحظور (وضع خاص، حصّة ممتلئة) لا يُخفي الشريط: يعود
 * للافتراضي، فالطيّ الصامت يسلب المستخدم زرّ «رجوع» بلا سبب يراه.
 */
export function readQuickBarOpen(store: PrefStore, userId: string | null | undefined): boolean {
  try {
    return store.getItem(quickBarOpenKey(userId)) !== "0";
  } catch {
    return true;
  }
}

/** يحفظ الاختيار لهذا المستخدم — وفشل الحفظ لا يمنع الطيّ من العمل في الجلسة. */
export function writeQuickBarOpen(
  store: PrefStore,
  userId: string | null | undefined,
  open: boolean,
): void {
  try {
    store.setItem(quickBarOpenKey(userId), open ? "1" : "0");
  } catch {
    /* التخزين المحظور لا يمنع الشريط من الطيّ والبسط في هذه الجلسة */
  }
}
