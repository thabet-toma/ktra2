/**
 * A5 — «وضع المحاسب»: تفضيلُ ترتيبٍ لصاحب هذا المتصفح، يضع مجموعة «المحاسبة»
 * أول القائمة لمن يعمل عليها طول اليوم بدل أن ينزل إليها في كل مرة.
 *
 * **ترتيبٌ لا صلاحية**: لا يغيّر ما يصل إليه المستخدم، ولا مساراً واحداً، ولا
 * مفتاح صلاحية — بل ما يراه أولاً. لذلك يعيش في `localStorage` وحده بلا خادم.
 *
 * دالتان صرفتان (لا React) كي تُختبرا وحدهما، ولا ترميان أبداً: متصفح يمنع
 * التخزين يبقى على الترتيب الافتراضي بدل أن تنكسر القائمة كلها.
 */
export const ACCOUNTANT_MODE_KEY = 'accountantMode';

/** مطفأ افتراضياً — غياب المفتاح أو أي قيمة غير `'1'` تعني مطفأ. */
export function readAccountantMode(): boolean {
  try {
    return localStorage.getItem(ACCOUNTANT_MODE_KEY) === '1';
  } catch {
    return false;
  }
}

export function writeAccountantMode(enabled: boolean): void {
  try {
    localStorage.setItem(ACCOUNTANT_MODE_KEY, enabled ? '1' : '0');
  } catch {
    /* تجاهل — الحالة في الذاكرة تكفي لهذه الجلسة */
  }
}
