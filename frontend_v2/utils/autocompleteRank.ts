/**
 * T-SEARCH — قاعدة ترتيب نتائج البحث المدمج (`KitAutocomplete`).
 *
 * مقعدها هنا لا في المكوّن: الملف الذي يحمل JSX لا يمرّ من `node --test`،
 * وقاعدة البحث أصغر من أن تبقى بلا اختبار وأكبر من أن تُجرَّب يدوياً في كل
 * شاشة تستعملها.
 *
 * ما تصلحه عن سابقتها:
 *  1. **الحقول** — كانت تبحث في الاسم والسطر الثانوي وحدهما، فرقمُ الصنف
 *     وباركودُه (وهما ما يكتبه البائع فعلاً) لا يجدان شيئاً وإن كانا في
 *     البيانات. `keywords` حقلٌ يُبحَث فيه ولا يُعرض.
 *  2. **الكلمات** — كانت تطابق النصّ المكتوب كاملاً، فـ«اطار 17» لا يجد
 *     «اطار ميشلان 17». الآن كل كلمة تُطابَق وحدها، والصفّ يمرّ إن طابقت
 *     كلماتُه كلُّها في أيّ حقل.
 *  3. **المحجوب** — تُعيد العدد الكلّي، فتعرف الشاشة كم نتيجةً أخفاها السقف
 *     بدل أن تصمت عمّا لم تعرضه.
 */

export type RankableOption = {
  label: string;
  sub?: string;
  /** نصٌّ إضافي يُبحَث فيه ولا يُعرض (SKU · باركود · هاتف). */
  keywords?: string;
};

export type RankResult<T> = {
  matches: T[];
  /** عدد المطابقات كلّها قبل القصّ على `max`. */
  total: number;
};

/** درجات المطابقة — الأصغر أولى. */
const SCORE_LABEL_PREFIX = 0;
const SCORE_LABEL_CONTAINS = 1;
const SCORE_SUB = 2;
const SCORE_KEYWORDS = 3;

export function rankOptions<T extends RankableOption>(
  options: T[], query: string, max: number,
): RankResult<T> {
  const needle = query.trim().toLowerCase();
  if (!needle) return { matches: options.slice(0, max), total: options.length };

  const tokens = needle.split(/\s+/).filter(Boolean);
  const scored: Array<{ opt: T; score: number }> = [];

  for (const opt of options) {
    const label = (opt.label || '').toLowerCase();
    const sub = (opt.sub || '').toLowerCase();
    const keywords = (opt.keywords || '').toLowerCase();
    let best = Number.POSITIVE_INFINITY;
    let matchedAll = true;

    for (const token of tokens) {
      let score: number;
      if (label.startsWith(token)) score = SCORE_LABEL_PREFIX;
      else if (label.includes(token)) score = SCORE_LABEL_CONTAINS;
      else if (sub.includes(token)) score = SCORE_SUB;
      else if (keywords.includes(token)) score = SCORE_KEYWORDS;
      else { matchedAll = false; break; }
      if (score < best) best = score;
    }

    if (matchedAll) scored.push({ opt, score: best });
  }

  scored.sort(
    (a, b) => a.score - b.score || a.opt.label.length - b.opt.label.length,
  );
  return { matches: scored.slice(0, max).map((s) => s.opt), total: scored.length };
}

/**
 * موضع أول تطابق في نصّ — تستعمله الشاشة لتظليله.
 * يُعيد `null` إن لم تطابق أيّ كلمة.
 */
export function firstMatchRange(
  text: string, query: string,
): { start: number; end: number } | null {
  const needle = query.trim().toLowerCase();
  if (!needle || !text) return null;
  const lower = text.toLowerCase();
  for (const token of needle.split(/\s+/).filter(Boolean)) {
    const at = lower.indexOf(token);
    if (at >= 0) return { start: at, end: at + token.length };
  }
  return null;
}
