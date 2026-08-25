/**
 * M7-T4 — ترحيل مفاتيح التخزين المحلي من سابقة `aseel_` إلى `ktra_`.
 *
 * إعادة التسمية طالت **مفاتيح حيّة في متصفّحات المستخدمين**: عروض أعمدة كل
 * جدول ضبطه المستخدم بيده، وارتفاعات صفوفه، وسجلّ حاسبته. تغييرُ اسم المفتاح
 * بلا ترحيل يعني أن ضبطاً بُني عبر شهور **يختفي بصمت** عند أول تحديث — وهو
 * أسوأ ثمنٍ يُدفع مقابل مكسبٍ تجميلي لا يراه أحد.
 *
 * الترحيل يجري **مرّةً واحدة عند الإقلاع**: كل مفتاح بالسابقة القديمة يُنسخ إلى
 * الجديدة ثم يُحذف. لا يُدهس مفتاحٌ جديد موجود (المستخدم عدّل بعد الترحيل على
 * جهازٍ آخر مثلاً)، والفشل لا يُسقط الإقلاع.
 */

/** المخزن المطلوب فعلاً — `localStorage` يحقّقه، والاختبار يزيّفه بلا متصفح. */
export type MigratableStore = {
  readonly length: number;
  key(index: number): string | null;
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
};

export const LEGACY_PREFIX = "aseel_";
export const CURRENT_PREFIX = "ktra_";

/**
 * ينقل المفاتيح ويُرجع عددها. يجمع الأسماء **قبل** الكتابة: التعديل أثناء
 * المرور على `localStorage` بالفهرس يُزحزح البقية فتُتخطّى مفاتيح بصمت.
 */
export function migrateLegacyStorageKeys(store: MigratableStore): number {
  let moved = 0;
  try {
    const legacy: string[] = [];
    for (let i = 0; i < store.length; i += 1) {
      const key = store.key(i);
      if (key && key.startsWith(LEGACY_PREFIX)) legacy.push(key);
    }

    for (const oldKey of legacy) {
      const newKey = CURRENT_PREFIX + oldKey.slice(LEGACY_PREFIX.length);
      const value = store.getItem(oldKey);
      /* مفتاحٌ جديد موجود = رأيٌ أحدث؛ لا يُدهس، ويُنظَّف القديم فقط. */
      if (value !== null && store.getItem(newKey) === null) {
        store.setItem(newKey, value);
        moved += 1;
      }
      store.removeItem(oldKey);
    }
  } catch {
    /* تخزينٌ محظور أو ممتلئ: الإقلاع يمضي، والمفاتيح تبقى كما هي */
  }
  return moved;
}
